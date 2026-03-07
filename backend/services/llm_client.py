"""OpenRouter LLM client. Reuses the openai SDK with a custom base_url."""

from typing import Optional

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from config.models import MODEL_ROUTING
from config.settings import settings


class LLMClient:
    """Unified LLM gateway through OpenRouter."""

    def __init__(self):
        self._async_client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )

    def get_langchain_model(self, role: str = "market_analyst") -> ChatOpenAI:
        """Return a LangChain-compatible ChatOpenAI instance for LangGraph Agent."""
        model = MODEL_ROUTING.get(role, MODEL_ROUTING["market_analyst"])
        return ChatOpenAI(
            model=model,
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            streaming=True,
            default_headers={
                "HTTP-Referer": settings.APP_URL,
                "X-Title": "Finance QA System",
            },
        )

    async def chat_raw(
        self,
        messages: list,
        model: Optional[str] = None,
        stream: bool = True,
    ):
        """Direct call for non-Agent scenarios like router classification."""
        return await self._async_client.chat.completions.create(
            model=model or MODEL_ROUTING["router"],
            messages=messages,
            stream=stream,
        )


# Singleton instance
llm_client = LLMClient()
