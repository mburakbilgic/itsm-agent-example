from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RcaRequest:
    ticket_id: str


@dataclass(frozen=True, slots=True)
class RcaResponse:
    ticket_id: str
    report_path: str | None
    error: str | None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.report_path is not None
