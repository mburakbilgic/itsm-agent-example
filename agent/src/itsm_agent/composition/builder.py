"""Composition root — fluent Builder that wires every layer together."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from itsm_agent.application.dto import RcaRequest, RcaResponse
from itsm_agent.application.pipeline import AgentPipeline, PipelineDependencies
from itsm_agent.application.use_cases import BatchGenerateRcaUseCase, GenerateRcaUseCase
from itsm_agent.composition.config import AgentConfig
from itsm_agent.domain.ports import (
    KnowledgeRepository,
    LlmService,
    ReportRenderer,
    ReportRepository,
    TicketRepository,
)
from itsm_agent.domain.services import RetrievalQueryBuilder

log = logging.getLogger(__name__)


class BuilderError(RuntimeError):
    """Raised when `.build()` is called with missing or invalid wiring."""


@dataclass(frozen=True, slots=True)
class AgentApplication:
    """Public façade returned by `AgentBuilder.build()`.

    Exposes only the operations the outer world needs — callers never
    see pipelines, renderers, or framework objects directly.
    """

    generate_one: GenerateRcaUseCase
    generate_all: BatchGenerateRcaUseCase
    tickets: TicketRepository

    async def run_for_ticket(self, ticket_id: str) -> RcaResponse:
        return await self.generate_one.execute(RcaRequest(ticket_id=ticket_id))

    async def run_all(self) -> list[RcaResponse]:
        return await self.generate_all.execute()

    async def list_open_ticket_ids(self) -> list[str]:
        ids = await self.tickets.list_open_ticket_ids()
        return [str(t) for t in ids]


class AgentBuilder:
    """Fluent builder. Each `.with_*` returns self so calls can be chained.

    Defaults are environment-driven via `AgentConfig.from_env()` so a
    `AgentBuilder().with_default_*().build()` chain produces a fully
    wired app from container env vars. Tests can swap any single
    collaborator with `.with_custom_*` overrides.
    """

    def __init__(self) -> None:
        self._config: AgentConfig | None = None
        self._tickets: TicketRepository | None = None
        self._knowledge: KnowledgeRepository | None = None
        self._llm: LlmService | None = None
        self._renderer: ReportRenderer | None = None
        self._reports: ReportRepository | None = None

    # ----- config --------------------------------------------------------

    def with_config(self, config: AgentConfig) -> AgentBuilder:
        self._config = config
        return self

    def with_config_from_env(self) -> AgentBuilder:
        return self.with_config(AgentConfig.from_env())

    # ----- adapters (env-driven defaults) --------------------------------

    def with_default_llm(self) -> AgentBuilder:
        from itsm_agent.infrastructure.llm.ollama_service import OllamaLlmService

        cfg = self._require_config().ollama
        self._llm = OllamaLlmService(
            model=cfg.model,
            base_url=cfg.base_url,
            temperature=cfg.temperature,
            num_ctx=cfg.num_ctx,
        )
        return self

    def with_default_knowledge_base(self) -> AgentBuilder:
        from itsm_agent.infrastructure.rag.chroma_repository import ChromaKnowledgeRepository
        from itsm_agent.infrastructure.rag.e5_embedder import E5Embedder

        cfg = self._require_config().rag
        embedder = E5Embedder(cfg.embedding_model)
        self._knowledge = ChromaKnowledgeRepository(
            kb_dir=cfg.kb_dir,
            persist_dir=cfg.persist_dir,
            embedder=embedder,
            collection=cfg.collection,
        )
        return self

    def with_default_ticket_repository(self) -> AgentBuilder:
        from itsm_agent.infrastructure.mcp.ticket_repository import McpTicketRepository

        cfg = self._require_config().mcp
        self._tickets = McpTicketRepository(server_url=cfg.server_url)
        return self

    def with_default_renderer(self) -> AgentBuilder:
        from itsm_agent.infrastructure.reports.markdown_renderer import MarkdownReportRenderer

        self._renderer = MarkdownReportRenderer()
        return self

    def with_default_report_repository(self) -> AgentBuilder:
        from itsm_agent.infrastructure.reports.filesystem_repository import (
            FilesystemReportRepository,
        )

        cfg = self._require_config().reports
        self._reports = FilesystemReportRepository(out_dir=cfg.out_dir)
        return self

    # ----- adapters (custom overrides for tests / alt implementations) ---

    def with_custom_llm(self, llm: LlmService) -> AgentBuilder:
        self._llm = llm
        return self

    def with_custom_knowledge_base(self, kb: KnowledgeRepository) -> AgentBuilder:
        self._knowledge = kb
        return self

    def with_custom_ticket_repository(self, repo: TicketRepository) -> AgentBuilder:
        self._tickets = repo
        return self

    def with_custom_renderer(self, renderer: ReportRenderer) -> AgentBuilder:
        self._renderer = renderer
        return self

    def with_custom_report_repository(self, repo: ReportRepository) -> AgentBuilder:
        self._reports = repo
        return self

    # ----- final assembly ------------------------------------------------

    def build(self) -> AgentApplication:
        config = self._require_config()
        tickets = self._tickets
        knowledge = self._knowledge
        llm = self._llm
        renderer = self._renderer
        reports = self._reports
        missing = [
            name
            for name, value in (
                ("tickets", tickets),
                ("knowledge", knowledge),
                ("llm", llm),
                ("renderer", renderer),
                ("reports", reports),
            )
            if value is None
        ]
        if (
            missing
            or tickets is None
            or knowledge is None
            or llm is None
            or renderer is None
            or reports is None
        ):
            raise BuilderError(
                "Cannot build application — missing collaborators: " + ", ".join(missing)
            )

        deps = PipelineDependencies(
            tickets=tickets,
            knowledge=knowledge,
            llm=llm,
            renderer=renderer,
            reports=reports,
            query_builder=RetrievalQueryBuilder(),
            top_k=config.rag.top_k,
        )
        pipeline = AgentPipeline(deps)
        single = GenerateRcaUseCase(pipeline)
        batch = BatchGenerateRcaUseCase(single, deps.tickets)
        return AgentApplication(generate_one=single, generate_all=batch, tickets=deps.tickets)

    # ----- internals -----------------------------------------------------

    def _require_config(self) -> AgentConfig:
        if self._config is None:
            raise BuilderError("with_config(...) or with_config_from_env() must be called first")
        return self._config


def build_default_application(config: AgentConfig | None = None) -> AgentApplication:
    """Convenience: env-driven defaults all the way down.

    Pass an explicit `config` to avoid re-reading environment variables when
    the caller has already loaded them (e.g. for logging setup).
    """
    builder = AgentBuilder()
    builder = builder.with_config(config) if config is not None else builder.with_config_from_env()
    return (
        builder.with_default_llm()
        .with_default_knowledge_base()
        .with_default_ticket_repository()
        .with_default_renderer()
        .with_default_report_repository()
        .build()
    )
