"""Embedding factory — supports OpenAI, OpenRouter, and any OpenAI-compatible API.

Configuration priority for API key:
  1. EMBEDDING_API_KEY (explicit embedding key)
  2. OPENAI_API_KEY (legacy / direct OpenAI)
  3. OPENROUTER_API_KEY (fallback to OpenRouter)

Configuration for base URL:
  - EMBEDDING_BASE_URL="" → OpenAI default (https://api.openai.com/v1)
  - EMBEDDING_BASE_URL="https://openrouter.ai/api/v1" → OpenRouter
  - Any other OpenAI-compatible endpoint
"""

import logging

from langchain_openai import OpenAIEmbeddings

from config.settings import settings

logger = logging.getLogger(__name__)


def get_embeddings() -> OpenAIEmbeddings:
    """Create an OpenAIEmbeddings instance based on settings."""
    # Resolve API key with fallback chain
    api_key = (
        settings.EMBEDDING_API_KEY
        or settings.OPENAI_API_KEY
        or settings.OPENROUTER_API_KEY
    )

    if not api_key:
        raise ValueError(
            "Embedding API key not configured. "
            "Set EMBEDDING_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY in .env"
        )

    kwargs: dict = {
        "model": settings.EMBEDDING_MODEL,
        "api_key": api_key,
    }

    # Only set base_url if explicitly configured (otherwise use OpenAI default)
    if settings.EMBEDDING_BASE_URL:
        kwargs["base_url"] = settings.EMBEDDING_BASE_URL
        logger.info(
            f"Embedding: model={settings.EMBEDDING_MODEL}, "
            f"base_url={settings.EMBEDDING_BASE_URL}"
        )
    else:
        logger.info(f"Embedding: model={settings.EMBEDDING_MODEL}, provider=OpenAI (default)")

    return OpenAIEmbeddings(**kwargs)
