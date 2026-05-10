from __future__ import annotations

from itsm_agent.application.formatting import format_comments, format_history
from itsm_agent.domain.models import RcaReport
from itsm_agent.domain.value_objects import KbReference


class MarkdownReportRenderer:
    """ReportRenderer that produces the Markdown body of an RCA report."""

    def render(self, report: RcaReport) -> str:
        ticket = report.ticket
        generated = report.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            f"# RCA — {ticket.id}: {ticket.title}\n"
            "\n"
            f"**Generated:** {generated}\n"
            f"**Service:** {ticket.service} ({ticket.environment})\n"
            f"**Priority:** {ticket.priority.value}  •  "
            f"**Category:** {ticket.category}  •  "
            f"**Affected users:** {ticket.affected_users}\n"
            f"**Created:** {ticket.created_at}\n"
            "\n"
            "## Summary\n"
            f"> {ticket.description.strip()}\n"
            "\n"
            "## Evidence\n"
            "**Log excerpts**\n"
            "```\n"
            f"{ticket.logs_excerpt or '(none)'}\n"
            "```\n"
            "\n"
            "**Operator comments**\n"
            f"{format_comments(report.comments)}\n"
            "\n"
            "**History**\n"
            f"{format_history(report.history)}\n"
            "\n"
            "## Root Cause Analysis\n"
            f"{report.analysis or '_(not generated)_'}\n"
            "\n"
            "## Remediation\n"
            f"{report.remediation or '_(not generated)_'}\n"
            "\n"
            "## Knowledge Base References\n"
            f"{self._format_references(report.references)}\n"
            "\n"
            "---\n"
            f"_This RCA was produced by the local ITSM agent (Ollama `{report.model_name}` "
            f"+ RAG over `{report.chunk_count}` runbook chunks). "
            "All ticket data was fetched through the MCP server._\n"
        )

    @staticmethod
    def _format_references(refs: tuple[KbReference, ...]) -> str:
        if not refs:
            return "_(none retrieved)_"
        return "\n".join(f"- `{r.source}` § _{r.section}_ (score {r.score})" for r in refs)
