"""Embedding factory — supports OpenAI, OpenRouter, and any OpenAI-compatible API.

Configuration priority for API key:
  1. EMBEDDING_API_KEY (explicit embedding key)
  2. OPENAI_API_KEY (legacy / direct OpenAI)
  3. OPENROUTER_API_KEY (fallback to OpenRouter)

Configuration for base URL:
  - EMBEDDING_BASE_URL="" → OpenAI default (https://api.openai.com/v1)
  - EMBEDDING_BASE_URL="https://openrouter.ai/api/v1" → OpenRouter
  - Any other OpenAI-compatible endpoint

When Redis is available, embed_query and embed_documents are cached via LangChain
CacheBackedEmbeddings + RedisStore to reduce API calls.
"""

import logging

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_community.storage import RedisStore

from langchain_classic.embeddings import CacheBackedEmbeddings
from config.settings import settings
from services.cache_service import REDIS_AVAILABLE

logger = logging.getLogger(__name__)


def _create_openai_embeddings() -> OpenAIEmbeddings:
    """Create a raw OpenAIEmbeddings instance (no cache)."""
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
    if settings.EMBEDDING_BASE_URL:
        kwargs["base_url"] = settings.EMBEDDING_BASE_URL
        logger.info(
            "Embedding: model=%s, base_url=%s",
            settings.EMBEDDING_MODEL,
            settings.EMBEDDING_BASE_URL,
        )
    else:
        logger.info("Embedding: model=%s, provider=OpenAI (default)", settings.EMBEDDING_MODEL)
    return OpenAIEmbeddings(**kwargs)


def get_embeddings(use_cache: bool = True) -> Embeddings:
    """Return embeddings; when use_cache=True and Redis is available, wrap with CacheBackedEmbeddings."""
    raw = _create_openai_embeddings()
    if not use_cache or not REDIS_AVAILABLE:
        return raw
    try:
        redis_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
        store = RedisStore(
            redis_url=redis_url,
            ttl=settings.CACHE_TTL_EMBEDDING,
            namespace=f"emb:{settings.EMBEDDING_MODEL}",
        )
        return CacheBackedEmbeddings.from_bytes_store(
            underlying_embeddings=raw,
            document_embedding_cache=store,
            namespace=settings.EMBEDDING_MODEL,
            query_embedding_cache=True,
        )
    except Exception as e:
        logger.warning("Embedding Redis cache disabled: %s", e)
        return raw
