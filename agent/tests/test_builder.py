from __future__ import annotations

from pathlib import Path

import pytest

from itsm_agent.composition.builder import (
    AgentApplication,
    AgentBuilder,
    BuilderError,
)
from itsm_agent.composition.config import (
    AgentConfig,
    McpConfig,
    OllamaConfig,
    RagConfig,
    ReportsConfig,
)


def _config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(
        ollama=OllamaConfig(base_url="http://x", model="m", temperature=0.2, num_ctx=8192),
        rag=RagConfig(
            kb_dir=tmp_path / "kb",
            persist_dir=tmp_path / "chroma",
            embedding_model="ignored",
            top_k=3,
            collection="test_kb",
        ),
        mcp=McpConfig(server_url="http://mcp/"),
        reports=ReportsConfig(out_dir=tmp_path / "reports"),
        log_level="INFO",
    )


def test_build_without_config_raises():
    with pytest.raises(BuilderError, match="with_config"):
        AgentBuilder().build()


def test_build_without_collaborators_lists_missing(tmp_path: Path):
    builder = AgentBuilder().with_config(_config(tmp_path))
    with pytest.raises(BuilderError) as exc:
        builder.build()
    msg = str(exc.value)
    for name in ("tickets", "knowledge", "llm", "renderer", "reports"):
        assert name in msg


def test_build_with_all_custom_collaborators_returns_application(
    tmp_path: Path,
    fake_tickets,
    fake_kb,
    fake_llm,
    fake_renderer,
    fake_reports,
):
    app = (
        AgentBuilder()
        .with_config(_config(tmp_path))
        .with_custom_ticket_repository(fake_tickets)
        .with_custom_knowledge_base(fake_kb)
        .with_custom_llm(fake_llm)
        .with_custom_renderer(fake_renderer)
        .with_custom_report_repository(fake_reports)
        .build()
    )
    assert isinstance(app, AgentApplication)
    assert app.generate_one is not None
    assert app.generate_all is not None
