"""Markdown formatting helpers shared between LLM prompts and the rendered report.

The same Markdown formatting of comments / history / KB chunks shows up in both
the LLM prompts and the final report body. Centralizing keeps them in lockstep.
"""

from __future__ import annotations

from itsm_agent.domain.models import Comment, HistoryEvent
from itsm_agent.domain.value_objects import RetrievedChunk


def format_comments(comments: tuple[Comment, ...]) -> str:
    if not comments:
        return "(none)"
    return "\n".join(f"- [{c.at}] {c.author}: {c.body}" for c in comments)


def format_history(history: tuple[HistoryEvent, ...]) -> str:
    if not history:
        return "(none)"
    return "\n".join(
        f"- [{h.at}] {h.event}" + (f" → {h.value}" if h.value is not None else "") for h in history
    )


def format_kb_block(chunks: tuple[RetrievedChunk, ...]) -> str:
    if not chunks:
        return "(no relevant runbooks retrieved)"
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(
            f"[{i}] (source: {c.source} — section: {c.section} — score: {c.score})\n{c.text}"
        )
    return "\n\n".join(parts)
