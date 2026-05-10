from __future__ import annotations

from itsm_agent.domain.models import RcaReport
from itsm_agent.infrastructure.reports.markdown_renderer import MarkdownReportRenderer


def test_renders_title_and_metadata(sample_report: RcaReport):
    body = MarkdownReportRenderer().render(sample_report)
    assert body.startswith("# RCA — INC-9001: DB lock contention on orders service\n")
    assert "**Service:** orders-api (production)" in body
    assert "**Priority:** P1" in body
    assert "**Category:** database" in body
    assert "**Affected users:** 1200" in body
    assert "**Generated:** 2026-05-07 12:00:00 UTC" in body


def test_renders_kb_references_block(sample_report: RcaReport):
    body = MarkdownReportRenderer().render(sample_report)
    assert "## Knowledge Base References" in body
    assert "- `kb_02_db_lock_contention.md` § _Mitigation_ (score 0.88)" in body


def test_renders_footer(sample_report: RcaReport):
    body = MarkdownReportRenderer().render(sample_report)
    assert "qwen2.5:3b" in body
    assert "RAG over `2` runbook chunks" in body


def test_uses_placeholder_when_analysis_missing(sample_report: RcaReport):
    blank = RcaReport(
        ticket=sample_report.ticket,
        comments=sample_report.comments,
        history=sample_report.history,
        analysis="",
        remediation="",
        references=sample_report.references,
        generated_at=sample_report.generated_at,
        model_name=sample_report.model_name,
        chunk_count=sample_report.chunk_count,
    )
    body = MarkdownReportRenderer().render(blank)
    assert "_(not generated)_" in body
