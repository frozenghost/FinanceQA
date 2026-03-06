"""Embedding factory — supports OpenAI, OpenRouter, and any OpenAI-compatible API.

Configuration priority for API key:
  1. EMBEDDING_API_KEY (explicit embedding key)
  2. OPENAI_API_KEY (legacy / direct OpenAI)
  3. OPENROUTER_API_KEY (fallback to OpenRouter)

Configuration for base URL:
  - EMBEDDING_BASE_URL="" → OpenAI default (https://api.openai.com/v1)
  - EMBEDDING_BASE_URL="https://openrouter.ai/api/v1" → OpenRouter
  - Any other OpenAI-compatible endpoint

When Redis is available, embed_query and embed_documents are cached to reduce API calls.
"""

import hashlib
import json
import logging

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from config.settings import settings
from services.cache_service import REDIS_AVAILABLE, get_redis

logger = logging.getLogger(__name__)

EMBED_CACHE_PREFIX = "emb"
EMBED_KEY_HASH_LEN = 16


class CachedEmbeddings(Embeddings):
    """Wraps an Embeddings instance and caches results in Redis."""

    def __init__(self, underlying: Embeddings, model_name: str, ttl: int):
        self._underlying = underlying
        self._model_name = model_name
        self._ttl = ttl

    def _key(self, input_str: str) -> str:
        h = hashlib.md5(input_str.encode()).hexdigest()[:EMBED_KEY_HASH_LEN]
        return f"{EMBED_CACHE_PREFIX}:{self._model_name}:{h}"

    def embed_query(self, text: str) -> list[float]:
        r = get_redis()
        if REDIS_AVAILABLE and r is not None:
            key = self._key(text)
            try:
                if cached := r.get(key):
                    return json.loads(cached)
            except Exception as e:
                logger.warning("Embedding cache read error: %s", e)
        result = self._underlying.embed_query(text)
        if REDIS_AVAILABLE and r is not None:
            try:
                r.setex(key, self._ttl, json.dumps(result))
            except Exception as e:
                logger.warning("Embedding cache write error: %s", e)
        return result

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        r = get_redis()
        raw = json.dumps(texts, sort_keys=True)
        if REDIS_AVAILABLE and r is not None:
            key = self._key(raw)
            try:
                if cached := r.get(key):
                    return json.loads(cached)
            except Exception as e:
                logger.warning("Embedding cache read error: %s", e)
        result = self._underlying.embed_documents(texts)
        if REDIS_AVAILABLE and r is not None:
            try:
                r.setex(key, self._ttl, json.dumps(result))
            except Exception as e:
                logger.warning("Embedding cache write error: %s", e)
        return result


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


def get_embeddings() -> Embeddings:
    """Return embeddings with Redis cache when available. Uses CACHE_TTL_EMBEDDING for TTL."""
    raw = _create_openai_embeddings()
    return CachedEmbeddings(
        raw,
        model_name=settings.EMBEDDING_MODEL,
        ttl=settings.CACHE_TTL_EMBEDDING,
    )
