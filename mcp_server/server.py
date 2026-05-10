"""MCP server that exposes the mock ITSM REST API as MCP tools.

Transport: streamable-HTTP, so the agent (running in a separate
container) can connect over the docker network. The server is a thin
facade — it performs no business logic of its own.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


class ITSMToolset:
    """Bundles the four MCP tools that proxy the ITSM REST API.

    Holds the shared httpx.Client and registers each method as an MCP
    tool against an injected FastMCP instance. Keeps state and tool
    surface in one cohesive object.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def register(self, mcp: FastMCP) -> None:
        mcp.tool()(self.list_tickets)
        mcp.tool()(self.get_ticket)
        mcp.tool()(self.get_ticket_comments)
        mcp.tool()(self.get_ticket_history)

    def list_tickets(
        self, status: str | None = None, priority: str | None = None
    ) -> list[dict[str, Any]]:
        """List ITSM tickets with optional filters.

        Args:
            status: Optional ticket status filter (e.g., "open", "closed").
            priority: Optional priority filter (e.g., "P1", "P2").

        Returns:
            A list of ticket summaries with id, title, status, priority,
            category, service, created_at.
        """
        params = {k: v for k, v in {"status": status, "priority": priority}.items() if v}
        r = self._client.get("/tickets", params=params)
        r.raise_for_status()
        return r.json()

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        """Fetch the full detail of a single ticket, including description and log excerpts.

        Args:
            ticket_id: The ticket identifier, e.g. "INC-1001".
        """
        r = self._client.get(f"/tickets/{ticket_id}")
        r.raise_for_status()
        return r.json()

    def get_ticket_comments(self, ticket_id: str) -> list[dict[str, Any]]:
        """Return all comments on a ticket in chronological order.

        Args:
            ticket_id: The ticket identifier.
        """
        r = self._client.get(f"/tickets/{ticket_id}/comments")
        r.raise_for_status()
        return r.json()

    def get_ticket_history(self, ticket_id: str) -> list[dict[str, Any]]:
        """Return the audit-log style history of a ticket (creation, priority changes, assignments).

        Args:
            ticket_id: The ticket identifier.
        """
        r = self._client.get(f"/tickets/{ticket_id}/history")
        r.raise_for_status()
        return r.json()


def build_server() -> FastMCP:
    base_url = os.environ.get("ITSM_BASE_URL", "http://itsm-mock:8000")
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8001"))
    timeout = float(os.environ.get("ITSM_HTTP_TIMEOUT", "10.0"))
    mcp = FastMCP("itsm-mcp", host=host, port=port)
    ITSMToolset(base_url=base_url, timeout=timeout).register(mcp)
    return mcp


if __name__ == "__main__":
    build_server().run(transport="streamable-http")
