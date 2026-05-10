"""LangGraph-backed pipeline.

Five linear nodes mutate `PipelineState`. Each node delegates the actual
work to a domain port (TicketRepository, KnowledgeRepository, LlmService,
ReportRenderer, ReportRepository); the pipeline owns only orchestration
and short-circuit-on-error logic.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from itsm_agent.application.formatting import format_comments, format_history, format_kb_block
from itsm_agent.application.prompts import (
    ANALYZE_HUMAN,
    ANALYZE_SYSTEM,
    SOLUTION_HUMAN,
    SOLUTION_SYSTEM,
)
from itsm_agent.domain.models import (
    Comment,
    HistoryEvent,
    RcaReport,
    Ticket,
    TicketBundle,
)
from itsm_agent.domain.ports import (
    KnowledgeRepository,
    LlmService,
    ReportRenderer,
    ReportRepository,
    TicketRepository,
)
from itsm_agent.domain.services import RetrievalQueryBuilder
from itsm_agent.domain.value_objects import KbReference, RetrievedChunk, TicketId

log = logging.getLogger(__name__)


class PipelineState(TypedDict, total=False):
    ticket_id: str
    ticket: Ticket
    comments: tuple[Comment, ...]
    history: tuple[HistoryEvent, ...]
    retrieved: tuple[RetrievedChunk, ...]
    analysis: str
    remediation: str
    report_path: str
    error: str


@dataclass(frozen=True)
class PipelineDependencies:
    tickets: TicketRepository
    knowledge: KnowledgeRepository
    llm: LlmService
    renderer: ReportRenderer
    reports: ReportRepository
    query_builder: RetrievalQueryBuilder
    top_k: int


class AgentPipeline:
    """LangGraph compilation of the RCA pipeline. Built once, invoked many."""

    def __init__(self, deps: PipelineDependencies) -> None:
        self._deps = deps
        self._graph = self._build()

    async def run(self, ticket_id: str) -> PipelineState:
        return await self._graph.ainvoke({"ticket_id": ticket_id})

    # ----- node implementations ------------------------------------------

    async def _node_fetch(self, state: PipelineState) -> PipelineState:
        tid = state["ticket_id"]
        log.info("[%s] fetching ticket via MCP", tid)
        try:
            bundle: TicketBundle = await self._deps.tickets.fetch_bundle(TicketId(tid))
        except LookupError as e:
            return {"error": str(e)}
        except Exception as e:
            log.exception("MCP fetch failed for %s", tid)
            return {"error": f"MCP fetch failed: {e}"}
        return {
            "ticket": bundle.ticket,
            "comments": bundle.comments,
            "history": bundle.history,
        }

    async def _node_retrieve(self, state: PipelineState) -> PipelineState:
        if state.get("error"):
            return {}
        ticket = state["ticket"]
        query = self._deps.query_builder.build(ticket, state.get("comments", ()))
        log.info("[%s] RAG retrieve top-%d", ticket.id, self._deps.top_k)
        try:
            chunks = await asyncio.to_thread(self._deps.knowledge.retrieve, query, self._deps.top_k)
        except Exception as e:
            log.exception("RAG retrieve failed for %s", ticket.id)
            return {"error": f"RAG retrieve failed: {e}"}
        return {"retrieved": tuple(chunks)}

    async def _node_analyze(self, state: PipelineState) -> PipelineState:
        if state.get("error"):
            return {}
        ticket = state["ticket"]
        log.info("[%s] LLM analyze", ticket.id)
        prompt = ANALYZE_HUMAN.format(
            ticket_id=str(ticket.id),
            title=ticket.title,
            service=ticket.service,
            environment=ticket.environment,
            priority=ticket.priority.value,
            category=ticket.category,
            affected_users=ticket.affected_users,
            created_at=ticket.created_at,
            description=ticket.description,
            logs_excerpt=ticket.logs_excerpt or "(none)",
            comments_block=format_comments(state.get("comments", ())),
            history_block=format_history(state.get("history", ())),
            kb_block=format_kb_block(state.get("retrieved", ())),
        )
        try:
            analysis = await self._deps.llm.complete(ANALYZE_SYSTEM, prompt)
        except Exception as e:
            log.exception("LLM analyze failed for %s", ticket.id)
            return {"error": f"LLM analyze failed: {e}"}
        return {"analysis": analysis}

    async def _node_propose(self, state: PipelineState) -> PipelineState:
        if state.get("error"):
            return {}
        ticket = state["ticket"]
        log.info("[%s] LLM propose remediation", ticket.id)
        prompt = SOLUTION_HUMAN.format(
            analysis=state.get("analysis", ""),
            kb_block=format_kb_block(state.get("retrieved", ())),
            title=ticket.title,
            description=ticket.description,
            logs_excerpt=ticket.logs_excerpt or "(none)",
        )
        try:
            remediation = await self._deps.llm.complete(SOLUTION_SYSTEM, prompt)
        except Exception as e:
            log.exception("LLM propose failed for %s", ticket.id)
            return {"error": f"LLM propose failed: {e}"}
        return {"remediation": remediation}

    async def _node_write_report(self, state: PipelineState) -> PipelineState:
        if state.get("error"):
            log.error(
                "[%s] aborting report due to error: %s",
                state.get("ticket_id"),
                state["error"],
            )
            return {}
        ticket = state["ticket"]
        retrieved: tuple[RetrievedChunk, ...] = state.get("retrieved", ())
        report = RcaReport(
            ticket=ticket,
            comments=state.get("comments", ()),
            history=state.get("history", ()),
            analysis=state.get("analysis", ""),
            remediation=state.get("remediation", ""),
            references=tuple(
                KbReference(source=c.source, section=c.section, score=c.score) for c in retrieved
            ),
            generated_at=datetime.now(UTC),
            model_name=self._deps.llm.model_name,
            chunk_count=len(retrieved),
        )
        try:
            body = self._deps.renderer.render(report)
            path = self._deps.reports.save(report, body)
        except Exception as e:
            log.exception("Report write failed for %s", ticket.id)
            return {"error": f"Report write failed: {e}"}
        log.info("[%s] wrote %s", ticket.id, path)
        return {"report_path": path}

    # ----- graph composition ---------------------------------------------

    def _build(self) -> Any:
        g = StateGraph(PipelineState)
        g.add_node("fetch_ticket", self._node_fetch)
        g.add_node("retrieve", self._node_retrieve)
        g.add_node("analyze", self._node_analyze)
        g.add_node("propose_solution", self._node_propose)
        g.add_node("write_report", self._node_write_report)
        g.set_entry_point("fetch_ticket")
        g.add_edge("fetch_ticket", "retrieve")
        g.add_edge("retrieve", "analyze")
        g.add_edge("analyze", "propose_solution")
        g.add_edge("propose_solution", "write_report")
        g.add_edge("write_report", END)
        return g.compile()
