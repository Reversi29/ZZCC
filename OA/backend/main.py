"""main.py — FastAPI 应用入口（SQLAlchemy 持久化）"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from config import get_settings

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import init_db
from logging_config import RequestLogMiddleware, logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✓ 数据库表已创建 / 更新")
    _seed_default_thresholds()
    _seed_default_departments()
    print("✓ 默认审批阈值已初始化")
    print("✓ 默认部门已初始化")
    yield


def _seed_default_departments():
    from routers._org import seed_default_departments
    from database import SessionLocal
    db = SessionLocal()
    try:
        seed_default_departments(db)
    except Exception as e:
        print(f"⚠ 部门种子失败: {e}")
    finally:
        db.close()


def _seed_default_thresholds():
    """首次启动时自动写入默认审批阈值（幂等，已有配置不覆盖）"""
    from database import SessionLocal, ApprovalRule
    from services.auto_approval import (
        save_threshold, ApprovalThreshold, DEFAULT_THRESHOLDS,
    )
    db = SessionLocal()
    try:
        # 直接查 DB，绕过 list_thresholds 的自动补充逻辑
        existing = {r.doctype for r in db.query(ApprovalRule)\
                    .filter_by(approver_role="auto_approve").all()}
        for default in DEFAULT_THRESHOLDS:
            if default["doctype"] not in existing:
                save_threshold(db, ApprovalThreshold(**default))
                print(f"  + 种子: {default['doctype']} (amount≤{default['auto_approve_amount']})")
    finally:
        db.close()


app = FastAPI(
    title="ZZCC OA API",
    version="1.0.0",
    description="ZZCC 企业 OA 系统后端（SQLAlchemy + SQLite，兼容 ERPNext v15 REST 协议）",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── 结构化日志中间件 ─────────────────────────────────────────
app.add_middleware(RequestLogMiddleware)

# CORS：允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 审计日志中间件：自动记录写操作 ──
AUDIT_EXCLUDE = {"/api/auth/login", "/api/auth/oidc/login", "/api/auth/oidc/callback", "/api/status", "/docs", "/openapi.json", "/redoc"}
@app.middleware("http")
async def _audit_middleware(request, call_next):
    if request.method == "OPTIONS" or request.url.path in AUDIT_EXCLUDE or request.url.path.startswith("/assets"):
        return await call_next(request)
    # 只记录写操作
    is_write = request.method in ("POST","PUT","PATCH","DELETE")
    body_str = ""
    if is_write and request.method in ("POST","PUT","PATCH"):
        try:
            raw = await request.body()
            body_str = raw.decode("utf-8")[:200]
        except:
            pass
    resp = await call_next(request)
    if is_write:
        try:
            import jwt
            from config import get_settings
            from database import SessionLocal
            from routers.audit_log import AuditEntry
            auth = request.headers.get("Authorization","")
            token = auth.replace("Bearer ","") if auth else ""
            username = "anonymous"
            if token:
                try:
                    payload = jwt.decode(token, get_settings().JWT_SECRET_KEY, algorithms=["HS256"])
                    username = str(payload.get("sub", "anonymous"))[:80]
                except Exception:
                    pass
            module = request.url.path.replace("/api/","").split("/")[0]
            detail = (request.url.path + (" " + body_str[:200] if body_str else ""))[:500]
            db = SessionLocal()
            try:
                db.add(AuditEntry(
                    username=username,
                    action=request.method,
                    module=module,
                    detail=detail,
                    ip=request.client.host if request.client else "",
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"audit middleware error: {e}")
    return resp



# ── API 限流（P3.16）──────────────────────────────────────────
from middleware.ratelimit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)


# ── 健康检查 ──────────────────────────────────────────────────
@app.get("/api/status")
def status():
    return {
        "status": "ok",
        "version": "1.0.0",
        "persistence": get_settings().DATABASE_URL.split("+")[0] if "+" in get_settings().DATABASE_URL else "sqlite",
    }


# ── 全局错误处理 ──────────────────────────────────────────────
@app.exception_handler(Exception)
def global_error(req: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── 路由注册（懒加载避免循环导入）─────────────────────────────
def _register():
    from fastapi import APIRouter
    router_files = [
        "routers.auth",       # 认证路由（必须排第一，保护其他路由）
        "routers.auth_oidc",  # P3.15 SSO（Casdoor OIDC，JIT 建号）
        "routers.users",      # 用户管理（admin CRUD）
        "routers.crm",
        "routers.project",
        "routers.procurement",
        "routers.finance",
        "routers.compliance",
        "routers.customer_service",
        "routers.quality",
        "routers.hr",
        "routers.org",      # 组织架构（Department CRUD）
        "routers.stock",
        "routers.workflow",
        "routers.ai",
        "routers.export",
        "routers.approval",
        "routers.notifications",
        "routers.search",
        "routers.dashboard",
        "routers.module_toggle",
        "routers.audit_log",
        "routers.performance",
        "routers.recruitment",
        "routers.notification_settings",
        "routers.analytics",
        "routers.budget",
        "routers.approval_rules",
        "routers.announcements",
        "routers.calendar",
        "routers.directory",
        "routers.daily_reports",
        "routers.meetings",
        "routers.form_designer",
        "routers.netdrive",
    ]
    for f in router_files:
        mod = __import__(f, fromlist=["router"])
        app.include_router(mod.router)


_register()


# ── 禁缓存中间件（开发期：确保浏览器不缓存旧版 index.html）─────
@app.middleware("http")
async def _no_cache(request, call_next):
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith(".html"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


# ── 静态前端（同源部署：API 在 /api/，前端在 /）───────────────
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _P
_FRONTEND = _P(__file__).parent.parent / "frontend"
if (_FRONTEND / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
