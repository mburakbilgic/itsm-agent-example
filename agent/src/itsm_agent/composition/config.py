"""All env-var reading happens here. Other modules accept a frozen config."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    base_url: str
    model: str
    temperature: float
    num_ctx: int


@dataclass(frozen=True, slots=True)
class RagConfig:
    kb_dir: Path
    persist_dir: Path
    embedding_model: str
    top_k: int
    collection: str


@dataclass(frozen=True, slots=True)
class McpConfig:
    server_url: str


@dataclass(frozen=True, slots=True)
class ReportsConfig:
    out_dir: Path


@dataclass(frozen=True, slots=True)
class AgentConfig:
    ollama: OllamaConfig
    rag: RagConfig
    mcp: McpConfig
    reports: ReportsConfig
    log_level: str

    @classmethod
    def from_env(cls) -> AgentConfig:
        return cls(
            ollama=OllamaConfig(
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"),
                model=os.environ.get("OLLAMA_MODEL", "qwen2.5:3b"),
                temperature=_float_env("OLLAMA_TEMPERATURE", 0.2),
                num_ctx=_int_env("OLLAMA_NUM_CTX", 8192),
            ),
            rag=RagConfig(
                kb_dir=Path(os.environ.get("KB_DIR", "/app/kb")),
                persist_dir=Path(os.environ.get("CHROMA_PERSIST_DIR", "/app/chroma_data")),
                embedding_model=os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"),
                top_k=_int_env("TOP_K", 4),
                collection=os.environ.get("CHROMA_COLLECTION", "itsm_kb"),
            ),
            mcp=McpConfig(
                server_url=os.environ.get("MCP_SERVER_URL", "http://mcp-server:8001/mcp"),
            ),
            reports=ReportsConfig(
                out_dir=Path(os.environ.get("REPORTS_DIR", "/app/reports")),
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"Environment variable {name}={raw!r} is not a valid integer") from e


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(f"Environment variable {name}={raw!r} is not a valid float") from e
