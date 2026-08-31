"""
/auth/* — user authentication endpoints (register / login / reset).
Offline-first: local account creation always works; server login validates hash.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import text

from models.user_models import (
    ChatUserCreate,
    ChatUserLogin,
    ChatUserRegister,
    ChatUserRead,
    PasswordResetCodeRequest,
    PasswordResetRequest,
    TokenResponse,
    VerificationCodeSend,
)
from services.db import log_audit as _db_log_audit
from services.user_db import managed_session

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Token secret — override via env JWT_SECRET_KEY
import os
_SECRET = os.environ.get("JWT_SECRET_KEY", "zzcc-dev-secret-change-me")
_TOKEN_TTL_SEC = 7 * 24 * 3600

# In-memory verification code store (dev only; production: Redis)
_verification_codes: dict[str, tuple[str, datetime]] = {}


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_password(password: str, hash_: str) -> bool:
    return _hash_password(password) == hash_


def _b64url(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def create_access_token(user_id: str, username: str, roles: str = "user") -> str:
    """Simple HMAC-signed token (not full JWT — keeps deps light)."""
    payload = f"{user_id}|{username}|{roles}|{datetime.now(timezone.utc).timestamp()}"
    sig = hashlib.sha256(f"{payload}{_SECRET}".encode()).hexdigest()
    return _b64url(payload.encode()) + "." + sig


def parse_access_token(token: str) -> dict | None:
    try:
        payload_b64, sig = token.rsplit(".", 1)
        payload = _b64url_decode(payload_b64).decode()
        if hashlib.sha256(f"{payload}{_SECRET}".encode()).hexdigest() != sig:
            return None
        user_id, username, roles, issued_at = payload.split("|")
        if datetime.now(timezone.utc).timestamp() - float(issued_at) > _TOKEN_TTL_SEC:
            return None
        return {"id": user_id, "username": username, "roles": roles,
                "sub": user_id, "iat": int(float(issued_at))}
    except Exception:
        return None


def _b64url_decode(s: str) -> bytes:
    import base64
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + padding).encode())


async def get_current_user_dep(
    authorization: Optional[str] = Header(None),
):
    """Extract user from Authorization: Bearer <token> header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录或缺少 Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = parse_access_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="无效或过期的 token")
    return user


def log_audit(*, actor: str, action: str, resource: str, detail: dict | None = None):
    """Fire-and-forget audit log. Best-effort."""
    import asyncio
    async def _w():
        try:
            await _db_log_audit(actor=actor, action=action, resource=resource, detail=detail)
        except Exception as exc:
            _log.warning("audit_log_failed", actor=actor, error=str(exc))
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_w())
    except RuntimeError:
        pass


# ════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════

@router.post("/register", response_model=TokenResponse)
async def register(body: ChatUserRegister):
    """Register a new user with password."""
    if not body.username or len(body.username) < 3:
        raise HTTPException(status_code=400, detail="用户名至少 3 个字符")
    if body.password and len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 个字符")

    async with managed_session() as sess:
        existing = (await sess.execute(
            text("SELECT id FROM chat_user WHERE username = :u AND is_deleted = FALSE"),
            {"u": body.username},
        )).first()
        if existing:
            raise HTTPException(status_code=409, detail="用户名已存在")

        uid = str(uuid.uuid4())
        await sess.execute(text(
            """INSERT INTO chat_user
               (id, username, display_name, password_hash, email, phone, client_uid)
               VALUES (CAST(:id AS UUID), :un, :dn, :ph, :em, :ph2, :cuid)
            """
        ), {
            "id": uid,
            "un": body.username,
            "dn": body.display_name or body.username,
            "ph": _hash_password(body.password) if body.password else None,
            "em": body.email,
            "ph2": body.phone,
            "cuid": body.client_uid,
        })
        await sess.commit()

    log_audit(actor=body.username, action="register", resource=f"chat_user:{uid}")
    return TokenResponse(
        access_token=create_access_token(uid, body.username),
        refresh_token="",
        expires_in=_TOKEN_TTL_SEC,
        user_id=uid,
        username=body.username,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: ChatUserLogin):
    """Login with password."""
    async with managed_session() as sess:
        row = (await sess.execute(
            text("SELECT * FROM chat_user WHERE username = :u AND is_deleted = FALSE"),
            {"u": body.username},
        )).mappings().first()
        if not row:
            raise HTTPException(status_code=401, detail="用户不存在")
        if not row.get("password_hash"):
            raise HTTPException(status_code=401, detail="该账号无密码，请使用离线登录或绑定身份")
        if not _verify_password(body.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="密码错误")
        if not row.get("is_active", True):
            raise HTTPException(status_code=403, detail="账号已被禁用")

        # Update last_login_at
        await sess.execute(text(
            "UPDATE chat_user SET last_login_at = NOW() WHERE id = CAST(:id AS UUID)"
        ), {"id": str(row["id"])})
        await sess.commit()

    uid = str(row["id"])
    log_audit(actor=body.username, action="login", resource=f"chat_user:{uid}")
    return TokenResponse(
        access_token=create_access_token(uid, body.username, roles="user"),
        refresh_token="",
        expires_in=_TOKEN_TTL_SEC,
        user_id=uid,
        username=body.username,
    )


@router.get("/me", response_model=ChatUserRead)
async def me(user=Depends(get_current_user_dep)):
    async with managed_session() as sess:
        row = (await sess.execute(
            text("SELECT * FROM chat_user WHERE id = CAST(:id AS UUID) AND is_deleted = FALSE"),
            {"id": user["id"]},
        )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "id": str(row["id"]),
        "username": row["username"],
        "display_name": row.get("display_name"),
        "email": row.get("email"),
        "phone": row.get("phone"),
        "avatar_url": row.get("avatar_url"),
        "matrix_user_id": row.get("matrix_user_id"),
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row.get("created_at")),
        "updated_at": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row.get("updated_at")),
        "last_login_at": row["last_login_at"].isoformat() if hasattr(row.get("last_login_at"), "isoformat") else row.get("last_login_at"),
        "is_active": row.get("is_active", True),
        "sync_status": row.get("sync_status", "local"),
        "client_uid": row.get("client_uid"),
    }


@router.post("/reset-password/code")
async def send_reset_code(body: PasswordResetCodeRequest):
    """Send reset code (dev: log + return; prod: email/SMS)."""
    async with managed_session() as sess:
        row = None
        if body.email:
            row = (await sess.execute(
                text("SELECT id, email FROM chat_user WHERE email = :e AND is_deleted = FALSE"),
                {"e": body.email},
            )).mappings().first()
        elif body.phone:
            row = (await sess.execute(
                text("SELECT id, phone FROM chat_user WHERE phone = :p AND is_deleted = FALSE"),
                {"p": body.phone},
            )).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="邮箱或手机号未绑定")

    code = f"{secrets.randbelow(900000) + 100000}"
    key = body.email or body.phone
    _verification_codes[key] = (code, datetime.now(timezone.utc))
    _log.info("reset_code_sent", target=key, code=code)
    return {"sent": True, "target": key, "code": code}


@router.post("/reset-password", response_model=TokenResponse)
async def reset_password(body: PasswordResetRequest):
    """Reset password with verification code."""
    key = body.email or body.phone
    if not key:
        raise HTTPException(status_code=400, detail="必须提供 email 或 phone")
    stored = _verification_codes.get(key)
    if not stored or stored[1] < datetime.now(timezone.utc).replace(
        minute=stored[1].minute - 5, second=0
    ):
        # Simple 5-min expiry
        try:
            age = (datetime.now(timezone.utc) - stored[1]).total_seconds()
        except Exception:
            age = 999
        if stored is None or age > 300:
            raise HTTPException(status_code=400, detail="验证码已过期")
    if stored[0] != body.code:
        raise HTTPException(status_code=400, detail="验证码错误")

    # Find user and update password
    async with managed_session() as sess:
        row = None
        if body.email:
            row = (await sess.execute(
                text("SELECT id, username FROM chat_user WHERE email = :e AND is_deleted = FALSE"),
                {"e": body.email},
            )).mappings().first()
        elif body.phone:
            row = (await sess.execute(
                text("SELECT id, username FROM chat_user WHERE phone = :p AND is_deleted = FALSE"),
                {"p": body.phone},
            )).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        await sess.execute(text(
            "UPDATE chat_user SET password_hash = :h, updated_at = NOW() WHERE id = CAST(:id AS UUID)"
        ), {"h": _hash_password(body.new_password), "id": str(row["id"])})
        await sess.commit()
    _verification_codes.pop(key, None)

    log_audit(actor=row["username"], action="reset_password", resource=f"chat_user:{row['id']}")
    return TokenResponse(
        access_token=create_access_token(str(row["id"]), row["username"]),
        refresh_token="",
        expires_in=_TOKEN_TTL_SEC,
        user_id=str(row["id"]),
        username=row["username"],
    )


@router.post("/send-code")
async def send_verification_code(body: VerificationCodeSend):
    """Send verification code for binding email/phone (dev mode: return code)."""
    if not body.email and not body.phone:
        raise HTTPException(status_code=400, detail="必须提供 email 或 phone")
    code = f"{secrets.randbelow(900000) + 100000}"
    key = f"bind:{body.email or body.phone}"
    _verification_codes[key] = (code, datetime.now(timezone.utc))
    _log.info("bind_code_sent", target=key, code=code)
    return {"sent": True, "target": body.email or body.phone, "code": code}
