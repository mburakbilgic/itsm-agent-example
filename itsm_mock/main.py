"""Mock ITSM REST API.

Serves a small, in-memory dataset of incident tickets so the rest of the
system has something realistic to query. Keep the surface small but rich
enough that the agent can demonstrate fetching, filtering, and analyzing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str) -> Any:
    with (DATA_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


TICKETS: list[dict] = _load("tickets.json")
COMMENTS: dict[str, list[dict]] = _load("comments.json")
HISTORY: dict[str, list[dict]] = _load("history.json")
TICKETS_BY_ID: dict[str, dict] = {t["id"]: t for t in TICKETS}

app = FastAPI(title="Mock ITSM API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "tickets": len(TICKETS)}


@app.get("/tickets")
def list_tickets(status: str | None = None, priority: str | None = None) -> list[dict]:
    items = TICKETS
    if status:
        items = [t for t in items if t["status"] == status]
    if priority:
        items = [t for t in items if t["priority"] == priority]
    return [
        {k: t[k] for k in ("id", "title", "status", "priority", "category", "service", "created_at")}
        for t in items
    ]


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict:
    if ticket_id not in TICKETS_BY_ID:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return TICKETS_BY_ID[ticket_id]


@app.get("/tickets/{ticket_id}/comments")
def get_comments(ticket_id: str) -> list[dict]:
    if ticket_id not in TICKETS_BY_ID:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return COMMENTS.get(ticket_id, [])


@app.get("/tickets/{ticket_id}/history")
def get_history(ticket_id: str) -> list[dict]:
    if ticket_id not in TICKETS_BY_ID:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return HISTORY.get(ticket_id, [])
