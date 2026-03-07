"""Redis cache layer with graceful degradation.

When Redis is unavailable the decorator transparently falls through
to the wrapped function so the main data path is never blocked.
"""

import asyncio
import functools
import hashlib
import json
import logging
from typing import Optional

import redis

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Redis connection (fail-open) ──────────────────────────────
try:
    _r: Optional[redis.Redis] = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=2,
    )
    _r.ping()
    REDIS_AVAILABLE = True
    logger.info("Redis connected")
except Exception:
    logger.warning("Redis unavailable; cache layer degraded to direct mode")
    _r = None
    REDIS_AVAILABLE = False


def get_redis() -> Optional[redis.Redis]:
    """Return the shared Redis client for use by other modules (e.g. embedding cache)."""
    return _r


def cached(key_prefix: str, ttl: int):
    """
    Universal cache decorator supporting both sync and async functions.

    - Redis available: cache hit → return cached; miss → compute + store.
    - Redis unavailable: pass-through, main path unaffected.
    """

    def decorator(func):
        is_async = asyncio.iscoroutinefunction(func)
        
        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not REDIS_AVAILABLE or _r is None:
                    return await func(*args, **kwargs)

                raw = json.dumps({"a": args, "k": kwargs}, sort_keys=True, default=str)
                key = f"{key_prefix}:{hashlib.md5(raw.encode()).hexdigest()[:12]}"

                # Try read from cache
                try:
                    if cached_val := _r.get(key):
                        result = json.loads(cached_val)
                        result["_cache"] = {"hit": True, "ttl": _r.ttl(key)}
                        return result
                except redis.RedisError as e:
                    logger.warning(f"Cache read error: {e}")

                # Compute
                result = await func(*args, **kwargs)

                # Try write to cache
                try:
                    _r.setex(key, ttl, json.dumps(result, default=str))
                    result["_cache"] = {"hit": False}
                except redis.RedisError as e:
                    logger.warning(f"Cache write error: {e}")

                return result
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if not REDIS_AVAILABLE or _r is None:
                    return func(*args, **kwargs)

                raw = json.dumps({"a": args, "k": kwargs}, sort_keys=True, default=str)
                key = f"{key_prefix}:{hashlib.md5(raw.encode()).hexdigest()[:12]}"

                # Try read from cache
                try:
                    if cached_val := _r.get(key):
                        result = json.loads(cached_val)
                        result["_cache"] = {"hit": True, "ttl": _r.ttl(key)}
                        return result
                except redis.RedisError as e:
                    logger.warning(f"Cache read error: {e}")

                # Compute
                result = func(*args, **kwargs)

                # Try write to cache
                try:
                    _r.setex(key, ttl, json.dumps(result, default=str))
                    result["_cache"] = {"hit": False}
                except redis.RedisError as e:
                    logger.warning(f"Cache write error: {e}")

                return result

            return wrapper

    return decorator
