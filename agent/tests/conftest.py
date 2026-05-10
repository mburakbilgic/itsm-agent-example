"""Shared pytest fixtures and in-memory fakes for every port.

The fakes live here (not in `src/`) because they exist for tests only.
Each one implements the corresponding `Protocol` from `itsm_agent.domain.ports`
so the Builder's `with_custom_*` slots can accept them directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from itsm_agent.domain.models import (
    Comment,
    HistoryEvent,
    Priority,
    RcaReport,
    Ticket,
    TicketBundle,
)
from itsm_agent.domain.value_objects import KbReference, RetrievedChunk, TicketId

# ----- Sample data --------------------------------------------------------


def _sample_ticket(ticket_id: str = "INC-9001") -> Ticket:
    return Ticket(
        id=TicketId(ticket_id),
        title="DB lock contention on orders service",
        description="Orders API responding 5xx; lock waits spiking.",
        status="open",
        priority=Priority.P1,
        category="database",
        service="orders-api",
        environment="production",
        affected_users=1200,
        created_at="2026-05-07T08:00:00Z",
        logs_excerpt="ERROR: deadlock detected on relation orders_pkey",
    )


def _sample_bundle(ticket_id: str = "INC-9001") -> TicketBundle:
    return TicketBundle(
        ticket=_sample_ticket(ticket_id),
        comments=(Comment(at="2026-05-07T08:05Z", author="oncall", body="Saw spike at 08:02"),),
        history=(
            HistoryEvent(at="2026-05-07T08:00Z", event="created"),
            HistoryEvent(at="2026-05-07T08:03Z", event="priority_changed", value="P1"),
        ),
    )


def _sample_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            doc_id="kb_02::00",
            source="kb_02_db_lock_contention.md",
            section="Symptoms",
            text="Repeated lock waits indicate ...",
            score=0.91,
        ),
        RetrievedChunk(
            doc_id="kb_02::01",
            source="kb_02_db_lock_contention.md",
            section="Mitigation",
            text="Identify the blocking transaction with pg_stat_activity ...",
            score=0.88,
        ),
    ]


@pytest.fixture
def sample_ticket() -> Ticket:
    return _sample_ticket()


@pytest.fixture
def sample_bundle() -> TicketBundle:
    return _sample_bundle()


@pytest.fixture
def sample_chunks() -> list[RetrievedChunk]:
    return _sample_chunks()


@pytest.fixture
def sample_report(sample_ticket: Ticket) -> RcaReport:
    return RcaReport(
        ticket=sample_ticket,
        comments=(Comment(at="2026-05-07T08:05Z", author="oncall", body="hi"),),
        history=(),
        analysis="### Most Likely Root Cause\nLock contention on orders_pkey.\n",
        remediation="### Immediate Mitigation\n1. Cancel blocker.\n",
        references=(
            KbReference(source="kb_02_db_lock_contention.md", section="Mitigation", score=0.88),
        ),
        generated_at=datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC),
        model_name="qwen2.5:3b",
        chunk_count=2,
    )


# ----- Fakes --------------------------------------------------------------


class FakeTicketRepository:
    """In-memory TicketRepository.

    `bundles` keyed by string ticket id. `list_open_ticket_ids()` returns
    every key in insertion order. Raise LookupError on miss to mirror the
    real adapter.
    """

    def __init__(self, bundles: dict[str, TicketBundle] | None = None) -> None:
        self.bundles: dict[str, TicketBundle] = bundles or {}
        self.fetch_calls: list[str] = []
        self.list_calls: int = 0

    async def fetch_bundle(self, ticket_id: TicketId) -> TicketBundle:
        self.fetch_calls.append(str(ticket_id))
        bundle = self.bundles.get(str(ticket_id))
        if bundle is None:
            raise LookupError(f"Ticket {ticket_id} not found")
        return bundle

    async def list_open_ticket_ids(self) -> list[TicketId]:
        self.list_calls += 1
        return [TicketId(k) for k in self.bundles]


class FakeKnowledgeRepository:
    """Returns a pre-seeded list of chunks regardless of query."""

    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        self.calls.append((query, top_k))
        return list(self.chunks[:top_k])


class FakeLlmService:
    """Returns canned responses; records every (system, user) prompt pair."""

    model_name = "fake-llm-1.0"

    def __init__(
        self,
        analysis: str = "### Most Likely Root Cause\nfake analysis.\n",
        remediation: str = "### Immediate Mitigation\n1. Fake step.\n",
    ) -> None:
        self.analysis = analysis
        self.remediation = remediation
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        # Heuristic: which prompt template is in play.
        if "Remediation" in user or "Remediation" in system:
            return self.remediation
        return self.analysis


class FakeReportRenderer:
    """Echoes the rendered marker so tests can assert pipeline routing."""

    def __init__(self, body: str = "RENDERED-BODY") -> None:
        self.body = body
        self.calls: list[RcaReport] = []

    def render(self, report: RcaReport) -> str:
        self.calls.append(report)
        return self.body


class FakeReportRepository:
    """Stores last save in memory; returns a deterministic 'path'."""

    def __init__(self) -> None:
        self.saved: list[tuple[RcaReport, str]] = []

    def save(self, report: RcaReport, body: str) -> str:
        self.saved.append((report, body))
        return f"/fake/reports/{report.ticket.id}.md"


class TmpFileReportRepository:
    """Writes to a tmp directory — useful when a test wants real bytes on disk."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, report: RcaReport, body: str) -> str:
        out = self._root / f"{report.ticket.id}.md"
        out.write_text(body, encoding="utf-8")
        return str(out)


# ----- Factory fixtures ---------------------------------------------------


@pytest.fixture
def fake_tickets(sample_bundle: TicketBundle) -> FakeTicketRepository:
    return FakeTicketRepository({str(sample_bundle.ticket.id): sample_bundle})


@pytest.fixture
def fake_kb(sample_chunks: list[RetrievedChunk]) -> FakeKnowledgeRepository:
    return FakeKnowledgeRepository(sample_chunks)


@pytest.fixture
def fake_llm() -> FakeLlmService:
    return FakeLlmService()


@pytest.fixture
def fake_renderer() -> FakeReportRenderer:
    return FakeReportRenderer()


@pytest.fixture
def fake_reports() -> FakeReportRepository:
    return FakeReportRepository()
