from __future__ import annotations

import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from itsm_agent.domain.models import Comment, HistoryEvent, Priority, Ticket, TicketBundle
from itsm_agent.domain.value_objects import TicketId


def _decode(result: Any) -> Any:
    """MCP tool returns are wrapped as TextContent JSON; decode to native Python."""
    sc = getattr(result, "structuredContent", None)
    if sc is not None:
        if isinstance(sc, dict) and "result" in sc and len(sc) == 1:
            return sc["result"]
        return sc
    content = getattr(result, "content", [])
    if not content:
        return None
    text = getattr(content[0], "text", None)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _to_ticket(raw: dict[str, Any]) -> Ticket:
    return Ticket(
        id=TicketId(raw["id"]),
        title=raw.get("title", ""),
        description=raw.get("description", ""),
        status=raw.get("status", ""),
        priority=Priority.parse(raw.get("priority")),
        category=raw.get("category", "?"),
        service=raw.get("service", "?"),
        environment=raw.get("environment", "?"),
        affected_users=raw.get("affected_users", "?"),
        created_at=raw.get("created_at", "?"),
        logs_excerpt=raw.get("logs_excerpt", ""),
    )


def _to_comments(raw: list[dict[str, Any]]) -> tuple[Comment, ...]:
    return tuple(
        Comment(at=c.get("at", ""), author=c.get("author", ""), body=c.get("body", "")) for c in raw
    )


def _to_history(raw: list[dict[str, Any]]) -> tuple[HistoryEvent, ...]:
    return tuple(
        HistoryEvent(at=h.get("at", ""), event=h.get("event", ""), value=h.get("value"))
        for h in raw
    )


class McpTicketRepository:
    """TicketRepository adapter over an MCP streamable-http server.

    A fresh session per call keeps the agent stateless. For one ticket per
    invocation that's the right trade; under sustained load we'd pool.
    """

    def __init__(self, server_url: str) -> None:
        self._server_url = server_url

    async def fetch_bundle(self, ticket_id: TicketId) -> TicketBundle:
        async with (
            streamablehttp_client(self._server_url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            ticket_res = await session.call_tool("get_ticket", {"ticket_id": str(ticket_id)})
            comments_res = await session.call_tool(
                "get_ticket_comments", {"ticket_id": str(ticket_id)}
            )
            history_res = await session.call_tool(
                "get_ticket_history", {"ticket_id": str(ticket_id)}
            )

        raw_ticket = _decode(ticket_res)
        if not raw_ticket:
            raise LookupError(f"Ticket {ticket_id} not found")
        return TicketBundle(
            ticket=_to_ticket(raw_ticket),
            comments=_to_comments(_decode(comments_res) or []),
            history=_to_history(_decode(history_res) or []),
        )

    async def list_open_ticket_ids(self) -> list[TicketId]:
        async with (
            streamablehttp_client(self._server_url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            res = await session.call_tool("list_tickets", {"status": "open"})
        decoded = _decode(res) or []
        return [TicketId(t["id"]) for t in decoded]
