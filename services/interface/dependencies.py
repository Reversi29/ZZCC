"""
Shared FastAPI dependencies.
Both main.py and routers import from here to avoid circular imports.

Provides:
- get_client()     — NebulaClient singleton accessor
- get_session()    — FastAPI Depends() for NebulaGraph session
- require_api_key()— FastAPI Depends() for API-key auth
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from config import get_settings
from modules.nebula_client import NebulaClient

# ============================================================
# Client singleton (initialized by main.py lifespan)
# ============================================================
_client: NebulaClient | None = None


def get_client() -> NebulaClient:
    if _client is None:
        raise RuntimeError("Nebula client not initialized")
    return _client


def set_client(client: NebulaClient) -> None:
    """Called by main.py lifespan to publish the singleton."""
    global _client
    _client = client


# ============================================================
# Auth
# ============================================================
async def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Return empty string if auth disabled, else raise 401."""
    settings = get_settings()
    if not settings.api_key_set:
        return ""
    if x_api_key != settings.api.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return x_api_key


# ============================================================
# Session
# ============================================================
async def get_session(
    nebula_host: Annotated[str | None, Header(alias="X-Nebula-Host")] = None,
    nebula_port: Annotated[int | None, Header(alias="X-Nebula-Port")] = None,
    nebula_user: Annotated[str | None, Header(alias="X-Nebula-User")] = None,
    nebula_password: Annotated[str | None, Header(alias="X-Nebula-Password")] = None,
):
    """FastAPI Depends — returns a NebulaGraph session."""
    return get_client().session_with(
        host=nebula_host,
        port=nebula_port,
        user=nebula_user,
        password=nebula_password,
    )
