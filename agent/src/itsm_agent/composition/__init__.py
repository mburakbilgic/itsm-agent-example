"""Composition root — wires domain + application + infrastructure via Builder."""

from itsm_agent.composition.builder import (
    AgentApplication,
    AgentBuilder,
    BuilderError,
    build_default_application,
)
from itsm_agent.composition.config import (
    AgentConfig,
    McpConfig,
    OllamaConfig,
    RagConfig,
    ReportsConfig,
)

__all__ = [
    "AgentApplication",
    "AgentBuilder",
    "AgentConfig",
    "BuilderError",
    "McpConfig",
    "OllamaConfig",
    "RagConfig",
    "ReportsConfig",
    "build_default_application",
]
