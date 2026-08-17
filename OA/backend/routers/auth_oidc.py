"""P3.15 SSO — Casdoor OIDC 集成（Authorization Code 流程）

流程：
1. GET /api/auth/oidc/login → 302 到 Casdoor authorize（带 state 防 CSRF）
2. 用户在 Casdoor 完成登录 → 302 回 /api/auth/oidc/callback?code=...&state=...
3. callback：验 state → code 换 token → 验 id_token（JWKS RS256）
   → JIT 建号（首次 SSO 登录自动创建 OA 账号，用户决策 B）
   → 签 OA JWT → 返回 HTML 注入 localStorage 并跳转首页

环境变量可覆盖（后续对接任意 OIDC IdP 只需改配置，代码零改动）：
- OIDC_ISSUER / OIDC_CLIENT_ID / OIDC_CLIENT_SECRET / OIDC_REDIRECT_URI

设计要点：
- 本地账号密码登录保留（双轨），SSO 为新增通道
- JIT 用户 role=user、status=active（Casdoor 已完成身份认证，不再走注册审批）
- JIT 用户密码为随机不可知串 → 只能 SSO 登录，无法本地密码登录
- 若 Casdoor email 与 OA 已有用户名相同 → 直接绑定登录（不重复建号）
"""
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db, User
from routers.auth import _hash_pw, create_access_token

router = APIRouter()

# ── 配置（env 可覆盖）──────────────────────────────────────
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "http://localhost:8004")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "894cb728becce8983061")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "cee48f367d759e19c7b7c09f074f4958281bb368")
OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "http://localhost:8003/api/auth/oidc/callback")

OIDC_AUTH_URL = f"{OIDC_ISSUER}/login/oauth/authorize"
OIDC_TOKEN_URL = f"{OIDC_ISSUER}/api/login/oauth/access_token"
OIDC_JWKS_URL = f"{OIDC_ISSUER}/.well-known/jwks"

_STATE_TTL = 600   # state 10 分钟
_states: dict[str, float] = {}   # state -> expiry（单实例内存；多实例部署需换 Redis）
_JWKS_TTL = 300    # JWKS 缓存 5 分钟
_jwks_cache: dict = {"keys": None, "at": 0.0}


# ── JWKS / id_token 验证 ──────────────────────────────────────
def _get_jwks_keys() -> list[dict]:
    """获取并缓存 IdP JWKS（5 分钟）"""
    now = time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["at"] < _JWKS_TTL:
        return _jwks_cache["keys"]
    with httpx.Client(timeout=10) as c:
        r = c.get(OIDC_JWKS_URL)
        r.raise_for_status()
    keys = r.json().get("keys", [])
    if not keys:
        raise HTTPException(status_code=502, detail="OIDC: IdP 未返回 JWKS 密钥")
    _jwks_cache["keys"] = keys
    _jwks_cache["at"] = now
    return keys


def _verify_id_token(id_token: str) -> dict:
    """验证 id_token（RS256 + JWKS），返回 claims"""
    keys = _get_jwks_keys()
    # 先无签名解析拿 kid，选择匹配密钥
    unverified = jwt.decode(id_token, options={"verify_signature": False})
    kid = unverified.get("kid")
    key = next((k for k in keys if k.get("kid") == kid), None) if kid else None
    if key is None:
        key = keys[0]
    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
    return jwt.decode(
        id_token,
        public_key,
        algorithms=["RS256"],
        audience=OIDC_CLIENT_ID,
        issuer=OIDC_ISSUER,
    )


def _exchange_code(code: str) -> dict:
    """授权码换 token（抽出便于测试 mock）"""
    with httpx.Client(timeout=15) as c:
        r = c.post(
            OIDC_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": OIDC_CLIENT_ID,
                "client_secret": OIDC_CLIENT_SECRET,
                "redirect_uri": OIDC_REDIRECT_URI,
            },
        )
        r.raise_for_status()
        return r.json()


# ── 路由 ──────────────────────────────────────────────────────
@router.get("/api/auth/oidc/login")
async def oidc_login():
    """SSO 入口：跳转 Casdoor 授权页"""
    state = secrets.token_urlsafe(16)
    _states[state] = time.time() + _STATE_TTL
    params = {
        "client_id": OIDC_CLIENT_ID,
        "redirect_uri": OIDC_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
    }
    return RedirectResponse(f"{OIDC_AUTH_URL}?{urlencode(params)}")


@router.get("/api/auth/oidc/callback")
async def oidc_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """回调：换 token → 验 id_token → JIT 建号 → 签发 OA JWT"""
    exp = _states.pop(state, None)
    if not exp or time.time() > exp:
        raise HTTPException(status_code=400, detail="OIDC: state 无效或已过期")

    try:
        tokens = _exchange_code(code)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"OIDC: token 交换失败: {e}")
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="OIDC: IdP 响应缺少 id_token")

    try:
        claims = _verify_id_token(id_token)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"OIDC: id_token 验证失败: {e}")

    sub = claims.get("sub", "")
    email = claims.get("email") or (f"{sub}@oidc" if sub else "")
    if not email:
        raise HTTPException(status_code=401, detail="OIDC: id_token 缺少 sub/email")
    name = claims.get("name") or claims.get("preferred_username") or email

    # JIT 建号：优先按 email，其次按 sub 绑定已有账号
    user = db.query(User).filter(User.username == email).first()
    if user is None and sub:
        user = db.query(User).filter(User.username == sub).first()
    if user is None:
        user = User(
            username=email,
            hashed_password=_hash_pw(secrets.token_urlsafe(24)),  # 随机不可知密码
            display_name=name,
            role="user",
            status="active",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.is_active or user.status != "active":
        raise HTTPException(status_code=403, detail="账号未激活，请联系管理员")

    token = create_access_token(user.username, user.display_name, user.role)
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>登录成功</title></head>
<body><script>
localStorage.setItem('oa_token', '{token}');
localStorage.setItem('oa_user', '{user.username}');
localStorage.setItem('oa_display_name', '{user.display_name}');
location.href = '/';
</script>登录成功，正在跳转…</body></html>"""
    return HTMLResponse(html)
