from __future__ import annotations

from sentence_transformers import SentenceTransformer


class E5Embedder:
    """SentenceTransformer wrapper that applies E5 task-specific prefixes."""

    QUERY_PREFIX = "query: "
    PASSAGE_PREFIX = "passage: "

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(
            [self.PASSAGE_PREFIX + t for t in texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    def encode_query(self, text: str) -> list[float]:
        vec = self._model.encode(
            [self.QUERY_PREFIX + text],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()
        return vec[0]
