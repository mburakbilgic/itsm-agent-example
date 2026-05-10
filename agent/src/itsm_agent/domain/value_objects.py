from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TicketId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("TicketId cannot be empty")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    doc_id: str
    source: str
    section: str
    text: str
    score: float


@dataclass(frozen=True, slots=True)
class KbReference:
    source: str
    section: str
    score: float
