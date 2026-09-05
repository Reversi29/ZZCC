"""
Middleware: CORS, rate limiting, slow-request logger.
Uses Starlette's standard Middleware class (not BaseHTTPMiddleware) to
avoid the call_next exception-propagation bug in Starlette 1.x.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from starlette.types import ASGIApp, Receive, Scope, Send

from config import get_settings

_log = logging.getLogger(__name__)

# ============================================================
# SlowAPI limiter (optional)
# ============================================================
_limiter = None
_limiter_available = False

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    _limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    _limiter_available = True
except ImportError:
    pass


# ============================================================
# Slow-request logger — standard ASGI middleware
# ============================================================
class SlowRequestLoggerMiddleware:
    """Log requests slower than threshold_ms."""

    def __init__(self, app: ASGIApp, threshold_ms: int = 3000):
        self.app = app
        self.threshold_ms = threshold_ms

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.threshold_ms <= 0 or scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()

        async def wrapped_send(message: dict) -> None:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if elapsed_ms > self.threshold_ms:
                _log.warning(
                    "slow_request method=%s path=%s status=%s duration_ms=%s",
                    scope.get("method"),
                    scope.get("path"),
                    message.get("status", 0),
                    round(elapsed_ms, 1),
                )
            await send(message)

        await self.app(scope, receive, wrapped_send)


# ============================================================
# SlowAPI rate limiter — standard ASGI middleware
# ============================================================
class SlowAPIRateLimitMiddleware:
    """Rate limiting via SlowAPI as a standard ASGI middleware."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _limiter_available:
            await self.app(scope, receive, send)
            return

        from slowapi.errors import RateLimitExceeded

        # Get client IP from scope
        client_ip = scope.get("client", (None, None))[0] or "unknown"
        key = f"client_ip:{client_ip}"

        try:
            # Check rate limit synchronously
            _limiter._check_request_limit(
                key=key,
                request=None,
                token=None,
            )
        except RateLimitExceeded:
            from starlette.responses import Response

            response = Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ============================================================
# Apply all middleware to app
# ============================================================
def setup_middleware(app: ASGIApp) -> None:
    """Wire up CORS, optional rate limiting, and slow-request logging."""
    settings = get_settings()
    api_cfg = settings.api

    # CORS — use standard Starlette CORSMiddleware
    from starlette.middleware.cors import CORSMiddleware as _CORSMiddleware

    app.add_middleware(
        _CORSMiddleware,
        allow_origins=api_cfg.cors_origins,
        allow_credentials=api_cfg.cors_allow_credentials,
        allow_methods=api_cfg.cors_allow_methods,
        allow_headers=api_cfg.cors_allow_headers,
    )

    # Slow request logger
    if api_cfg.slow_request_threshold_ms > 0:
        app.add_middleware(
            SlowRequestLoggerMiddleware,
            threshold_ms=api_cfg.slow_request_threshold_ms,
        )

    # SlowAPI rate limiter
    if _limiter_available and api_cfg.rate_limit_enabled:
        from slowapi.middleware import SlowAPIMiddleware as _SlowAPIMiddleware
        from slowapi.errors import RateLimitExceeded
        from slowapi import _rate_limit_exceeded_handler

        app.state.limiter = _limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(_SlowAPIMiddleware)
