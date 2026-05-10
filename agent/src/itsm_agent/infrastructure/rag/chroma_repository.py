from __future__ import annotations

import contextlib
import hashlib
import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings

from itsm_agent.domain.value_objects import RetrievedChunk
from itsm_agent.infrastructure.rag.e5_embedder import E5Embedder
from itsm_agent.infrastructure.rag.markdown_chunker import MarkdownChunker

log = logging.getLogger(__name__)


class ChromaKnowledgeRepository:
    """KnowledgeRepository implementation backed by ChromaDB.

    Indexes the KB at construction time. Re-indexes only when the source
    files change (tracked by name + size + mtime fingerprint).
    """

    def __init__(
        self,
        kb_dir: Path,
        persist_dir: Path,
        embedder: E5Embedder,
        collection: str,
        chunker: MarkdownChunker | None = None,
    ) -> None:
        self._kb_dir = kb_dir
        self._persist_dir = persist_dir
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._embedder = embedder
        self._chunker = chunker or MarkdownChunker()
        self._collection_name = collection
        self._client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(self._collection_name)
        self._ensure_indexed()

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        emb = [self._embedder.encode_query(query)]
        res = self._collection.query(query_embeddings=emb, n_results=top_k)
        ids = res["ids"][0]
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res.get("distances", [[0.0] * len(ids)])[0]
        chunks: list[RetrievedChunk] = []
        for cid, doc, meta, dist in zip(ids, docs, metas, dists, strict=False):
            similarity = 1.0 - (dist / 2.0)  # cosine ~= 1 - dist/2 for normalized vectors
            chunks.append(
                RetrievedChunk(
                    doc_id=cid,
                    source=meta.get("source", "?"),
                    section=meta.get("section", "?"),
                    text=doc,
                    score=round(similarity, 4),
                )
            )
        return chunks

    def _fingerprint(self) -> str:
        h = hashlib.sha256()
        for p in sorted(self._kb_dir.glob("*.md")):
            st = p.stat()
            h.update(p.name.encode())
            h.update(str(st.st_size).encode())
            h.update(str(int(st.st_mtime)).encode())
        return h.hexdigest()

    def _ensure_indexed(self) -> None:
        fp_file = self._persist_dir / "fingerprint.txt"
        current = self._fingerprint()
        previous = fp_file.read_text().strip() if fp_file.exists() else ""
        if current == previous and self._collection.count() > 0:
            log.info("KB index up to date (%d chunks).", self._collection.count())
            return

        log.info("Rebuilding KB index from %s", self._kb_dir)
        with contextlib.suppress(Exception):
            self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(self._collection_name)

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        for md_path in sorted(self._kb_dir.glob("*.md")):
            text = md_path.read_text(encoding="utf-8")
            for i, (section, body) in enumerate(self._chunker.split(text)):
                ids.append(f"{md_path.stem}::{i:02d}")
                documents.append(f"{section}\n\n{body}")
                metadatas.append({"source": md_path.name, "section": section})

        if not documents:
            log.warning("No KB documents found in %s", self._kb_dir)
            return

        embeddings = self._embedder.encode_passages(documents)
        self._collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        fp_file.write_text(current)
        log.info(
            "Indexed %d chunks across %d files.",
            len(ids),
            len({m["source"] for m in metadatas}),
        )
