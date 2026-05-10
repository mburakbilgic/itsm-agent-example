from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama


class OllamaLlmService:
    """LlmService adapter over `langchain_ollama.ChatOllama`."""

    def __init__(
        self,
        model: str,
        base_url: str,
        temperature: float,
        num_ctx: int,
    ) -> None:
        self._model = model
        self._chat = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=temperature,
            num_ctx=num_ctx,
        )

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(self, system: str, user: str) -> str:
        msg = await self._chat.ainvoke([SystemMessage(system), HumanMessage(user)])
        return msg.content.strip()
