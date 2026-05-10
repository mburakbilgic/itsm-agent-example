from __future__ import annotations

from pathlib import Path

from itsm_agent.domain.models import RcaReport


class FilesystemReportRepository:
    """ReportRepository that writes Markdown reports to a host directory."""

    def __init__(self, out_dir: Path) -> None:
        self._out_dir = out_dir
        self._out_dir.mkdir(parents=True, exist_ok=True)

    def save(self, report: RcaReport, body: str) -> str:
        path = self._out_dir / f"{report.ticket.id}.md"
        path.write_text(body, encoding="utf-8")
        return str(path)
