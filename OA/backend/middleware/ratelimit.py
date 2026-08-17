"""
API 限流中间件（P3.16）

- 默认按客户端 IP 限流（全局 N 次/分钟）
- 登录接口单独更严格的限流（防暴力破解，与 auth 的登录锁定 423 互补）
- 真实部署在反向代理后时，优先取 X-Forwarded-For / X-Real-IP
- 限流阈值可通过环境变量在运行时调整（无需重建镜像）

部署调优（环境变量）：
  RATELIMIT_DEFAULT=120    全局每 IP 每分钟请求数
  RATELIMIT_WINDOW=60      全局窗口（秒）
  RATELIMIT_LOGIN=20       登录接口每 IP 每分钟次数
  RATELIMIT_LOGIN_WINDOW=60 登录窗口（秒）
"""
import os
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

LOGIN_PATH = "/api/auth/login"


class RateLimitMiddleware(BaseHTTPMiddleware):
    # 单进程单 app：所有实例共享同一限流桶（key -> deque[timestamps]）
    _buckets: dict = defaultdict(deque)

    def __init__(
        self,
        app,
        default_limit: int = 120,
        window: int = 60,
        login_limit: int = 20,
        login_window: int = 60,
    ):
        super().__init__(app)
        self.default_limit = default_limit
        self.window = window
        self.login_limit = login_limit
        self.login_window = login_window

    # ── 配置读取（支持运行时通过环境变量调整）────────────────
    def _limits(self):
        default = int(os.getenv("RATELIMIT_DEFAULT", self.default_limit))
        window = int(os.getenv("RATELIMIT_WINDOW", self.window))
        login = int(os.getenv("RATELIMIT_LOGIN", self.login_limit))
        login_window = int(os.getenv("RATELIMIT_LOGIN_WINDOW", self.login_window))
        return default, window, login, login_window

    @staticmethod
    def _client_ip(request: Request) -> str:
        fwd = request.headers.get("X-Forwarded-For")
        if fwd:
            return fwd.split(",")[0].strip()
        real = request.headers.get("X-Real-IP")
        if real:
            return real
        return request.client.host if request.client else "unknown"

    def _admit(self, key: str, limit: int, window: int):
        """返回 (是否放行, 建议重试秒数)"""
        now = time.time()
        dq = self._buckets[key]
        while dq and dq[0] <= now - window:
            dq.popleft()
        if len(dq) >= limit:
            retry = int(window - (now - dq[0])) + 1
            return False, max(retry, 1)
        dq.append(now)
        return True, 0

    async def dispatch(self, request: Request, call_next):
        # 测试 / 运维可通过环境变量临时关闭限流
        if os.getenv("RATELIMIT_ENABLED", "true").lower() in ("false", "0", "no", "off"):
            return await call_next(request)
        default, window, login, login_window = self._limits()
        ip = self._client_ip(request)
        path = request.url.path.rstrip("/")

        if path.endswith(LOGIN_PATH):
            ok, retry = self._admit(f"login:{ip}", login, login_window)
            if not ok:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "登录尝试过于频繁，请稍后再试"},
                    headers={"Retry-After": str(retry)},
                )
        else:
            ok, retry = self._admit(f"ip:{ip}", default, window)
            if not ok:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后再试"},
                    headers={"Retry-After": str(retry)},
                )
        return await call_next(request)
