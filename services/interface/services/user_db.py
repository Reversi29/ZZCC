"""
ChatUser DB service — reuses KT_DB Postgres engine.
Provides async DB access for chat users, messages, rooms.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.db import _engine_factory, get_session, managed_session, _GREENLET_OK

_log = logging.getLogger(__name__)


async def health_check() -> dict:
    try:
        async with managed_session() as sess:
            await sess.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        _log.error("chat_db_health_check_failed: %s", exc)
        return {"status": "degraded", "detail": str(exc)}


async def execute(sql: str, params: Optional[dict] = None) -> int:
    async with managed_session() as sess:
        result = await sess.execute(text(sql), params or {})
        await sess.commit()
        return result.rowcount or 0


async def fetch_one(sql: str, params: Optional[dict] = None) -> Optional[dict]:
    async with managed_session() as sess:
        result = await sess.execute(text(sql), params or {})
        row = result.mappings().first()
        return dict(row) if row else None


async def fetch_all(sql: str, params: Optional[dict] = None) -> list[dict]:
    async with managed_session() as sess:
        result = await sess.execute(text(sql), params or {})
        return [dict(r) for r in result.mappings()]


_CREATE_USER_TABLE = """
CREATE TABLE IF NOT EXISTS chat_user (
    id UUID PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    display_name VARCHAR(128),
    password_hash VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(32),
    avatar_url TEXT,
    matrix_user_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    sync_status VARCHAR(16) NOT NULL DEFAULT 'local',
    client_uid VARCHAR(64) UNIQUE
)
"""

_CREATE_BINDING_TABLE = """
CREATE TABLE IF NOT EXISTS chat_identity_binding (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    binding_type VARCHAR(16) NOT NULL,
    binding_value VARCHAR(255) NOT NULL,
    verified_at TIMESTAMPTZ,
    verified_method VARCHAR(16),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(binding_type, binding_value)
)
"""

_CREATE_ROOM_TABLE = """
CREATE TABLE IF NOT EXISTS chat_room (
    id UUID PRIMARY KEY,
    name VARCHAR(128),
    description TEXT,
    room_type VARCHAR(16) NOT NULL DEFAULT 'private',
    owner_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
)
"""

_CREATE_ROOM_MEMBER_TABLE = """
CREATE TABLE IF NOT EXISTS chat_room_member (
    room_id UUID NOT NULL,
    user_id UUID NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'member',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_read_at TIMESTAMPTZ,
    PRIMARY KEY(room_id, user_id)
)
"""

_CREATE_MESSAGE_TABLE = """
CREATE TABLE IF NOT EXISTS chat_message (
    id BIGSERIAL PRIMARY KEY,
    room_id UUID NOT NULL,
    sender_id UUID NOT NULL,
    content TEXT NOT NULL,
    msg_type VARCHAR(16) NOT NULL DEFAULT 'text',
    client_msg_id VARCHAR(64) UNIQUE,
    server_msg_id VARCHAR(64) UNIQUE,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    reply_to_id BIGINT
)
"""

_CREATE_AUDIT_LOG = """
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor TEXT,
    action TEXT,
    resource TEXT,
    detail JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_chat_user_client_uid ON chat_user(client_uid)",
    "CREATE INDEX IF NOT EXISTS idx_chat_user_email ON chat_user(email)",
    "CREATE INDEX IF NOT EXISTS idx_chat_user_phone ON chat_user(phone)",
    "CREATE INDEX IF NOT EXISTS idx_chat_message_room_time ON chat_message(room_id, sent_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chat_room_member_user ON chat_room_member(user_id)",
]


async def init_schema() -> bool:
    """Create chat tables if missing. Idempotent."""
    if not _GREENLET_OK:
        _log.error("chat_db_init_skipped: greenlet not installed")
        return False
    try:
        async with managed_session() as sess:
            for stmt in (
                _CREATE_USER_TABLE,
                _CREATE_BINDING_TABLE,
                _CREATE_ROOM_TABLE,
                _CREATE_ROOM_MEMBER_TABLE,
                _CREATE_MESSAGE_TABLE,
                _CREATE_AUDIT_LOG,
            ):
                await sess.execute(text(stmt))
            await sess.commit()
            for stmt in _CREATE_INDEXES:
                await sess.execute(text(stmt))
            await sess.commit()
        _log.info("chat_db_schema_ensured")
        return True
    except Exception as exc:
        _log.error("chat_db_schema_ensure_failed: %s", exc)
        return False
