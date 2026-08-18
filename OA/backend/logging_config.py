"""ZZCC OA — 结构化日志配置（P4.19）

- JSON 格式日志输出到 stdout（容器环境收集）
- 文件日志可选（本地开发）
- 每个请求自动附加 request_id / user / method / path / duration
"""
import logging
import sys
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class JsonFormatter(logging.Formatter):
    """输出 JSON 格式日志行，便于 ELK/Loki 收集"""

    def format(self, record: logging.LogRecord) -> str:
        import datetime as dt
        import json

        msg = {
            "ts": dt.datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            msg.update(record.extra_fields)
        if record.exc_info:
            msg["exc"] = self.formatException(record.exc_info)
        return json.dumps(msg, ensure_ascii=False, default=str)


def _build_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    log = logging.getLogger(name)
    log.setLevel(level)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter())
        log.addHandler(h)
        log.propagate = False
    return log


# 全局 logger（main.py / routers 均可 import）
logger = _build_logger("zzcc.oa")


# ── 请求日志中间件 ────────────────────────────────────────────
class RequestLogMiddleware(BaseHTTPMiddleware):
    """每个请求结束时打印结构化日志"""

    async def dispatch(self, req: Request, call_next) -> Response:
        request_id = req.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        start = time.perf_counter()
        user: str = "anonymous"

        # 延迟 import，避免 conftest patch 之前触发 DB 连接
        try:
            token = req.headers.get("Authorization", "")
            if token.startswith("Bearer "):
                token = token[7:]
                if token:
                    from config import get_settings
                    import jwt

                    s = get_settings()
                    try:
                        payload = jwt.decode(token, s.JWT_SECRET_KEY, algorithms=["HS256"])
                        user = payload.get("sub", payload.get("username", "unknown"))
                    except Exception:
                        pass
        except Exception:
            pass

        resp = await call_next(req)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        extra = {
            "request_id": request_id,
            "method": req.method,
            "path": req.url.path,
            "status": resp.status_code,
            "duration_ms": duration_ms,
            "user": user,
            "ip": req.client.host if req.client else "-",
        }
        log = _build_logger("zzcc.oa.request")
        log.log(
            logging.INFO if resp.status_code < 400 else logging.WARNING,
            f"{req.method} {req.url.path} → {resp.status_code} ({duration_ms}ms) [{user}]",
            extra={"extra_fields": extra},
        )
        resp.headers["X-Request-ID"] = request_id
        return resp
