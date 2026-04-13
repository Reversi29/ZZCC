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
_session_factory: async_sessionmaker[AsyncSession] | None = None


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


def _session_factory_fn() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = _engine_factory()
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency — yields an async SQLAlchemy session, auto-closes."""
    factory = _session_factory_fn()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def managed_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager version — use outside of Depends()."""
    factory = _session_factory_fn()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def health_check() -> str:
    """Return 'ok' if Postgres is reachable, else error message."""
    if not _GREENLET_OK:
        return "greenlet not installed"
    try:
        async with managed_session() as sess:
            await sess.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        _log.warning("postgres_health_fail", error=str(exc))
        return f"error: {exc}"


async def log_audit(
    *,
    actor: str,
    action: str,
    resource: str,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write an audit entry. Requires:
    CREATE TABLE IF NOT EXISTS audit_log (
        id BIGSERIAL PRIMARY KEY,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        resource TEXT NOT NULL,
        detail JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    if not _GREENLET_OK:
        return
    try:
        async with managed_session() as sess:
            await sess.execute(
                text("""
                    INSERT INTO audit_log (actor, action, resource, detail)
                    VALUES (:actor, :action, :resource, :detail)
                """),
                {
                    "actor": actor,
                    "action": action,
                    "resource": resource,
                    "detail": detail,
                },
            )
            await sess.commit()
    except Exception as exc:
        _log.warning("audit_log_fail", error=str(exc))
