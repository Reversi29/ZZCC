"""
Matrix Proxy Service — Thin wrapper around Synapse Client-Server API.

Provides a clean interface for Flutter to interact with Matrix without
dealing with the full complexity of the Matrix protocol.
"""
from __future__ import annotations

import httpx
from typing import Any, Optional
import structlog

_log = structlog.get_logger()


class MatrixError(Exception):
    """Matrix API error with code and message."""
    def __init__(self, code: str, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(f"[{code}] {message}")


class MatrixClient:
    """Client for Matrix Synapse homeserver."""
    
    def __init__(self, base_url: str = "http://124.223.47.167:8008"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        await self.client.aclose()
    
    def _make_url(self, path: str) -> str:
        """Build full Matrix API URL."""
        if path.startswith("/_matrix/"):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/_matrix/client/v3{path}"
    
    def _headers(self, access_token: Optional[str] = None) -> dict[str, str]:
        """Build request headers with optional auth."""
        headers = {"Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers
    
    async def _request(
        self,
        method: str,
        path: str,
        access_token: Optional[str] = None,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Make a Matrix API request."""
        url = self._make_url(path)
        headers = self._headers(access_token)
        
        _log.debug(
            "matrix_request",
            method=method,
            path=path,
            has_auth=bool(access_token),
        )
        
        try:
            response = await self.client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params,
            )
        except httpx.NetworkError as exc:
            _log.error("matrix_network_error", error=str(exc))
            raise MatrixError("M_NETWORK_ERROR", f"Cannot reach Matrix server: {exc}", 503)
        
        data = response.json() if response.content else {}
        
        if response.status_code >= 400:
            errcode = data.get("errcode", "M_UNKNOWN")
            error = data.get("error", "Unknown error")
            _log.warning(
                "matrix_error_response",
                status=response.status_code,
                errcode=errcode,
                error=error,
            )
            raise MatrixError(errcode, error, response.status_code)
        
        return data
    
    # ============================================================
    # Authentication
    # ============================================================
    
    async def register(
        self,
        username: str,
        password: str,
        display_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Register a new user."""
        # First, register without auth (admin API or shared secret)
        # For P1, we use the shared secret approach
        data = {
            "username": username,
            "password": password,
            "auth": {"type": "m.login.dummy"},
        }
        if display_name:
            data["displayname"] = display_name
        
        try:
            result = await self._request("POST", "/register", json_data=data)
        except MatrixError as exc:
            if exc.code == "M_USER_IN_USE":
                raise MatrixError("M_USER_IN_USE", f"Username '{username}' already taken", 409)
            raise
        
        return {
            "user_id": result["user_id"],
            "access_token": result["access_token"],
            "device_id": result.get("device_id"),
            "home_server": result.get("home_server"),
        }
    
    async def login(self, username: str, password: str) -> dict[str, Any]:
        """Login and get access token."""
        # Handle username with or without server part
        if ":" not in username:
            identifier = {
                "type": "m.id.user",
                "user": username,
            }
        else:
            identifier = {
                "type": "m.id.user",
                "user": username.split(":")[0].lstrip("@"),
            }
        
        data = {
            "type": "m.login.password",
            "identifier": identifier,
            "password": password,
        }
        
        result = await self._request("POST", "/login", json_data=data)
        
        return {
            "user_id": result["user_id"],
            "access_token": result["access_token"],
            "device_id": result.get("device_id"),
            "home_server": result.get("home_server"),
        }
    
    async def logout(self, access_token: str) -> None:
        """Logout and invalidate access token."""
        await self._request("POST", "/logout", access_token=access_token)

    async def deactivate_user(self, access_token: str, erase_user: bool = False) -> dict[str, Any]:
        """
        Deactivate (and optionally erase) the user account.

        Matrix API: POST /_matrix/client/r0/account/deactivate
        Set erase_user=true to also erase all user data.
        """
        result = await self._request(
            "POST",
            "/account/deactivate",
            access_token=access_token,
            json_data={"erase_user": erase_user},
        )
        return result
    
    # ============================================================
    # Profile
    # ============================================================
    
    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """Get user profile (display name, avatar)."""
        result = await self._request("GET", f"/profile/{user_id}")
        return {
            "user_id": user_id,
            "displayname": result.get("displayname"),
            "avatar_url": result.get("avatar_url"),
        }
    
    async def set_display_name(
        self, access_token: str, user_id: str, display_name: str
    ) -> None:
        """Set user's display name."""
        await self._request(
            "PUT",
            f"/profile/{user_id}/displayname",
            access_token=access_token,
            json_data={"displayname": display_name},
        )
    
    # ============================================================
    # Rooms
    # ============================================================
    
    async def create_room(
        self,
        access_token: str,
        name: Optional[str] = None,
        topic: Optional[str] = None,
        invite: Optional[list[str]] = None,
        is_direct: bool = False,
        preset: str = "private_chat",
    ) -> dict[str, Any]:
        """Create a new room."""
        data: dict[str, Any] = {
            "preset": preset,
            "is_direct": is_direct,
        }
        if name:
            data["name"] = name
        if topic:
            data["topic"] = topic
        if invite:
            data["invite"] = invite
        
        result = await self._request(
            "POST", "/createRoom", access_token=access_token, json_data=data
        )
        return {
            "room_id": result["room_id"],
        }
    
    async def join_room(self, access_token: str, room_id_or_alias: str) -> dict[str, Any]:
        """Join a room by ID or alias."""
        # URL encode room ID for path
        encoded = room_id_or_alias.replace("#", "%23").replace("!", "%21")
        result = await self._request(
            "POST", f"/join/{encoded}", access_token=access_token
        )
        return {
            "room_id": result["room_id"],
        }
    
    async def leave_room(self, access_token: str, room_id: str) -> None:
        """Leave a room."""
        encoded = room_id.replace("!", "%21")
        await self._request(
            "POST", f"/rooms/{encoded}/leave", access_token=access_token
        )
    
    async def get_joined_rooms(self, access_token: str) -> list[str]:
        """Get list of joined room IDs."""
        result = await self._request("GET", "/joined_rooms", access_token=access_token)
        return result.get("joined_rooms", [])
    
    async def get_room_info(
        self, access_token: str, room_id: str
    ) -> dict[str, Any]:
        """Get room name and topic."""
        encoded = room_id.replace("!", "%21")
        
        # Get room state for name and topic
        try:
            state = await self._request(
                "GET", f"/rooms/{encoded}/state", access_token=access_token
            )
        except MatrixError as exc:
            if exc.http_status == 403:
                # Not in room or no permission
                return {"room_id": room_id, "name": None, "topic": None}
            raise
        
        name = None
        topic = None
        for event in state:
            if event.get("type") == "m.room.name":
                name = event.get("content", {}).get("name")
            elif event.get("type") == "m.room.topic":
                topic = event.get("content", {}).get("topic")
        
        return {
            "room_id": room_id,
            "name": name,
            "topic": topic,
        }
    
    # ============================================================
    # Messages
    # ============================================================
    
    async def send_message(
        self,
        access_token: str,
        room_id: str,
        body: str,
        msgtype: str = "m.text",
    ) -> dict[str, Any]:
        """Send a message to a room."""
        encoded = room_id.replace("!", "%21")
        
        # Generate transaction ID for idempotency
        import uuid
        txn_id = str(uuid.uuid4())
        
        data = {
            "msgtype": msgtype,
            "body": body,
        }
        
        result = await self._request(
            "PUT",
            f"/rooms/{encoded}/send/m.room.message/{txn_id}",
            access_token=access_token,
            json_data=data,
        )
        return {
            "event_id": result["event_id"],
        }
    
    async def get_room_messages(
        self,
        access_token: str,
        room_id: str,
        limit: int = 50,
        from_token: Optional[str] = None,
        direction: str = "b",  # 'b' = backwards (newest first)
    ) -> dict[str, Any]:
        """Get messages from a room."""
        encoded = room_id.replace("!", "%21")
        
        params: dict[str, Any] = {
            "limit": limit,
            "dir": direction,
        }
        if from_token:
            params["from"] = from_token
        
        result = await self._request(
            "GET",
            f"/rooms/{encoded}/messages",
            access_token=access_token,
            params=params,
        )
        
        # Filter to only message events
        messages = []
        for event in result.get("chunk", []):
            if event.get("type") == "m.room.message":
                content = event.get("content", {})
                messages.append({
                    "event_id": event.get("event_id"),
                    "sender": event.get("sender"),
                    "timestamp": event.get("origin_server_ts"),
                    "msgtype": content.get("msgtype"),
                    "body": content.get("body"),
                })
        
        return {
            "messages": messages,
            "start": result.get("start"),
            "end": result.get("end"),
        }
    
    # ============================================================
    # Sync (Long-polling for real-time updates)
    # ============================================================
    
    async def sync(
        self,
        access_token: str,
        since: Optional[str] = None,
        timeout_ms: int = 30000,
        full_state: bool = False,
    ) -> dict[str, Any]:
        """
        Long-polling sync for real-time updates.
        
        This is the core mechanism for receiving new messages and room updates.
        Blocks until there's new data or timeout.
        """
        params: dict[str, Any] = {
            "timeout": timeout_ms,
            "full_state": "true" if full_state else "false",
        }
        if since:
            params["since"] = since
        
        result = await self._request(
            "GET", "/sync", access_token=access_token, params=params
        )
        
        # Simplify the sync response for Flutter
        rooms = result.get("rooms", {})
        join_rooms = rooms.get("join", {})
        
        simplified_rooms = {}
        for room_id, room_data in join_rooms.items():
            timeline = room_data.get("timeline", {})
            state = room_data.get("state", {})
            
            # Extract new messages from timeline
            new_messages = []
            for event in timeline.get("events", []):
                if event.get("type") == "m.room.message":
                    content = event.get("content", {})
                    new_messages.append({
                        "event_id": event.get("event_id"),
                        "sender": event.get("sender"),
                        "timestamp": event.get("origin_server_ts"),
                        "msgtype": content.get("msgtype"),
                        "body": content.get("body"),
                    })
            
            simplified_rooms[room_id] = {
                "new_messages": new_messages,
                "limited": timeline.get("limited"),
                "prev_batch": timeline.get("prev_batch"),
            }
        
        return {
            "next_batch": result["next_batch"],
            "rooms": simplified_rooms,
        }


# Singleton instance
_matrix_client: Optional[MatrixClient] = None


def get_matrix_client() -> MatrixClient:
    """Get or create Matrix client singleton."""
    global _matrix_client
    if _matrix_client is None:
        from config import get_settings
        settings = get_settings()
        _matrix_client = MatrixClient(base_url=settings.matrix.base_url)
    return _matrix_client


def set_matrix_client(client: MatrixClient) -> None:
    """Set Matrix client singleton (for testing)."""
    global _matrix_client
    _matrix_client = client
