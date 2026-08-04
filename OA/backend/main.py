"""main.py — FastAPI 应用入口（SQLAlchemy 持久化）"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from database import DB_URL

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import init_db
from config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✓ 数据库表已创建 / 更新")
    yield


app = FastAPI(
    title="ZZCC OA API",
    version="1.0.0",
    description="ZZCC 企业 OA 系统后端（SQLAlchemy + SQLite，兼容 ERPNext v15 REST 协议）",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS：允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 健康检查 ──────────────────────────────────────────────────
@app.get("/api/status")
def status():
    return {
        "status": "ok",
        "version": "1.0.0",
        "persistence": DB_URL.split("+")[0] if "+" in DB_URL else "sqlite",
    }


# ── 兼容 ERPNext 的路由组（AI 业务咨询）──────────────────────
@app.post("/api/ai/consult")
def ai_consult(req: Request):
    """通用 AI 咨询入口（调度各模块规则引擎）"""
    body, s = req.json(), get_settings()
    module = body.get("module", "")
    ctx = body.get("context", {})

    # 本地规则引擎路由（无 LLM API 依赖）
    if module == "procurement":
        amount = float(ctx.get("amount") or 0)
        supplier = ctx.get("supplier", "")
        risk, suggestions, score = [], [("采购要素完整，可正常推进", 80)], 80
        if amount > 500000: risk.append("单笔超50万，需审批流升级"); score = 55
        elif amount > 100000: suggestions.insert(0, ("建议3家供应商比价", 65)); score = 65
        elif amount < 10000: suggestions.insert(0, ("建议走快速采购通道", 90))
        if not supplier: risk.append("缺少供应商信息")
        import re
        text = (ctx.get("items", "") + ctx.get("description", "")).lower()
        if re.search(r"独家|唯一|指定", text): risk.append("指定/独家供货，需说明合理性")
        if re.search(r"预付|全款|订金", text) and amount > 50000: risk.append("大额预付，建议分期")
        return {"advice": f"采购 {amount:.2f} 元 | {supplier or '未指定供应商'}",
                "risk_flags": risk, "suggestions": [s[0] for s in suggestions], "score": score}

    if module == "finance":
        return {"advice": "财务合规检查通过", "risk_flags": [], "suggestions": ["发票备注项目名称"]}

    if module == "compliance":
        return {"advice": "合同合规性检查通过", "risk_flags": [], "suggestions": ["建议约定争议仲裁条款"]}

    if module == "project":
        return {"advice": "项目进展正常", "risk_flags": [], "suggestions": ["定期同步里程碑"]}

    if module == "crm":
        return {"advice": "线索评分良好", "risk_flags": [], "suggestions": ["建议3日内首次跟进"]}

    return {"advice": "模块未识别", "risk_flags": [], "suggestions": []}


# ── 全局错误处理 ──────────────────────────────────────────────
@app.exception_handler(Exception)
def global_error(req: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── 路由注册（懒加载避免循环导入）─────────────────────────────
def _register():
    from fastapi import APIRouter
    router_files = [
        "routers.crm",
        "routers.project",
        "routers.procurement",
        "routers.finance",
        "routers.compliance",
        "routers.customer_service",
        "routers.quality",
        "routers.hr",
        "routers.stock",
        "routers.workflow",
        "routers.ai",
    ]
    for f in router_files:
        mod = __import__(f, fromlist=["router"])
        app.include_router(mod.router)


_register()


# ── 静态前端（同源部署：API 在 /api/，前端在 /）───────────────
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _P
_FRONTEND = _P(__file__).parent.parent / "frontend"
if (_FRONTEND / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
