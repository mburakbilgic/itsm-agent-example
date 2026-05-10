from __future__ import annotations

from itsm_agent.infrastructure.rag.markdown_chunker import MarkdownChunker


def test_splits_by_h2_headings():
    text = (
        "# Title\n"
        "Intro under the H1.\n"
        "## First\n"
        "body of first\n"
        "## Second\n"
        "body of second\n"
    )
    out = MarkdownChunker().split(text)
    assert [s for s, _ in out] == ["Title", "First", "Second"]
    # First chunk's body includes the H1 line itself plus the intro paragraph;
    # this is intentional so the LLM still sees the document title.
    assert out[0][1] == "# Title\nIntro under the H1."
    assert out[1][1] == "body of first"
    assert out[2][1] == "body of second"


def test_uses_overview_when_no_h1():
    text = "## Lonely\nbody\n"
    out = MarkdownChunker().split(text)
    # No H1 line means the leading bucket is "Overview", but it's empty so it's
    # pruned and only the H2 section survives.
    assert [s for s, _ in out] == ["Lonely"]


def test_keeps_h1_section_when_it_carries_body():
    text = "# Title\n\n## Empty\n\n## Real\nactual content\n"
    out = MarkdownChunker().split(text)
    # H1 line counts as body, so the title section is kept; the empty H2
    # is dropped because its body is whitespace-only.
    assert [s for s, _ in out] == ["Title", "Real"]


def test_handles_no_headings_at_all():
    text = "just some prose with no markers"
    out = MarkdownChunker().split(text)
    assert out == [("Overview", "just some prose with no markers")]
