"""Domain services — pure logic that doesn't fit on a single entity."""

from __future__ import annotations

from .models import Comment, Ticket


class RetrievalQueryBuilder:
    """Builds the free-text query used to retrieve KB chunks for a ticket.

    Pulled out as its own object so the strategy (which fields, in which
    order, with what weighting) can evolve without touching the pipeline.
    """

    def build(self, ticket: Ticket, comments: tuple[Comment, ...]) -> str:
        parts = [
            ticket.title,
            ticket.description,
            ticket.logs_excerpt,
            " ".join(c.body for c in comments),
        ]
        return "\n".join(p for p in parts if p)
