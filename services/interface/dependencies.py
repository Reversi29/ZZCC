"""FastAPI dependency injection functions (avoids circular imports)."""
from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import Header, HTTPException

from modules.nebula_client import get_client

# ============================================================
# Auth
# ============================================================
API_KEY = "secret-key-change-me"


def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    """Raise 403 if the X-API-Key header doesn't match."""
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
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
    """FastAPI Depends — yields a NebulaGraph session (cleanup after request)."""
    client = get_client()
    cm = client.session_with(
        host=nebula_host,
        port=nebula_port,
        user=nebula_user,
        password=nebula_password,
    )
    sess = await asyncio.to_thread(cm.__enter__)
    try:
        yield sess
    finally:
        await asyncio.to_thread(cm.__exit__, None, None, None)
