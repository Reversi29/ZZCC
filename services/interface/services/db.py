"""
KnowledgeTable database service — Postgres + SQLAlchemy.
Provides async DB access for metadata, audit logs, etc.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

try:
    import greenlet
    _GREENLET_OK = True
except ImportError:
    _GREENLET_OK = False

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import get_settings

_log = logging.getLogger(__name__)

_engine: async_sessionmaker[AsyncSession] | None = None


def _engine_factory() -> async_sessionmaker[AsyncSession]:
    global _engine
    if _engine is None:
        settings = get_settings()
        dsn = settings.database.dsn.replace("postgresql://", "postgresql+asyncpg://")
        _engine = async_sessionmaker(
            bind=create_async_engine(dsn, echo=settings.debug, pool_pre_ping=True),
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency — yields an async SQLAlchemy session, auto-closes."""
    factory = _engine_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def managed_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager version — use outside of Depends()."""
    factory = _engine_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def health_check() -> dict:
    """Return status dict: {'status': 'ok'|'degraded', 'detail': ...}."""
    if not _GREENLET_OK:
        _log.error("postgres_health_check_skipped", reason="greenlet not installed")
        return {"status": "degraded", "detail": "greenlet not installed"}
    try:
        async with managed_session() as sess:
            await sess.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        _log.error("postgres_health_check_failed", reason=str(exc))
        return {"status": "degraded", "detail": str(exc)}


async def log_audit(
    *,
    actor: str,
    action: str,
    resource: str,
    detail: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Write an audit entry. Returns True on success, False on failure.
    Requires table: CREATE TABLE IF NOT EXISTS audit_log (
        id BIGSERIAL PRIMARY KEY,
        actor TEXT, action TEXT, resource TEXT,
        detail JSONB, created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    if not _GREENLET_OK:
        _log.error("audit_log_skipped", reason="greenlet not installed")
        return False
    try:
        async with managed_session() as sess:
            sql = text(
                "INSERT INTO audit_log (actor, action, resource, detail) "
                "VALUES (:actor, :action, :resource, :detail)"
            )
            await sess.execute(sql, {
                "actor": actor,
                "action": action,
                "resource": resource,
                "detail": detail,
            })
            await sess.commit()
        return True
    except Exception as exc:
        _log.error("audit_log_failed", actor=actor, action=action, resource=resource, error=str(exc))
        return False
