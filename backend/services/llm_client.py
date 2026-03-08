"""OpenRouter LLM client. Reuses the openai SDK with a custom base_url."""

import logging
from typing import Any, Optional

from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from config.models import MODEL_ROUTING
from config.settings import settings

logger = logging.getLogger(__name__)


def _reasoning_to_str(val: Any) -> str:
    """Convert reasoning payload to string for streaming."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        direct = val.get("text") or val.get("content") or val.get("summary")
        if direct and isinstance(direct, str):
            return direct
        summary_list = val.get("summary")
        if isinstance(summary_list, list):
            return "".join(
                s.get("text", s) if isinstance(s, dict) else str(s) for s in summary_list
            )
        return ""
    return str(val)


def _reasoning_from_delta(delta: Any) -> str:
    """Extract reasoning text from stream delta (OpenRouter uses 'reasoning' / 'reasoning_details')."""
    if delta is None:
        return ""
    if isinstance(delta, dict):
        return (
            _reasoning_to_str(delta.get("reasoning_content"))
            or _reasoning_to_str(delta.get("reasoning"))
            or _reasoning_to_str(delta.get("reasoning_details"))
            or _reasoning_to_str((delta.get("model_extra") or {}).get("reasoning_content"))
        )
    return (
        _reasoning_to_str(getattr(delta, "reasoning_content", None))
        or _reasoning_to_str(getattr(delta, "reasoning", None))
        or _reasoning_to_str(getattr(delta, "reasoning_details", None))
        or _reasoning_to_str((getattr(delta, "model_extra", None) or {}).get("reasoning_content"))
    )


class OpenRouterChatOpenAI(ChatOpenAI):
    """ChatOpenAI that injects reasoning_content from stream delta into additional_kwargs.

    LangChain's ChatOpenAI does not preserve reasoning_content from OpenRouter/DeepSeek/o1.
    This subclass overrides chunk conversion so model thinking is available in stream chunks.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: Any,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        result = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if result is None:
            return None
        choices = chunk.get("choices", []) if isinstance(chunk, dict) else getattr(chunk, "choices", [])
        if not choices:
            return result
        choice = choices[0]
        delta = choice.get("delta") if isinstance(choice, dict) else getattr(choice, "delta", None)

        if delta is not None and not getattr(self, "_reasoning_delta_logged", False):
            delta_keys = list(delta.keys()) if isinstance(delta, dict) else [k for k in dir(delta) if not k.startswith("_")]
            logger.info("[llm] stream delta keys: %s", delta_keys)
            self._reasoning_delta_logged = True

        reasoning = _reasoning_from_delta(delta)
        if reasoning and hasattr(result.message, "additional_kwargs"):
            result.message.additional_kwargs["reasoning_content"] = reasoning
        return result


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
        
        # Check if model supports reasoning (contains thinking models)
        is_thinking_model = any(x in model.lower() for x in ["o1", "o3", "r1", "qwq", "reasoning", "thinking"])
        
        extra_kwargs = {}
        if is_thinking_model:
            # Enable reasoning tokens for thinking models
            extra_kwargs["extra_body"] = {
                "include_reasoning": True
            }
        
        return OpenRouterChatOpenAI(
            model=model,
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            temperature=0.1,
            streaming=True,
            default_headers={
                "HTTP-Referer": settings.APP_URL,
                "X-Title": "Finance QA System",
            },
            **extra_kwargs,
        )

    async def chat_raw(
        self,
        messages: list,
        model: Optional[str] = None,
        stream: bool = True,
    ):
        """Direct call for non-Agent scenarios (e.g. router classification)."""
        return await self._async_client.chat.completions.create(
            model=model or MODEL_ROUTING["market_analyst"],
            messages=messages,
            stream=stream,
            temperature=0.1,
        )


# Singleton instance
llm_client = LLMClient()
