from __future__ import annotations

import logging

from itsm_agent.application.dto import RcaRequest, RcaResponse
from itsm_agent.application.pipeline import AgentPipeline
from itsm_agent.domain.ports import TicketRepository

log = logging.getLogger(__name__)


class GenerateRcaUseCase:
    """Run the pipeline for a single ticket and return a structured response."""

    def __init__(self, pipeline: AgentPipeline) -> None:
        self._pipeline = pipeline

    async def execute(self, request: RcaRequest) -> RcaResponse:
        state = await self._pipeline.run(request.ticket_id)
        if state.get("error"):
            return RcaResponse(
                ticket_id=request.ticket_id,
                report_path=None,
                error=state["error"],
            )
        return RcaResponse(
            ticket_id=request.ticket_id,
            report_path=state.get("report_path"),
            error=None,
        )


class BatchGenerateRcaUseCase:
    """Discover open tickets via the repository and run GenerateRca for each."""

    def __init__(
        self,
        single: GenerateRcaUseCase,
        tickets: TicketRepository,
    ) -> None:
        self._single = single
        self._tickets = tickets

    async def execute(self) -> list[RcaResponse]:
        ids = await self._tickets.list_open_ticket_ids()
        if not ids:
            log.warning("No open tickets returned by repository.")
            return []
        responses: list[RcaResponse] = []
        for tid in ids:
            res = await self._single.execute(RcaRequest(ticket_id=str(tid)))
            responses.append(res)
        return responses
