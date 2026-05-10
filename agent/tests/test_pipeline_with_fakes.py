"""End-to-end pipeline test using only domain fakes.

These tests exercise the LangGraph composition without touching Ollama,
ChromaDB, or MCP — proving the pipeline contract is independent of any
specific adapter.
"""

from __future__ import annotations

import pytest

from itsm_agent.application.pipeline import AgentPipeline, PipelineDependencies
from itsm_agent.domain.services import RetrievalQueryBuilder


@pytest.fixture
def pipeline(fake_tickets, fake_kb, fake_llm, fake_renderer, fake_reports):
    deps = PipelineDependencies(
        tickets=fake_tickets,
        knowledge=fake_kb,
        llm=fake_llm,
        renderer=fake_renderer,
        reports=fake_reports,
        query_builder=RetrievalQueryBuilder(),
        top_k=4,
    )
    return AgentPipeline(deps)


async def test_happy_path_writes_report(pipeline, fake_reports):
    state = await pipeline.run("INC-9001")
    assert "error" not in state or state.get("error") is None
    assert state["report_path"] == "/fake/reports/INC-9001.md"
    assert len(fake_reports.saved) == 1
    saved_report, saved_body = fake_reports.saved[0]
    assert saved_report.ticket.id == "INC-9001" or str(saved_report.ticket.id) == "INC-9001"
    assert saved_body == "RENDERED-BODY"


async def test_unknown_ticket_short_circuits_without_writing(pipeline, fake_reports):
    state = await pipeline.run("INC-UNKNOWN")
    assert state.get("error")
    assert "not found" in state["error"]
    assert fake_reports.saved == []


async def test_kb_query_built_from_ticket_and_comments(pipeline, fake_kb):
    await pipeline.run("INC-9001")
    assert len(fake_kb.calls) == 1
    query, top_k = fake_kb.calls[0]
    assert top_k == 4
    # Query should weave together title, description, logs, and comments.
    assert "DB lock contention" in query
    assert "deadlock detected" in query
    assert "spike at 08:02" in query
