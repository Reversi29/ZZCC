"""
Cache service — Redis.
Provides: connection, health check, TTL cache helpers.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from config import get_settings

_log = logging.getLogger(__name__)

try:
    import redis.asyncio as redis

    _REDIS_OK = True
except ImportError:
    _REDIS_OK = False

_pool: "redis.ConnectionPool | None" = None


def _pool_factory() -> "redis.ConnectionPool":
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = redis.ConnectionPool.from_url(
            settings.redis.url,
            decode_responses=True,
            max_connections=20,
        )
    return _pool


async def get_redis() -> "redis.Redis":
    """Get an async Redis client."""
    if not _REDIS_OK:
        raise RuntimeError("redis package not installed")
    pool = _pool_factory()
    return redis.Redis(connection_pool=pool)


async def health_check() -> dict:
    """Return status dict: {'status': 'ok'|'degraded', 'detail': ...}."""
    if not _REDIS_OK:
        _log.error("redis_health_check_skipped", reason="redis package not installed")
        return {"status": "degraded", "detail": "redis package not installed"}
    try:
        client = await get_redis()
        await client.ping()
        await client.aclose()
        return {"status": "ok"}
    except Exception as exc:
        _log.error("redis_health_check_failed", reason=str(exc))
        return {"status": "degraded", "detail": str(exc)}


async def cache_get(key: str) -> Optional[Any]:
    """Get and deserialize a cached value."""
    if not _REDIS_OK:
        return None
    try:
        client = await get_redis()
        val = await client.get(key)
        await client.aclose()
        if val is None:
            return None
        return json.loads(val)
    except Exception:
        return None


async def cache_set(
    key: str,
    value: Any,
    ttl_seconds: int = 300,
) -> bool:
    """Serialize and cache a value with TTL."""
    if not _REDIS_OK:
        return False
    try:
        client = await get_redis()
        await client.set(key, json.dumps(value), ex=ttl_seconds)
        await client.aclose()
        return True
    except Exception as exc:
        _log.warning("cache_set_fail", key=key, error=str(exc))
        return False


async def cache_delete(key: str) -> bool:
    """Delete a cache key."""
    if not _REDIS_OK:
        return False
    try:
        client = await get_redis()
        await client.delete(key)
        await client.aclose()
        return True
    except Exception:
        return False
