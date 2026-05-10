"""Domain layer — pure business types, no framework dependencies."""

from itsm_agent.domain.models import (
    Comment,
    HistoryEvent,
    Priority,
    RcaReport,
    Ticket,
    TicketBundle,
)
from itsm_agent.domain.ports import (
    KnowledgeRepository,
    LlmService,
    ReportRenderer,
    ReportRepository,
    TicketRepository,
)
from itsm_agent.domain.services import RetrievalQueryBuilder
from itsm_agent.domain.value_objects import KbReference, RetrievedChunk, TicketId

__all__ = [
    "Comment",
    "HistoryEvent",
    "KbReference",
    "KnowledgeRepository",
    "LlmService",
    "Priority",
    "RcaReport",
    "ReportRenderer",
    "ReportRepository",
    "RetrievalQueryBuilder",
    "RetrievedChunk",
    "Ticket",
    "TicketBundle",
    "TicketId",
    "TicketRepository",
]
