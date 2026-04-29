"""
Router: /api/v1/chat — Matrix chat proxy endpoints.

Provides a clean REST API for Flutter to interact with Matrix Synapse.
All endpoints require X-API-Key header (if configured) and X-Access-Token for Matrix auth.
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from dependencies import verify_api_key
from services.matrix_proxy import MatrixClient, MatrixError, get_matrix_client

router = APIRouter(prefix="/chat", tags=["chat"])


# ============================================================
# Schemas
# ============================================================

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255, description="Matrix username (localpart)")
    password: str = Field(..., min_length=8, description="Password")
    display_name: Optional[str] = Field(None, description="Display name")


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username or full user ID (@user:server)")
    password: str = Field(..., description="Password")


class AuthResponse(BaseModel):
    ok: bool = True
    data: dict


class CreateRoomRequest(BaseModel):
    name: Optional[str] = Field(None, description="Room name")
    topic: Optional[str] = Field(None, description="Room topic/description")
    invite: Optional[list[str]] = Field(None, description="List of user IDs to invite")
    is_direct: bool = Field(False, description="Is this a direct message room")


class SendMessageRequest(BaseModel):
    body: str = Field(..., min_length=1, description="Message text")


class RoomResponse(BaseModel):
    ok: bool = True
    data: dict


class MessagesResponse(BaseModel):
    ok: bool = True
    data: dict


class SyncResponse(BaseModel):
    ok: bool = True
    data: dict


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=256)


class SyncAccountRequest(BaseModel):
    local_uid: str = Field(..., min_length=1, max_length=255, description="Locally generated UID")
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = Field(None, description="Display name")


class SyncAccountResponse(BaseModel):
    ok: bool = True
    data: dict


# ============================================================
# Dependencies
# ============================================================

def get_matrix() -> MatrixClient:
    """Get Matrix client singleton."""
    return get_matrix_client()


def get_access_token(
    x_access_token: Annotated[Optional[str], Header()] = None
) -> str:
    """Extract access token from header."""
    if not x_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Access-Token header",
        )
    return x_access_token


# ============================================================
# Authentication Endpoints
# ============================================================

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Register a new Matrix user."""
    try:
        result = await matrix.register(
            username=req.username,
            password=req.password,
            display_name=req.display_name,
        )
        return {"ok": True, "data": result}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.post("/login", response_model=AuthResponse)
async def login(
    req: LoginRequest,
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Login and get access token."""
    try:
        result = await matrix.login(
            username=req.username,
            password=req.password,
        )
        return {"ok": True, "data": result}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.post("/logout")
async def logout(
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Logout and invalidate access token."""
    try:
        await matrix.logout(access_token)
        return {"ok": True, "data": {"message": "Logged out"}}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


class DeleteAccountRequest(BaseModel):
    erase: bool = Field(False, description="Whether to also erase all user data (true = permanent deletion)")


@router.post("/delete-account")
async def delete_account(
    req: DeleteAccountRequest = DeleteAccountRequest(),
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """
    Deactivate (and optionally erase) the current user's account.

    - erase=false: account is deactivated (can no longer authenticate),
      but messages/rooms are preserved. Reversible via re-registration.
    - erase=true: permanently erases all user data from the server.
      This is NOT reversible.

    Requires the user's current access token.
    """
    try:
        result = await matrix.deactivate_user(
            access_token=access_token,
            erase_user=req.erase,
        )
        return {"ok": True, "data": result}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.post("/sync-account", response_model=SyncAccountResponse, status_code=status.HTTP_201_CREATED)
async def sync_account(
    req: SyncAccountRequest,
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """
    Sync a locally-created account to the server.

    Flow:
    1. Attempt register with the local UID + password
       - If success: return server user_id + access_token (newly created)
       - If 400/M_USER_EXISTS: account exists on server → try login instead
    2. Attempt login (only when register said username exists)
       - If success: return server user_id + access_token (was already registered)
       - If failed: propagate the error
    """
    # Step 1: try register
    try:
        reg_result = await matrix.register(
            username=req.local_uid,
            password=req.password,
            display_name=req.display_name,
        )
        return {
            "ok": True,
            "data": {
                "user_id": reg_result["user_id"],
                "access_token": reg_result["access_token"],
                "was_created": True,
            },
        }
    except MatrixError as exc:
        # Only fall through to login if username already taken
        # M_USER_IN_USE (409) means the UID was registered on another device
        if exc.http_status != 409 or "M_USER_IN_USE" not in exc.code:
            raise HTTPException(status_code=exc.http_status, detail=exc.message)

    # Step 2: username exists → try login
    try:
        login_result = await matrix.login(
            username=req.local_uid,
            password=req.password,
        )
        return {
            "ok": True,
            "data": {
                "user_id": login_result["user_id"],
                "access_token": login_result["access_token"],
                "was_created": False,
            },
        }
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


# ============================================================
# Profile Endpoints
# ============================================================

@router.get("/profile/{user_id}", response_model=RoomResponse)
async def get_profile(
    user_id: str,
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Get user profile."""
    try:
        result = await matrix.get_profile(user_id)
        return {"ok": True, "data": result}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.put("/profile/displayname", response_model=RoomResponse)
async def set_display_name(
    req: ProfileUpdateRequest,
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Set current user's display name."""
    # Extract user ID from token (we need to get it from Matrix)
    # For now, we'll use a workaround - get user ID from whoami
    try:
        # Get user ID from whoami
        whoami = await matrix._request("GET", "/account/whoami", access_token=access_token)
        user_id = whoami["user_id"]
        
        await matrix.set_display_name(access_token, user_id, req.display_name)
        return {"ok": True, "data": {"display_name": req.display_name}}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


# ============================================================
# Room Endpoints
# ============================================================

@router.get("/rooms", response_model=RoomResponse)
async def list_rooms(
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Get list of joined rooms with details."""
    try:
        room_ids = await matrix.get_joined_rooms(access_token)
        
        # Get details for each room
        rooms = []
        for room_id in room_ids:
            try:
                info = await matrix.get_room_info(access_token, room_id)
                rooms.append(info)
            except MatrixError:
                # Skip rooms we can't access
                continue
        
        return {"ok": True, "data": {"rooms": rooms}}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.post("/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    req: CreateRoomRequest,
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Create a new room."""
    try:
        result = await matrix.create_room(
            access_token=access_token,
            name=req.name,
            topic=req.topic,
            invite=req.invite,
            is_direct=req.is_direct,
        )
        return {"ok": True, "data": result}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.post("/rooms/{room_id}/join", response_model=RoomResponse)
async def join_room(
    room_id: str,
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Join a room by ID or alias."""
    try:
        result = await matrix.join_room(access_token, room_id)
        return {"ok": True, "data": result}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.post("/rooms/{room_id}/leave")
async def leave_room(
    room_id: str,
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Leave a room."""
    try:
        await matrix.leave_room(access_token, room_id)
        return {"ok": True, "data": {"room_id": room_id, "action": "left"}}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


# ============================================================
# Message Endpoints
# ============================================================

@router.get("/rooms/{room_id}/messages", response_model=MessagesResponse)
async def get_messages(
    room_id: str,
    limit: int = 50,
    from_token: Optional[str] = None,
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Get messages from a room."""
    try:
        result = await matrix.get_room_messages(
            access_token=access_token,
            room_id=room_id,
            limit=limit,
            from_token=from_token,
        )
        return {"ok": True, "data": result}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.post("/rooms/{room_id}/messages", response_model=RoomResponse)
async def send_message(
    room_id: str,
    req: SendMessageRequest,
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """Send a message to a room."""
    try:
        result = await matrix.send_message(
            access_token=access_token,
            room_id=room_id,
            body=req.body,
        )
        return {"ok": True, "data": result}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


# ============================================================
# Sync Endpoint (Real-time updates)
# ============================================================

@router.get("/sync", response_model=SyncResponse)
async def sync(
    since: Optional[str] = None,
    timeout: int = 30000,
    access_token: str = Depends(get_access_token),
    matrix: MatrixClient = Depends(get_matrix),
    auth: str = Depends(verify_api_key),
):
    """
    Long-polling sync for real-time updates.
    
    - Call initially with no `since` to get initial state
    - Use returned `next_batch` as next `since` parameter
    - Server will block up to `timeout` ms until there's new data
    """
    try:
        result = await matrix.sync(
            access_token=access_token,
            since=since,
            timeout_ms=timeout,
        )
        return {"ok": True, "data": result}
    except MatrixError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)
