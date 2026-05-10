"""FastAPI surface for the agent.

A long-running container exposes:

- POST /rca/{ticket_id} → enqueue an RCA job, return job_id
- GET  /jobs/{job_id}   → poll status
- GET  /reports/{ticket_id} → fetch the rendered Markdown
- GET  /tickets         → list open ticket ids
- GET  /health          → liveness
- GET  /ready           → readiness (deps reachable)
- /docs                 → Swagger UI

Endpoints are thin: they translate between HTTP and the application
use cases / job store. No business logic lives here.
"""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from itsm_agent.composition.builder import AgentApplication, build_default_application
from itsm_agent.composition.config import AgentConfig
from itsm_agent.interfaces.jobs import JobRecord, JobStatus, JobStore

log = logging.getLogger(__name__)

DependencyName = Literal["ollama", "mcp"]

_TICKET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


# ----- Pydantic response models -------------------------------------------


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])


class ReadinessCheck(BaseModel):
    name: DependencyName
    ok: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    ready: bool
    checks: list[ReadinessCheck]


class TicketSummary(BaseModel):
    id: str


class JobStatusResponse(BaseModel):
    job_id: str
    ticket_id: str
    status: JobStatus
    submitted_at: str
    started_at: str | None = None
    finished_at: str | None = None
    report_path: str | None = None
    error: str | None = None


class SubmitJobResponse(BaseModel):
    job_id: str
    ticket_id: str
    status: JobStatus


def _to_response(job: JobRecord) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job.id,
        ticket_id=job.ticket_id,
        status=job.status,
        submitted_at=job.submitted_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        report_path=job.report_path,
        error=job.error,
    )


# ----- Lifespan -----------------------------------------------------------


def _make_lifespan(
    application: AgentApplication | None,
    config: AgentConfig | None,
    jobs: JobStore | None,
):
    """Lifespan factory.

    If `application` (and friends) is supplied, lifespan reuses it as-is —
    used by tests so they can inject a fake-backed application without
    triggering Ollama / Chroma loading. Otherwise the lifespan builds the
    real defaults from environment.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_config = config or AgentConfig.from_env()
        app.state.config = resolved_config
        if application is None:
            log.info("Building agent application (loading models + KB index)…")
            app.state.application = build_default_application(resolved_config)
            log.info("Agent ready.")
        else:
            log.info("Using injected application instance (test mode).")
            app.state.application = application
        app.state.jobs = jobs or JobStore(concurrency=1)
        try:
            yield
        finally:
            log.info("Agent shutting down.")

    return lifespan


def create_app(
    *,
    application: AgentApplication | None = None,
    config: AgentConfig | None = None,
    jobs: JobStore | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    Production: `create_app()` — lifespan loads everything from env.
    Tests: pass `application=...` to bypass adapter loading.
    """
    app = FastAPI(
        title="ITSM Agent",
        description=(
            "Local RCA agent. POST a ticket id to /rca/{ticket_id}, then poll "
            "/jobs/{job_id} until status is `succeeded`, then read the report from "
            "/reports/{ticket_id}."
        ),
        lifespan=_make_lifespan(application, config, jobs),
    )

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/ready", response_model=ReadinessResponse, tags=["meta"])
    async def ready(request: Request) -> ReadinessResponse:
        checks = await _readiness_checks(request.app.state.config)
        return ReadinessResponse(
            ready=all(c.ok for c in checks),
            checks=checks,
        )

    @app.get("/tickets", response_model=list[TicketSummary], tags=["tickets"])
    async def list_tickets(request: Request) -> list[TicketSummary]:
        application: AgentApplication = request.app.state.application
        ids = await application.list_open_ticket_ids()
        return [TicketSummary(id=tid) for tid in ids]

    @app.post(
        "/rca/{ticket_id}",
        response_model=SubmitJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["rca"],
    )
    async def submit_rca(ticket_id: str, request: Request) -> SubmitJobResponse:
        application: AgentApplication = request.app.state.application
        jobs: JobStore = request.app.state.jobs

        async def work(tid: str) -> tuple[str | None, str | None]:
            response = await application.run_for_ticket(tid)
            return response.report_path, response.error

        job = await jobs.submit(ticket_id, work)
        return SubmitJobResponse(job_id=job.id, ticket_id=job.ticket_id, status=job.status)

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["rca"])
    async def get_job(job_id: str, request: Request) -> JobStatusResponse:
        jobs: JobStore = request.app.state.jobs
        job = await jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return _to_response(job)

    @app.get(
        "/reports/{ticket_id}",
        response_class=PlainTextResponse,
        tags=["rca"],
    )
    async def get_report(ticket_id: str, request: Request) -> PlainTextResponse:
        if not _TICKET_ID_RE.match(ticket_id):
            raise HTTPException(status_code=400, detail="Invalid ticket id")
        config: AgentConfig = request.app.state.config
        out_dir = Path(config.reports.out_dir).resolve()
        path = (out_dir / f"{ticket_id}.md").resolve()
        if not path.is_relative_to(out_dir) or not path.exists():
            raise HTTPException(status_code=404, detail=f"No report yet for {ticket_id}")
        return PlainTextResponse(
            content=path.read_text(encoding="utf-8"),
            media_type="text/markdown",
        )

    return app


# ----- helpers ------------------------------------------------------------


async def _readiness_checks(config: AgentConfig) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        checks.append(await _probe(client, "ollama", f"{config.ollama.base_url}/api/tags"))
        checks.append(await _probe(client, "mcp", config.mcp.server_url))
    return checks


async def _probe(client: httpx.AsyncClient, name: DependencyName, url: str) -> ReadinessCheck:
    try:
        r = await client.get(url)
        # MCP server replies 405/406 to a bare GET; both mean "alive".
        if r.status_code < 500:
            return ReadinessCheck(name=name, ok=True)
        return ReadinessCheck(name=name, ok=False, detail=f"HTTP {r.status_code}")
    except Exception as exc:
        return ReadinessCheck(name=name, ok=False, detail=str(exc))


# Module-level instance so `uvicorn itsm_agent.interfaces.rest:app` works.
app = create_app()
