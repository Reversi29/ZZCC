"""
NebulaGraph Interface — FastAPI service (refactored).

Entry point. Application wiring lives here; business logic in routers/services.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from starlette import status

from config import get_settings
from dependencies import get_client
from middleware.rate_limit import setup_middleware
from modules.nebula_client import NebulaClient

_log = structlog.get_logger()


# ============================================================
# Lifespan
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    _log.info("nebula_connect", host=settings.nebula.host, port=settings.nebula.port)

    client = NebulaClient(
        host=settings.nebula.host,
        port=settings.nebula.port,
        user=settings.nebula.user,
        password=settings.nebula.password,
    )

    if not client.init_pool():
        _log.error("nebula_pool_init_failed")
        raise RuntimeError(
            f"NebulaGraph connection failed: {settings.nebula.host}:{settings.nebula.port}"
        )

    set_client(client)          # publish singleton to all routers
    _log.info("nebula_pool_ready")

    yield

    client.close()
    _log.info("nebula_pool_closed")


# ============================================================
# App factory
# ============================================================
def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.api.api_version,
        lifespan=lifespan,
    )

    # Global exception handler — fixes Starlette 1.x + BaseHTTPMiddleware
    # where HTTPExceptions raised inside middleware layers sometimes
    # propagate as 500 instead of being caught.
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc: Exception):
        """Convert known exceptions to appropriate HTTP responses; log unknown ones."""
        # Unwrap cause chain
        inner = getattr(exc, '__cause__', None) or exc
        # ValueError → 400
        if isinstance(inner, ValueError):
            return JSONResponse(status_code=400, content={"detail": str(inner)})
        # HTTPException from cause chain → propagate
        if isinstance(inner, HTTPException):
            return JSONResponse(status_code=inner.status_code, content={"detail": inner.detail})
        # Unwrap ExceptionGroup (Starlette 1.x BaseHTTPMiddleware wrapping)
        if hasattr(inner, 'exceptions'):
            for sub in getattr(inner, 'exceptions', []):
                if isinstance(sub, HTTPException):
                    return JSONResponse(status_code=sub.status_code, content={"detail": sub.detail})
                if isinstance(sub, ValueError):
                    return JSONResponse(status_code=400, content={"detail": str(sub)})
        # Unknown exception — log full traceback, return generic 500
        _log.exception("unhandled_exception", exc=str(exc), path=str(request.url.path) if hasattr(request, "url") else None)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    setup_middleware(app)

    # Import routers (they import from dependencies — no circular dependency)
    from routers import spaces, tags, edge_types, edges, vertices, query, deploy, import_csv, documents

    v1 = "/api/v1"
    app.include_router(spaces.router, prefix=v1)
    app.include_router(tags.router, prefix=v1)
    app.include_router(edge_types.router, prefix=v1)
    app.include_router(edges.router, prefix=v1)
    app.include_router(vertices.router, prefix=v1)
    app.include_router(query.router, prefix=v1)
    app.include_router(deploy.router, prefix=v1)
    app.include_router(import_csv.router, prefix=v1)
    app.include_router(documents.router, prefix=v1)
    app.include_router(documents.convert_router, prefix=v1)

    # Root
    @app.get("/")
    async def root():
        return {
            "service": settings.app_name,
            "version": settings.api.api_version,
            "docs": "/docs",
        }

    # Full health check — graceful: db/redis failures are non-fatal
    @app.get("/health")
    async def health():
        from dependencies import get_client

        nebula = "unknown"
        try:
            with get_client().session() as sess:
                get_client()._run(sess, "SHOW HOSTS;")
            nebula = "connected"
        except Exception as exc:
            nebula = f"error: {exc}"
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "degraded", "nebula": nebula},
            )

        # DB and Redis are optional — health_check() returns dict with status
        try:
            from services.db import health_check as pg_health
            pg = await pg_health()
        except Exception as exc:
            _log.error("health_db_crash", error=str(exc))
            pg = {"status": "degraded", "detail": str(exc)}

        try:
            from services.cache import health_check as redis_health
            redis = await redis_health()
        except Exception as exc:
            _log.error("health_redis_crash", error=str(exc))
            redis = {"status": "degraded", "detail": str(exc)}

        return {
            "status": "ok",
            "nebula": nebula,
            "postgres": pg,
            "redis": redis,
        }

    return app


app = create_app()

# Re-export for backwards compatibility (tests, etc.)
from dependencies import get_client, get_session, verify_api_key  # noqa: F401
from routers.import_csv import _coerce  # noqa: F401
