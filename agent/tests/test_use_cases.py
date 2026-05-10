from __future__ import annotations

from pathlib import Path

import pytest

from itsm_agent.composition.builder import AgentBuilder
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
            top_k=4,
            collection="test_kb",
        ),
        mcp=McpConfig(server_url="http://mcp/"),
        reports=ReportsConfig(out_dir=tmp_path / "reports"),
        log_level="INFO",
    )


@pytest.fixture
def app(tmp_path, fake_tickets, fake_kb, fake_llm, fake_renderer, fake_reports):
    return (
        AgentBuilder()
        .with_config(_config(tmp_path))
        .with_custom_ticket_repository(fake_tickets)
        .with_custom_knowledge_base(fake_kb)
        .with_custom_llm(fake_llm)
        .with_custom_renderer(fake_renderer)
        .with_custom_report_repository(fake_reports)
        .build()
    )


async def test_generate_one_succeeds_for_known_ticket(app, fake_reports):
    response = await app.run_for_ticket("INC-9001")
    assert response.succeeded
    assert response.ticket_id == "INC-9001"
    assert response.error is None
    assert len(fake_reports.saved) == 1


async def test_generate_one_fails_for_unknown_ticket(app):
    response = await app.run_for_ticket("INC-DOES-NOT-EXIST")
    assert not response.succeeded
    assert response.error is not None
    assert "not found" in response.error


async def test_generate_all_runs_each_open_ticket(app, fake_tickets):
    responses = await app.run_all()
    assert fake_tickets.list_calls == 1
    assert len(responses) == len(fake_tickets.bundles)
    assert all(r.succeeded for r in responses)


async def test_llm_called_twice_per_ticket_analysis_then_remediation(app, fake_llm):
    await app.run_for_ticket("INC-9001")
    # One call for analysis, one for remediation.
    assert len(fake_llm.calls) == 2
