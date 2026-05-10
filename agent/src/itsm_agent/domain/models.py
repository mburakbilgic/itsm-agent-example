from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .value_objects import KbReference, TicketId

_log = logging.getLogger(__name__)


class Priority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    UNKNOWN = "?"

    @classmethod
    def parse(cls, raw: str | None) -> Priority:
        if not raw:
            return cls.UNKNOWN
        try:
            return cls(raw.upper())
        except ValueError:
            _log.warning("Unknown priority value %r — falling back to UNKNOWN", raw)
            return cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class Comment:
    at: str
    author: str
    body: str


@dataclass(frozen=True, slots=True)
class HistoryEvent:
    at: str
    event: str
    value: str | None = None


@dataclass(frozen=True, slots=True)
class Ticket:
    id: TicketId
    title: str
    description: str
    status: str
    priority: Priority
    category: str
    service: str
    environment: str
    affected_users: int | str
    created_at: str
    logs_excerpt: str = ""

    @property
    def is_high_priority(self) -> bool:
        return self.priority in (Priority.P1, Priority.P2)


@dataclass(frozen=True, slots=True)
class TicketBundle:
    """Aggregate exposed by TicketRepository — ticket + its evidence."""

    ticket: Ticket
    comments: tuple[Comment, ...]
    history: tuple[HistoryEvent, ...]


@dataclass(frozen=True, slots=True)
class RcaReport:
    """Output aggregate. The renderer turns this into Markdown bytes."""

    ticket: Ticket
    comments: tuple[Comment, ...]
    history: tuple[HistoryEvent, ...]
    analysis: str
    remediation: str
    references: tuple[KbReference, ...]
    generated_at: datetime
    model_name: str
    chunk_count: int
