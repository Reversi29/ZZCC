"""
NebulaGraph Interface — FastAPI service (refactored).

Entry point. Application wiring lives here; business logic in routers/services.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import json
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from starlette import status

from config import get_settings
from dependencies import get_client
from middleware.rate_limit import setup_middleware
from modules.nebula_client import NebulaClient, set_client

_log = structlog.get_logger()


async def _init_plugin_system(app: FastAPI) -> None:
    """初始化插件系统：建表 + 加载已注册插件 + 扫描新插件。

    表结构使用 PostgreSQL 方言（asyncpg）。表不存在时静默返回，不阻塞主流程。
    """
    try:
        from plugins import registry as _registry, event_bus as _event_bus
        from plugins.loader import scan_and_load_plugins
        from services.db import managed_session
        from sqlalchemy import text

        # 1. 建表（idempotent）
        async with managed_session() as db:
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS plugin_registry (
                    id VARCHAR(64) PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    version VARCHAR(32) NOT NULL,
                    author VARCHAR(64) DEFAULT '',
                    description TEXT,
                    manifest JSONB,
                    status VARCHAR(16) DEFAULT 'installed',
                    config JSONB,
                    installed_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS plugin_event_log (
                    id BIGSERIAL PRIMARY KEY,
                    plugin_id VARCHAR(64) NOT NULL,
                    event_name VARCHAR(128) NOT NULL,
                    payload JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await db.execute(text("CREATE INDEX IF NOT EXISTS idx_plugin_evt_pid ON plugin_event_log (plugin_id)"))
            await db.execute(text("CREATE INDEX IF NOT EXISTS idx_plugin_evt_name ON plugin_event_log (event_name)"))
            await db.commit()

        # Plugin marketplace metadata is intentionally filesystem-backed in Phase 3.
        try:
            from routers.plugin_marketplace import _market_dir
            market_dir = _market_dir()
            _log.info("plugin_market_ready", path=str(market_dir))
        except Exception as market_exc:
            _log.warning("plugin_market_init_failed", error=str(market_exc))

        # 2. 从 DB 恢复注册信息到内存
        db_rows = await _registry.load_from_db()
        for row in db_rows:
            try:
                manifest = json.loads(row.get("manifest") or "{}") if isinstance(row.get("manifest"), str) else row.get("manifest") or {}
                config = json.loads(row.get("config") or "{}") if isinstance(row.get("config"), str) else row.get("config") or {}
                from plugins.registry import PluginMetadata, PluginStatus
                meta = PluginMetadata(
                    id=row["id"], name=row["name"], version=row["version"],
                    author=row.get("author", "") or "",
                    description=row.get("description", "") or "",
                    manifest=manifest, status=PluginStatus(row.get("status", "installed")),
                    config=config,
                )
                _registry.register(meta)
            except Exception as exc:
                _log.warning("plugin_row_parse_failed", plugin_id=row.get("id"), error=str(exc))

        # 3. 扫描目录并加载插件（新插件从 DB 恢复 config）
        loaded = await scan_and_load_plugins(app, _registry, _event_bus)
        _log.info("plugins_loaded", count=len(loaded))
    except Exception as exc:
        _log.error("plugin_system_init_failed", error=str(exc))


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

    # Ensure chat user/room/message tables exist (idempotent)
    try:
        from services.user_db import init_schema as chat_init_schema
        await chat_init_schema()
    except Exception as exc:
        _log.error("chat_schema_init_failed", error=str(exc))

    # Plugin system init (best-effort; failure is non-fatal)
    try:
        await _init_plugin_system(app)
    except Exception as exc:
        _log.error("plugin_system_init_failed", error=str(exc))

    # Brain AI system init (best-effort; failure is non-fatal)
    try:
        from services.db import managed_session
        from services.brain import init_brain_tables, init_builtin_rules
        async with managed_session() as db:
            await init_brain_tables(db)
            await db.commit()
        rule_count = init_builtin_rules()
        _log.info("brain_system_ready", rules=rule_count)
    except Exception as exc:
        _log.error("brain_system_init_failed", error=str(exc))

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
    from routers import spaces, tags, edge_types, edges, vertices, query, deploy, import_csv, documents, chat, chat_user, auth, plugins as plugins_router, plugin_marketplace as plugin_marketplace_router, brain as brain_router

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
    app.include_router(chat.router, prefix=v1)
    app.include_router(chat_user.router, prefix=v1)
    app.include_router(auth.router, prefix=v1)
    app.include_router(plugins_router.router, prefix=v1)
    app.include_router(plugin_marketplace_router.router, prefix=v1)
    app.include_router(brain_router.router, prefix=v1)

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
