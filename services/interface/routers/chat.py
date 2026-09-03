"""
Router: /api/v1/chat — Chat API backed by PostgreSQL.

Provides a Matrix-compatible REST surface for the Flutter client.
All auth is via /chat/login + /chat/register which issue HMAC tokens
signed by routers.auth.create_access_token; subsequent calls attach
the token as X-Access-Token (or Authorization: Bearer).

Storage:
  - users  → chat_user (services.user_db)
  - rooms → chat_room + chat_room_member
  - messages → chat_message

The sync endpoint uses long-polling with a since parameter (Unix ms
or a base64-encoded pagination cursor) and returns a next_batch cursor.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from dependencies import verify_api_key
from routers.auth import (
    _hash_password,
    _verify_password,
    create_access_token,
    parse_access_token,
    log_audit,
)
from services.user_db import execute, fetch_all, fetch_one, managed_session

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


# ════════════════════════════════════════════════════════════════════
# Schemas
# ════════════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: Optional[str] = Field(None, max_length=256)
    client_uid: Optional[str] = Field(None, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    ok: bool = True
    data: dict


class DeleteAccountRequest(BaseModel):
    erase: bool = Field(False)


class SyncAccountRequest(BaseModel):
    local_uid: str
    password: Optional[str] = None
    display_name: Optional[str] = None


class SyncAccountResponse(BaseModel):
    ok: bool = True
    data: dict


class RoomResponse(BaseModel):
    ok: bool = True
    data: dict


class MessagesResponse(BaseModel):
    ok: bool = True
    data: dict


class SyncResponse(BaseModel):
    ok: bool = True
    data: dict


class CreateRoomRequest(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    invite: Optional[list[str]] = None
    invitees: Optional[list[str]] = None  # alias for invite
    is_direct: bool = False

    @property
    def all_invitees(self) -> list[str]:
        seen: list[str] = []
        for lst in (self.invite, self.invitees):
            if lst:
                for x in lst:
                    if x not in seen:
                        seen.append(x)
        return seen


class SendMessageRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=8192)


class DisplayNameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=256)


# ════════════════════════════════════════════════════════════════════
# Helpers — token extraction, user resolution, cursor encoding
# ════════════════════════════════════════════════════════════════════

def _extract_token(x_access_token: Optional[str], authorization: Optional[str]) -> Optional[str]:
    if x_access_token:
        return x_access_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


async def resolve_user_from_token(token: Optional[str]) -> Optional[dict]:
    """Return chat_user row dict given a valid HMAC token, else None."""
    if not token:
        return None
    try:
        payload = parse_access_token(token)
    except Exception:
        return None
    if payload is None:
        return None
    uid = payload.get("id")
    if not uid:
        return None
    row = await fetch_one(
        "SELECT * FROM chat_user WHERE id = CAST(:uid AS UUID) AND is_deleted = FALSE AND is_active = TRUE",
        {"uid": str(uid)},
    )
    if not row:
        return None
    # Reject tokens issued before the last logout
    logged_out_at = row.get("logged_out_at")
    if logged_out_at:
        try:
            token_iat = payload.get("iat", 0)
            # logged_out_at is a datetime; convert to epoch seconds
            from datetime import datetime, timezone
            if isinstance(logged_out_at, str):
                logged_out_at = datetime.fromisoformat(logged_out_at.replace("Z", "+00:00"))
            if isinstance(logged_out_at, datetime):
                logout_ts = int(logged_out_at.timestamp())
                if token_iat <= logout_ts:
                    return None
        except Exception:
            pass
    return row


async def _auth_user(
    x_access_token: Annotated[Optional[str], Header()] = None,
    authorization: Annotated[Optional[str], Header()] = None,
) -> dict:
    user = await resolve_user_from_token(_extract_token(x_access_token, authorization))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    return user


# Cursor helpers — encode pagination state as URL-safe base64 JSON.
# We store both the last-seen microsecond timestamp and the last-seen row id
# so that two messages within the same microsecond cannot be re-returned.
def _encode_cursor(ts_ms: int, last_id: Optional[int] = None) -> str:
    obj: dict = {"ts": ts_ms}
    if last_id is not None:
        obj["id"] = int(last_id)
    raw = json.dumps(obj).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[int, Optional[int]]:
    """Return (ts_ms, last_id). Empty cursor → (0, None)."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        obj = json.loads(raw)
        ts = int(obj.get("ts") or 0)
        mid = obj.get("id")
        mid = int(mid) if mid is not None else None
        return ts, mid
    except Exception:
        try:
            return int(cursor), None
        except Exception:
            return 0, None


def _row_to_room(row: dict) -> dict:
    return {
        "room_id": str(row["id"]) if not str(row["id"]).startswith("!") else str(row["id"]),
        "name": row.get("name"),
        "topic": row.get("description"),
        "is_direct": row.get("room_type") == "dm",
    }


def _row_to_message(row: dict) -> dict:
    sent_at = row.get("sent_at")
    if sent_at is None:
        ts = 0
    elif isinstance(sent_at, (int, float)):
        ts = int(sent_at)
    else:
        # datetime → ms since epoch
        try:
            ts = int(sent_at.timestamp() * 1000)
        except Exception:
            ts = 0
    return {
        "event_id": row.get("server_msg_id") or str(row["id"]),
        "room_id": str(row["room_id"]),
        "sender": str(row["sender_id"]),
        "msgtype": row.get("msg_type") or "m.text",
        "body": row.get("content") or "",
        "timestamp": ts,
    }


# ════════════════════════════════════════════════════════════════════
# Auth endpoints
# ════════════════════════════════════════════════════════════════════

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    auth: str = Depends(verify_api_key),
):
    async with managed_session() as sess:
        existing = (await sess.execute(
            text("SELECT id, username FROM chat_user WHERE username = :u AND is_deleted = FALSE"),
            {"u": req.username},
        )).first()
        if existing:
            raise HTTPException(409, "用户名已存在")

        uid = uuid.uuid4()
        pwd_hash = _hash_password(req.password)
        await sess.execute(text(
            """INSERT INTO chat_user
               (id, username, display_name, password_hash, client_uid, sync_status, is_active, is_deleted)
               VALUES (:id, :u, :dn, :ph, :cuid, 'synced', TRUE, FALSE)
            """
        ), {
            "id": str(uid),
            "u": req.username,
            "dn": req.display_name,
            "ph": pwd_hash,
            "cuid": req.client_uid,
        })
        await sess.commit()

    token = create_access_token(str(uid), req.username)
    log_audit(actor=req.username, action="register", resource="chat_user",
              detail={"client_uid": req.client_uid})
    return {
        "ok": True,
        "data": {
            "user_id": str(uid),
            "access_token": token,
            "device_id": None,
            "home_server": "zzcc.local",
        },
    }


@router.post("/login", response_model=AuthResponse)
async def login(
    req: LoginRequest,
    auth: str = Depends(verify_api_key),
):
    row = await fetch_one(
        "SELECT * FROM chat_user WHERE username = :u AND is_deleted = FALSE AND is_active = TRUE",
        {"u": req.username},
    )
    if not row or not row.get("password_hash"):
        raise HTTPException(401, "用户不存在或密码错误")
    if not _verify_password(req.password, row["password_hash"]):
        raise HTTPException(401, "用户不存在或密码错误")

    await execute(
        "UPDATE chat_user SET last_login_at = NOW(), logged_out_at = NULL, updated_at = NOW() WHERE id = :id",
        {"id": str(row["id"])},
    )
    token = create_access_token(str(row["id"]), row["username"])
    log_audit(actor=row["username"], action="login", resource="chat_user")
    return {
        "ok": True,
        "data": {
            "user_id": str(row["id"]),
            "access_token": token,
            "device_id": None,
            "home_server": "zzcc.local",
            "display_name": row.get("display_name"),
        },
    }


@router.post("/logout")
async def logout(
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    uid = str(user["id"])
    await execute(
        "UPDATE chat_user SET logged_out_at = NOW(), updated_at = NOW() WHERE id = :id",
        {"id": uid},
    )
    log_audit(actor=user["username"], action="logout", resource="chat_user")
    return {"ok": True, "data": {"message": "Logged out", "user_id": uid}}


class DeleteAccountRequest(BaseModel):
    erase: bool = False


@router.post("/delete-account")
async def delete_account(
    req: DeleteAccountRequest = DeleteAccountRequest(),
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    uid = str(user["id"])
    if req.erase:
        await execute(
            "UPDATE chat_user SET is_deleted = TRUE, is_active = FALSE, updated_at = NOW() WHERE id = :id",
            {"id": uid},
        )
        await execute(
            "UPDATE chat_identity_binding SET binding_value = CONCAT('deleted:', binding_value) WHERE user_id = :id",
            {"id": uid},
        )
        await execute(
            "UPDATE chat_room_member SET user_id = gen_random_uuid() WHERE user_id = :id",
            {"id": uid},
        )
        await execute(
            "UPDATE chat_message SET is_deleted = TRUE WHERE sender_id = :id",
            {"id": uid},
        )
    else:
        await execute(
            "UPDATE chat_user SET is_active = FALSE, updated_at = NOW() WHERE id = :id",
            {"id": uid},
        )
    log_audit(actor=user["username"], action="delete_account",
              resource="chat_user", detail={"erase": req.erase})
    return {"ok": True, "data": {"user_id": uid, "erase": req.erase}}


@router.post("/sync-account", response_model=SyncAccountResponse, status_code=status.HTTP_201_CREATED)
async def sync_account(
    req: SyncAccountRequest,
    auth: str = Depends(verify_api_key),
):
    """Upsert a locally-created account onto the server by local_uid (client_uid)."""
    row = await fetch_one(
        "SELECT * FROM chat_user WHERE client_uid = :cuid AND is_deleted = FALSE",
        {"cuid": req.local_uid},
    )
    was_created = False
    async with managed_session() as sess:
        if row:
            sets = "display_name = COALESCE(:dn, display_name), updated_at = NOW(), sync_status = 'synced'"
            if req.password:
                sets += ", password_hash = :ph"
            await sess.execute(text(
                f"UPDATE chat_user SET {sets} WHERE id = :id"
            ), {
                "id": str(row["id"]),
                "dn": req.display_name,
                "ph": _hash_password(req.password) if req.password else None,
            })
        else:
            uid = uuid.uuid4()
            await sess.execute(text(
                """INSERT INTO chat_user
                   (id, username, display_name, password_hash, client_uid, sync_status, is_active, is_deleted)
                   VALUES (:id, :u, :dn, :ph, :cuid, 'synced', TRUE, FALSE)
                """
            ), {
                "id": str(uid),
                "u": req.local_uid,
                "dn": req.display_name,
                "ph": _hash_password(req.password) if req.password else None,
                "cuid": req.local_uid,
            })
            row = {
                "id": str(uid),
                "username": req.local_uid,
                "display_name": req.display_name,
                "password_hash": _hash_password(req.password) if req.password else None,
            }
            was_created = True
        await sess.commit()

    token = create_access_token(str(row["id"]), row["username"])
    log_audit(actor=row["username"], action="sync_account",
              resource="chat_user", detail={"created": was_created})
    return {
        "ok": True,
        "data": {
            "user_id": str(row["id"]),
            "access_token": token,
            "was_created": was_created,
        },
    }


# ════════════════════════════════════════════════════════════════════
# Profile endpoints
# ════════════════════════════════════════════════════════════════════

@router.get("/profile/{user_id}", response_model=RoomResponse)
async def get_profile(
    user_id: str,
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    row = await fetch_one(
        "SELECT id, username, display_name, avatar_url, is_active, created_at FROM chat_user WHERE id = CAST(:id AS UUID) AND is_deleted = FALSE",
        {"id": user_id},
    )
    if not row:
        raise HTTPException(404, "用户不存在")
    return {"ok": True, "data": {
        "user_id": str(row["id"]),
        "name": row.get("display_name") or row.get("username"),
        "display_name": row.get("display_name"),
        "username": row.get("username"),
        "avatar_url": row.get("avatar_url"),
        "active": row.get("is_active"),
    }}


@router.put("/profile/displayname", response_model=RoomResponse)
async def set_display_name(
    body: DisplayNameRequest,
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    await execute(
        "UPDATE chat_user SET display_name = :dn, updated_at = NOW() WHERE id = :id",
        {"dn": body.display_name, "id": str(user["id"])},
    )
    log_audit(actor=user["username"], action="set_display_name", resource="chat_user")
    return {"ok": True, "data": {"user_id": str(user["id"]), "display_name": body.display_name}}


# ════════════════════════════════════════════════════════════════════
# Room endpoints
# ════════════════════════════════════════════════════════════════════

@router.get("/rooms", response_model=RoomResponse)
async def list_rooms(
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    rooms = await fetch_all(
        """SELECT r.*,
                  (SELECT COUNT(*) FROM chat_message m
                     WHERE m.room_id = r.id AND m.is_deleted = FALSE
                       AND m.sender_id <> :me) AS unread_count,
                  (SELECT m2.content FROM chat_message m2
                     WHERE m2.room_id = r.id AND m2.is_deleted = FALSE
                     ORDER BY m2.sent_at DESC LIMIT 1) AS last_body,
                  (SELECT m3.sent_at FROM chat_message m3
                     WHERE m3.room_id = r.id AND m3.is_deleted = FALSE
                     ORDER BY m3.sent_at DESC LIMIT 1) AS last_ts
            FROM chat_room r
            JOIN chat_room_member rm ON rm.room_id = r.id
            WHERE r.id IS NOT NULL AND r.is_deleted = FALSE
              AND rm.user_id = CAST(:me AS UUID)""",
        {"me": str(user["id"])},
    )
    payload = []
    for r in rooms:
        d = _row_to_room(r)
        d["unread_count"] = int(r.get("unread_count") or 0)
        d["last_message"] = r.get("last_body")
        d["last_message_ts"] = int(r["last_ts"].timestamp() * 1000) if r.get("last_ts") and hasattr(r["last_ts"], "timestamp") else None
        payload.append(d)
    return {"ok": True, "data": {"rooms": payload}}


@router.post("/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    req: CreateRoomRequest,
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    room_id = uuid.uuid4()
    uid = str(user["id"])
    async with managed_session() as sess:
        await sess.execute(text(
            """INSERT INTO chat_room (id, name, description, room_type, owner_id, is_deleted)
               VALUES (:id, :name, :topic, :rtype, CAST(:owner AS UUID), FALSE)
            """
        ), {
            "id": str(room_id),
            "name": req.name,
            "topic": req.topic,
            "rtype": "dm" if req.is_direct else "private",
            "owner": uid,
        })
        await sess.execute(text(
            """INSERT INTO chat_room_member (room_id, user_id, role)
               VALUES (CAST(:rid AS UUID), CAST(:uid AS UUID), 'owner')
            """
        ), {"rid": str(room_id), "uid": uid})
        for invitee in req.all_invitees:
            try:
                await sess.execute(text(
                    """INSERT INTO chat_room_member (room_id, user_id, role)
                       VALUES (CAST(:rid AS UUID), CAST(:inv AS UUID), 'member')
                       ON CONFLICT DO NOTHING
                    """
                ), {"rid": str(room_id), "inv": invitee})
            except Exception as exc:
                _log.warning("invite_skip %s: %s", invitee, exc)
        await sess.commit()

    log_audit(actor=user["username"], action="create_room",
              resource=f"chat_room:{room_id}")
    return {
        "ok": True,
        "data": {
            "room_id": str(room_id),
            "name": req.name,
            "topic": req.topic,
            "is_direct": req.is_direct,
        },
    }


@router.post("/rooms/{room_id}/join", response_model=RoomResponse)
async def join_room(
    room_id: str,
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    room_id_u = uuid.UUID(room_id)
    uid = str(user["id"])
    await execute(
        """INSERT INTO chat_room_member (room_id, user_id, role)
           VALUES (CAST(:rid AS UUID), CAST(:uid AS UUID), 'member')
           ON CONFLICT (room_id, user_id) DO NOTHING
        """,
        {"rid": str(room_id_u), "uid": uid},
    )
    log_audit(actor=user["username"], action="join_room",
              resource=f"chat_room:{room_id}")
    return {"ok": True, "data": {"room_id": str(room_id_u), "action": "joined"}}


@router.post("/rooms/{room_id}/leave")
async def leave_room(
    room_id: str,
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    try:
        rid = str(uuid.UUID(room_id))
    except Exception:
        raise HTTPException(400, "invalid room_id")
    await execute(
        "DELETE FROM chat_room_member WHERE room_id = CAST(:rid AS UUID) AND user_id = CAST(:uid AS UUID)",
        {"rid": rid, "uid": str(user["id"])},
    )
    log_audit(actor=user["username"], action="leave_room",
              resource=f"chat_room:{rid}")
    return {"ok": True, "data": {"room_id": rid, "action": "left"}}


# ════════════════════════════════════════════════════════════════════
# Message endpoints
# ════════════════════════════════════════════════════════════════════

@router.get("/rooms/{room_id}/messages", response_model=MessagesResponse)
async def get_messages(
    room_id: str,
    limit: int = 50,
    from_token: Optional[str] = None,
    from_start: bool = False,
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    try:
        rid = str(uuid.UUID(room_id))
    except Exception:
        raise HTTPException(400, "invalid room_id")
    limit = min(max(limit, 1), 500)

    since_ms, since_id = _decode_cursor(from_token) if from_token else (0, None)
    if since_ms > 0 or since_id is not None:
        rows = await fetch_all(
            """SELECT * FROM chat_message
               WHERE room_id = CAST(:rid AS UUID) AND is_deleted = FALSE
                 AND sent_at >= to_timestamp(:ts / 1000.0)
               ORDER BY sent_at ASC, id ASC
               LIMIT :lim""",
            {"rid": rid, "ts": since_ms, "lim": limit},
        )
        # Skip rows at or before the cursor (idempotent pagination).
        if since_id is None:
            rows = [r for r in rows if _row_to_message(r)["timestamp"] > since_ms]
        else:
            rows = [r for r in rows if int(r["id"]) > since_id]
    else:
        if from_start:
            rows = await fetch_all(
                """SELECT * FROM chat_message
                   WHERE room_id = CAST(:rid AS UUID) AND is_deleted = FALSE
                   ORDER BY sent_at ASC, id ASC
                   LIMIT :lim""",
                {"rid": rid, "lim": limit},
            )
        else:
            rows = await fetch_all(
                """SELECT * FROM chat_message
                   WHERE room_id = CAST(:rid AS UUID) AND is_deleted = FALSE
                   ORDER BY sent_at DESC
                   LIMIT :lim""",
                {"rid": rid, "lim": limit},
            )
            rows.reverse()

    messages = [_row_to_message(r) for r in rows]
    next_batch = None
    if messages:
        last = rows[-1]
        last_id = int(last["id"]) if "id" in last else None
        next_batch = _encode_cursor(messages[-1]["timestamp"], last_id)
    return {"ok": True, "data": {"messages": messages, "next_batch": next_batch}}


@router.post("/rooms/{room_id}/messages", response_model=RoomResponse)
async def send_message(
    room_id: str,
    req: SendMessageRequest,
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    try:
        rid = str(uuid.UUID(room_id))
    except Exception:
        raise HTTPException(400, "invalid room_id")
    uid = str(user["id"])

    member = await fetch_one(
        "SELECT room_id FROM chat_room_member WHERE room_id = CAST(:rid AS UUID) AND user_id = CAST(:uid AS UUID)",
        {"rid": rid, "uid": uid},
    )
    if not member:
        raise HTTPException(403, "not a member of this room")

    server_msg_id = f"${uuid.uuid4()}"
    client_msg_id = f"msg-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    await execute(
        """INSERT INTO chat_message
           (room_id, sender_id, content, msg_type, client_msg_id, server_msg_id)
           VALUES (CAST(:rid AS UUID), CAST(:uid AS UUID), :body, 'm.text', :cid, :sid)
        """,
        {"rid": rid, "uid": uid, "body": req.body, "cid": client_msg_id, "sid": server_msg_id},
    )
    log_audit(actor=user["username"], action="send_message",
              resource=f"chat_room:{rid}")
    return {"ok": True, "data": {
        "event_id": server_msg_id,
        "room_id": rid,
        "sender": uid,
        "msgtype": "m.text",
        "body": req.body,
        "timestamp": int(time.time() * 1000),
    }}


# ════════════════════════════════════════════════════════════════════
# Sync (long-polling)
# ════════════════════════════════════════════════════════════════════

_SYNC_MAX_WAIT_S = 30.0
_SYNC_POLL_INTERVAL_S = 1.0


@router.get("/sync", response_model=SyncResponse)
async def sync(
    since: Optional[str] = None,
    timeout: int = 30000,
    user: dict = Depends(_auth_user),
    auth: str = Depends(verify_api_key),
):
    """Long-poll for new messages. Returns per-room new_messages and next_batch."""
    uid = str(user["id"])
    max_wait_s = min(max(timeout, 0) / 1000.0, _SYNC_MAX_WAIT_S)
    deadline = time.monotonic() + max_wait_s

    since_ts_ms, since_id = _decode_cursor(since) if since else (0, None)
    if since_ts_ms <= 0:
        since_ts_ms = 0

    result: dict = {"rooms": {}}
    next_batch_ts = since_ts_ms
    next_batch_id = since_id

    while True:
        new_messages_by_room: dict[str, list[dict]] = {}
        if since_id is None and since_ts_ms == 0:
            rows = await fetch_all(
                """SELECT m.id, m.room_id, m.sender_id, m.content, m.msg_type,
                         m.client_msg_id, m.server_msg_id, m.sent_at
                   FROM chat_message m
                   JOIN chat_room_member rm ON rm.room_id = m.room_id
                   WHERE m.is_deleted = FALSE
                     AND rm.user_id = CAST(:uid AS UUID)
                   ORDER BY m.sent_at ASC, m.id ASC
                   LIMIT 500""",
                {"uid": uid},
            )
        else:
            rows = await fetch_all(
                """SELECT m.id, m.room_id, m.sender_id, m.content, m.msg_type,
                         m.client_msg_id, m.server_msg_id, m.sent_at
                   FROM chat_message m
                   JOIN chat_room_member rm ON rm.room_id = m.room_id
                   WHERE m.is_deleted = FALSE
                     AND rm.user_id = CAST(:uid AS UUID)
                     AND m.sent_at >= to_timestamp(:ts / 1000.0)
                   ORDER BY m.sent_at ASC, m.id ASC
                   LIMIT 500""",
                {"uid": uid, "ts": since_ts_ms},
            )
            if since_id is not None:
                rows = [r for r in rows if int(r["id"]) > since_id]
            else:
                rows = [r for r in rows if _row_to_message(r)["timestamp"] > since_ts_ms]

        if rows:
            for r in rows:
                msg = _row_to_message(r)
                rid = msg["room_id"]
                new_messages_by_room.setdefault(rid, []).append(msg)
                ts = msg["timestamp"]
                if ts > next_batch_ts:
                    next_batch_ts = ts
                next_batch_id = int(r["id"])

        if new_messages_by_room:
            for rid, msgs in new_messages_by_room.items():
                result["rooms"].setdefault(rid, {"new_messages": [], "limited": False, "prev_batch": None})
                result["rooms"][rid]["new_messages"].extend(msgs)

        if new_messages_by_room or time.monotonic() >= deadline:
            break
        await asyncio.sleep(_SYNC_POLL_INTERVAL_S)

    result["next_batch"] = _encode_cursor(next_batch_ts, next_batch_id)
    return {"ok": True, "data": result}
