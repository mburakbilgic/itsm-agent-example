"""Port interfaces (Protocols). Adapters live in `infrastructure/`."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import RcaReport, TicketBundle
from .value_objects import RetrievedChunk, TicketId


@runtime_checkable
class TicketRepository(Protocol):
    async def fetch_bundle(self, ticket_id: TicketId) -> TicketBundle: ...
    async def list_open_ticket_ids(self) -> list[TicketId]: ...


@runtime_checkable
class KnowledgeRepository(Protocol):
    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]: ...


@runtime_checkable
class LlmService(Protocol):
    @property
    def model_name(self) -> str: ...

    async def complete(self, system: str, user: str) -> str: ...


@runtime_checkable
class ReportRenderer(Protocol):
    def render(self, report: RcaReport) -> str: ...


@runtime_checkable
class ReportRepository(Protocol):
    def save(self, report: RcaReport, body: str) -> str:
        """Persist the rendered report; return the storage path/URI."""
        ...
