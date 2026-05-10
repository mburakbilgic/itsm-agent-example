"""Infrastructure layer — concrete adapters.

Sub-packages (`llm/`, `rag/`, `mcp/`, `reports/`) are imported explicitly by
the consumer (typically `composition.builder`). We do NOT eagerly re-export
them here because that would force heavy modules (SentenceTransformer,
ChromaDB, MCP client) to load every time the package is touched — which
kills test startup time and the domain layer's framework-free isolation.
"""
