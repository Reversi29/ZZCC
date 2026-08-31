"""
/chat/users/* — server-side user CRUD for offline-first account sync.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from models.user_models import (
    ChatUserCreate,
    ChatUserRead,
    ChatUserListResponse,
    ChatUserUpdate,
    ChatUserLogin,
    ChatUserRegister,
    ChatUserSyncRequest,
    ChatUserSyncResponse,
    IdentityBindingCreate,
    IdentityBindingRead,
    IdentityBindingListResponse,
    PasswordResetCodeRequest,
    PasswordResetRequest,
    VerificationCodeSend,
    TokenResponse,
)
from routers.auth import (
    _hash_password,
    _verify_password,
    create_access_token,
    get_current_user_dep,
    log_audit,
)
from services.user_db import fetch_all, fetch_one, managed_session

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat/users", tags=["chat-users"])


def _user_to_read(row: dict) -> dict:
    """Convert DB row → ChatUserRead dict."""
    if not row:
        return {}
    return {
        "id": str(row["id"]),
        "username": row["username"],
        "display_name": row.get("display_name"),
        "email": row.get("email"),
        "phone": row.get("phone"),
        "avatar_url": row.get("avatar_url"),
        "matrix_user_id": row.get("matrix_user_id"),
        "created_at": row["created_at"].isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at"),
        "updated_at": row["updated_at"].isoformat() if hasattr(row.get("updated_at"), "isoformat") else row.get("updated_at"),
        "last_login_at": row["last_login_at"].isoformat() if hasattr(row.get("last_login_at"), "isoformat") else row.get("last_login_at"),
        "is_active": row.get("is_active", True),
        "sync_status": row.get("sync_status", "local"),
        "client_uid": row.get("client_uid"),
    }


@router.get("", response_model=ChatUserListResponse)
async def list_users(
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    user=Depends(get_current_user_dep),
):
    """List users. Search by username/display_name/email/phone."""
    where = "WHERE is_deleted = FALSE"
    params: dict = {"limit": limit, "skip": skip}
    if q:
        where += " AND (username ILIKE :q OR display_name ILIKE :q OR email ILIKE :q OR phone ILIKE :q)"
        params["q"] = f"%{q}%"
    async with managed_session() as sess:
        result = await sess.execute(
            text(f"SELECT * FROM chat_user {where} ORDER BY created_at DESC LIMIT :limit OFFSET :skip"),
            params,
        )
        rows = [dict(r) for r in result.mappings()]
    return {"data": [_user_to_read(r) for r in rows], "length": len(rows)}


@router.get("/{user_id}", response_model=ChatUserRead)
async def get_user(
    user_id: str,
    user=Depends(get_current_user_dep),
):
    async with managed_session() as sess:
        row = (await sess.execute(
            text("SELECT * FROM chat_user WHERE id = CAST(:id AS UUID) AND is_deleted = FALSE"),
            {"id": user_id},
        )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _user_to_read(dict(row))


@router.patch("/{user_id}", response_model=ChatUserRead)
async def update_user(
    user_id: str,
    patch: ChatUserUpdate,
    user=Depends(get_current_user_dep),
):
    """Update profile. Self can edit own profile; admin can edit any."""
    if str(user["id"]) != user_id and "admin" not in str(user.get("roles", "user")):
        raise HTTPException(status_code=403, detail="只能修改自己的资料")

    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="无更新内容")
    # Remove is_deleted from user-editable fields
    data.pop("is_deleted", None)

    sets = ", ".join(f"{k} = :{k}" for k in data.keys())
    params = {**data, "id": user_id}
    params["updated_at"] = text("NOW()").render_generic(bindparam=None) if False else None
    # Simpler: execute with NOW()
    sql = f"UPDATE chat_user SET {sets}, updated_at = NOW() WHERE id = CAST(:id AS UUID) AND is_deleted = FALSE"
    params.pop("updated_at", None)
    async with managed_session() as sess:
        await sess.execute(text(sql), params)
        await sess.commit()
    log_audit(actor=user["username"], action="update_user", resource=f"chat_user:{user_id}", detail={"fields": list(data.keys())})
    return await get_user(user_id, user=user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    force: bool = False,
    user=Depends(get_current_user_dep),
):
    """Soft-delete user. force=True also nullifies password."""
    if str(user["id"]) != user_id and "admin" not in str(user.get("roles", "user")):
        raise HTTPException(status_code=403, detail="只能删除自己的账号")

    if force:
        sql = "UPDATE chat_user SET is_deleted = TRUE, password_hash = NULL, is_active = FALSE, updated_at = NOW() WHERE id = CAST(:id AS UUID)"
    else:
        sql = "UPDATE chat_user SET is_deleted = TRUE, updated_at = NOW() WHERE id = CAST(:id AS UUID)"
    async with managed_session() as sess:
        await sess.execute(text(sql), {"id": user_id})
        await sess.commit()
    log_audit(actor=user["username"], action="delete_user", resource=f"chat_user:{user_id}", detail={"force": force})
    return {"success": True}


@router.post("/sync", response_model=ChatUserSyncResponse)
async def sync_local_users(
    req: ChatUserSyncRequest,
    user=Depends(get_current_user_dep),
):
    """Batch upsert local users from Flutter client.

    For each user in req.users:
      - if client_uid matches existing row → merge server-side fields
      - else → create new row with local user info
    """
    created = 0
    updated = 0
    conflicts = []
    async with managed_session() as sess:
        for u in req.users:
            existing = (await sess.execute(
                text("SELECT id FROM chat_user WHERE client_uid = :cuid AND is_deleted = FALSE"),
                {"cuid": u.client_uid},
            )).first()
            if existing:
                # Merge
                sets = "display_name = COALESCE(:dn, display_name), email = COALESCE(:em, email), phone = COALESCE(:ph, phone), avatar_url = COALESCE(:av, avatar_url), is_deleted = FALSE, sync_status = 'synced', updated_at = NOW()"
                await sess.execute(text(
                    f"UPDATE chat_user SET {sets} WHERE client_uid = :cuid"
                ), {
                    "dn": u.display_name, "em": u.email, "ph": u.phone,
                    "av": u.avatar_url, "cuid": u.client_uid,
                })
                updated += 1
            else:
                # New user
                uid = uuid.uuid4()
                await sess.execute(text(
                    """INSERT INTO chat_user
                       (id, username, display_name, email, phone, avatar_url, client_uid, sync_status)
                       VALUES (:id, :un, :dn, :em, :ph, :av, :cuid, 'synced')
                    """
                ), {
                    "id": str(uid), "un": u.username, "dn": u.display_name,
                    "em": u.email, "ph": u.phone, "av": u.avatar_url,
                    "cuid": u.client_uid,
                })
                created += 1
        await sess.commit()
    log_audit(actor=user["username"], action="sync_users", resource="chat_user", detail={"created": created, "updated": updated})
    return {"created": created, "updated": updated, "conflicts": conflicts}


# ════════════════════════════════════════════════════════════════════
# Identity bindings
# ════════════════════════════════════════════════════════════════════

@router.post("/{user_id}/identities", response_model=IdentityBindingRead)
async def create_binding(
    user_id: str,
    binding: IdentityBindingCreate,
    user=Depends(get_current_user_dep),
):
    """Add email/phone/matrix binding to a user."""
    async with managed_session() as sess:
        existing = (await sess.execute(
            text("SELECT id, user_id FROM chat_identity_binding WHERE binding_type = :t AND binding_value = :v"),
            {"t": binding.binding_type, "v": binding.binding_value},
        )).first()
        if existing:
            other_id = existing.user_id
            if str(other_id) == user_id:
                return {"user_id": user_id, "binding_type": binding.binding_type,
                        "binding_value": binding.binding_value, "verified": True, "created_at": ""}
            raise HTTPException(status_code=409, detail="该身份已绑定其他用户")

        await sess.execute(text(
            """INSERT INTO chat_identity_binding
               (user_id, binding_type, binding_value, verified_at)
               VALUES (CAST(:uid AS UUID), :t, :v, CASE WHEN :vflag THEN NOW() ELSE NULL END)
            """
        ), {
            "uid": str(user_id),
            "t": binding.binding_type,
            "v": binding.binding_value,
            "vflag": bool(binding.verified),
        })

        # Also update chat_user.email or chat_user.phone
        if binding.binding_type == "email":
            await sess.execute(text(
                "UPDATE chat_user SET email = :v, updated_at = NOW() WHERE id = CAST(:uid AS UUID)"
            ), {"v": binding.binding_value, "uid": user_id})
        elif binding.binding_type == "phone":
            await sess.execute(text(
                "UPDATE chat_user SET phone = :v, updated_at = NOW() WHERE id = CAST(:uid AS UUID)"
            ), {"v": binding.binding_value, "uid": user_id})

        await sess.commit()
    log_audit(actor=user["username"], action="bind_identity", resource=f"chat_user:{user_id}",
              detail={"type": binding.binding_type, "verified": bool(binding.verified)})
    return {"user_id": user_id, "binding_type": binding.binding_type,
            "binding_value": binding.binding_value, "verified": bool(binding.verified), "created_at": ""}


@router.get("/{user_id}/identities", response_model=IdentityBindingListResponse)
async def list_bindings(
    user_id: str,
    user=Depends(get_current_user_dep),
):
    async with managed_session() as sess:
        rows = (await sess.execute(
            text("SELECT * FROM chat_identity_binding WHERE user_id = CAST(:uid AS UUID)"),
            {"uid": user_id},
        )).mappings().all()
    return {"items": [
        {"user_id": user_id, "binding_type": r["binding_type"],
         "binding_value": r["binding_value"], "verified": r["verified_at"] is not None,
         "verified_method": r.get("verified_method"),
         "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])}
        for r in rows
    ]}
