"""REST API smoke tests with the application stack stubbed out.

Pre-build an `AgentApplication` with in-memory fakes and inject it via
`create_app(application=...)`. The TestClient then exercises real route
handlers without touching Ollama / Chroma / MCP.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from itsm_agent.composition.builder import AgentBuilder
from itsm_agent.composition.config import (
    AgentConfig,
    McpConfig,
    OllamaConfig,
    RagConfig,
    ReportsConfig,
)
from itsm_agent.interfaces.jobs import JobStatus, JobStore
from itsm_agent.interfaces.rest import create_app
from tests.conftest import FakeReportRenderer, TmpFileReportRepository


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
def client(tmp_path, fake_tickets, fake_kb, fake_llm):
    config = _config(tmp_path)
    application = (
        AgentBuilder()
        .with_config(config)
        .with_custom_ticket_repository(fake_tickets)
        .with_custom_knowledge_base(fake_kb)
        .with_custom_llm(fake_llm)
        .with_custom_renderer(FakeReportRenderer(body="# fake report body\n"))
        .with_custom_report_repository(TmpFileReportRepository(config.reports.out_dir))
        .build()
    )
    app = create_app(application=application, config=config, jobs=JobStore(concurrency=1))
    with TestClient(app) as tc:
        yield tc


def _wait_for_terminal(client: TestClient, job_id: str, timeout_s: float = 5.0) -> dict:
    """Poll /jobs/{id} until status is succeeded/failed or timeout expires."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = client.get(f"/jobs/{job_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in (JobStatus.SUCCEEDED.value, JobStatus.FAILED.value):
            return body
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not terminate in {timeout_s}s")


def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_list_tickets_returns_open_ids(client, fake_tickets):
    r = client.get("/tickets")
    assert r.status_code == 200
    payload = r.json()
    assert {t["id"] for t in payload} == set(fake_tickets.bundles.keys())


def test_submit_rca_returns_202_then_succeeds(client):
    submit = client.post("/rca/INC-9001")
    assert submit.status_code == 202
    job = submit.json()
    assert job["status"] == JobStatus.QUEUED.value
    assert job["ticket_id"] == "INC-9001"

    final = _wait_for_terminal(client, job["job_id"])
    assert final["status"] == JobStatus.SUCCEEDED.value
    assert final["report_path"] is not None


def test_submit_rca_for_unknown_ticket_finishes_failed(client):
    job_id = client.post("/rca/INC-DOES-NOT-EXIST").json()["job_id"]
    final = _wait_for_terminal(client, job_id)
    assert final["status"] == JobStatus.FAILED.value
    assert final["error"] is not None
    assert "not found" in final["error"]


def test_get_unknown_job_is_404(client):
    r = client.get("/jobs/does-not-exist")
    assert r.status_code == 404


def test_get_report_returns_markdown_after_job_succeeds(client):
    job_id = client.post("/rca/INC-9001").json()["job_id"]
    _wait_for_terminal(client, job_id)
    r = client.get("/reports/INC-9001")
    assert r.status_code == 200
    assert r.text == "# fake report body\n"


def test_get_report_for_unknown_ticket_is_404(client):
    r = client.get("/reports/INC-NOPE")
    assert r.status_code == 404


@pytest.mark.parametrize(
    "bad_id",
    [
        "../etc/passwd",
        "..%2Fetc%2Fpasswd",
        "INC/../foo",
        "with spaces",
        "with;semicolon",
        "a" * 65,  # too long
        "",
    ],
)
def test_get_report_rejects_unsafe_ticket_id(client, bad_id):
    r = client.get(f"/reports/{bad_id}")
    # Either 400 (validator) or 404 (not found / not under out_dir).
    assert r.status_code in (400, 404)
    # Must never leak filesystem contents.
    assert "root:" not in r.text


def test_ready_returns_ok_when_dependencies_reachable(client, monkeypatch):
    from itsm_agent.interfaces import rest as rest_mod

    async def fake_checks(_config):
        return [
            rest_mod.ReadinessCheck(name="ollama", ok=True),
            rest_mod.ReadinessCheck(name="mcp", ok=True),
        ]

    monkeypatch.setattr(rest_mod, "_readiness_checks", fake_checks)
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert {c["name"] for c in body["checks"]} == {"ollama", "mcp"}


def test_ready_returns_not_ready_when_dependency_down(client, monkeypatch):
    from itsm_agent.interfaces import rest as rest_mod

    async def fake_checks(_config):
        return [
            rest_mod.ReadinessCheck(name="ollama", ok=True),
            rest_mod.ReadinessCheck(name="mcp", ok=False, detail="connection refused"),
        ]

    monkeypatch.setattr(rest_mod, "_readiness_checks", fake_checks)
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    mcp_check = next(c for c in body["checks"] if c["name"] == "mcp")
    assert mcp_check["ok"] is False
    assert "connection refused" in mcp_check["detail"]
