"""auth.py — 认证路由（JWT Bearer Token + DB User）"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Header, Body
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
import jwt
import hashlib

from database import get_db, User
from config import get_settings

router = APIRouter(prefix="/api/auth", tags=["认证"])

# ── 密钥（从 config.py 读取 .env，生产必须改）─────────────────────
ACCESS_TOKEN_EXPIRE_HOURS = 24   # 非敏感配置，可直接写死或改为 env

# ── 安全状态（demo 用内存字典；生产应换 Redis）──────────────
TOKEN_BLACKLIST: dict[str, float | None] = {}   # jti -> 过期时间（失效的 token）
_LOGIN_FAILS: dict[str, dict] = {}                # username -> {count, lock_until}
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
_ACTIVE_SESSIONS: dict[str, str] = {}             # jti -> username（活跃会话，demo 用内存）

# ── Pydantic 模型 ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str

    @field_validator("username")
    @classmethod
    def username_len(cls, v):
        if len(v) < 3:
            raise ValueError("用户名至少3个字符")
        if not v.isalnum():
            raise ValueError("用户名只能包含字母和数字")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("密码至少6个字符")
        return v

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds

class CurrentUser(BaseModel):
    username: str
    display_name: str
    role: str
    status: str = "active"


# ── 密码 ──────────────────────────────────────────────────────
def _hash_pw(password: str) -> str:
    """Hash password using salt from settings (lazy eval)."""
    from config import get_settings
    salt = bytes.fromhex(get_settings().PASSWORD_SALT_HEX)
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000).hex()

def _verify_pw(password: str, stored_hash: str) -> bool:
    return _hash_pw(password) == stored_hash

def create_access_token(username: str, display_name: str, role: str = "user") -> str:
    from config import get_settings
    payload = {
        "sub": username,
        "display_name": display_name,
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, get_settings().JWT_SECRET_KEY, algorithm="HS256")


# ── OAuth2 Bearer 依赖 ────────────────────────────────────────
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def get_current_user(
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """
    两套认证并行：
    1. Bearer Token（JWT）
    2. X-API-Key（兼容旧接口）
    """
    if token:
        try:
            payload = jwt.decode(token, get_settings().JWT_SECRET_KEY, algorithms=["HS256"])
            if "jti" in payload and payload["jti"] in TOKEN_BLACKLIST:
                raise HTTPException(status_code=401, detail="Token 已失效，请重新登录")
            return CurrentUser(
                username=payload["sub"],
                display_name=payload["display_name"],
                role=payload.get("role", "user"),
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token 已过期，请重新登录")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="无效的 Token")

    if api_key == get_settings().API_KEY:
        return CurrentUser(username="api-key-user", display_name="API 用户", role="api")

    raise HTTPException(
        status_code=401,
        detail="未认证，请先登录（POST /api/auth/login）或提供有效的 X-API-Key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _check_lock(username: str):
    f = _LOGIN_FAILS.get(username)
    if f and f["lock_until"] and f["lock_until"] > time.time():
        remain = int((f["lock_until"] - time.time()) / 60) + 1
        raise HTTPException(status_code=423, detail=f"账户已锁定，请 {remain} 分钟后重试")


def _record_fail(username: str):
    f = _LOGIN_FAILS.setdefault(username, {"count": 0, "lock_until": 0.0})
    f["count"] += 1
    if f["count"] >= MAX_FAILS:
        f["lock_until"] = time.time() + LOCK_SECONDS
        f["count"] = 0


def _reset_fail(username: str):
    _LOGIN_FAILS.pop(username, None)


def _register_session(token: str, username: str):
    """记录活跃会话（jti -> username）"""
    try:
        payload = jwt.decode(token, get_settings().JWT_SECRET_KEY, algorithms=["HS256"])
        jti = payload.get("jti")
        if jti:
            _ACTIVE_SESSIONS[jti] = username
    except jwt.PyJWTError:
        pass


def _blacklist_token(authorization: str | None):
    """将当前 token 的 jti 加入黑名单并从活跃会话移除（登出 / 改密后失效）"""
    raw = authorization[len("Bearer "):] if authorization and authorization.startswith("Bearer ") else None
    if not raw:
        return
    try:
        payload = jwt.decode(raw, get_settings().JWT_SECRET_KEY, algorithms=["HS256"])
        jti = payload.get("jti")
        if jti:
            TOKEN_BLACKLIST[jti] = payload.get("exp")
            _ACTIVE_SESSIONS.pop(jti, None)
    except jwt.PyJWTError:
        pass


def _resolve_user(token: str | None, api_key: str | None, authorization: str | None) -> CurrentUser:
    """解析当前用户：Bearer JWT 优先，X-API-Key 兼容。任一有效即返回。"""
    raw = token
    if not raw and authorization and authorization.startswith("Bearer "):
        raw = authorization[len("Bearer "):]
    if raw:
        try:
            payload = jwt.decode(raw, get_settings().JWT_SECRET_KEY, algorithms=["HS256"])
            if "jti" in payload and payload["jti"] in TOKEN_BLACKLIST:
                raise HTTPException(status_code=401, detail="Token 已失效，请重新登录")
            return CurrentUser(
                username=payload["sub"],
                display_name=payload.get("display_name", ""),
                role=payload.get("role", "user"),
            )
        except jwt.PyJWTError:
            pass
    if api_key == get_settings().API_KEY:
        return CurrentUser(username="api-key-user", display_name="API 用户", role="api")
    raise HTTPException(
        status_code=401,
        detail="未认证，请提供有效的 Token 或 X-API-Key",
        headers={"WWW-Authenticate": "Bearer"},
    )



# --- Role constants ---
ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_FINANCE = "finance"
ROLE_HR = "hr"
ROLE_OPERATOR = "operator"
ROLE_READER = "reader"
ROLE_USER = "user"
ROLE_API = "api"

WRITE_ROLES = {ROLE_ADMIN, ROLE_MANAGER, ROLE_FINANCE, ROLE_HR, ROLE_OPERATOR, ROLE_USER, ROLE_API}
APPROVAL_ROLES = {ROLE_ADMIN, ROLE_MANAGER, ROLE_FINANCE, ROLE_HR, ROLE_API}
FULL_ROLES = {ROLE_ADMIN, ROLE_API}
READ_ONLY_ROLES = {ROLE_READER}
ALL_VALID_ROLES = {"admin", "manager", "finance", "hr", "operator", "reader", "user"}


def require_auth(
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    """
    通用鉴权依赖：同时接受 Bearer JWT 和 X-API-Key。
    任一有效即通过。供资源类路由（finance/crm/hr/...）使用。
    """
    return _resolve_user(token, api_key, authorization)


def require_admin(
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    """
    管理员依赖：在 require_auth 基础上要求 admin（或系统级 api）角色。
    用于审批动作、用户管理等管理端点。
    """
    user = _resolve_user(token, api_key, authorization)
    if user.role not in ("admin", "api", "operator"):
        raise HTTPException(
            status_code=403,
            detail="需要管理员权限（当前角色: " + user.role + "）",
        )
    return user


# ── 端点 ──────────────────────────────────────────────────────
@router.post("/register", response_model=CurrentUser, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户"""
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=body.username,
        hashed_password=_hash_pw(body.password),
        display_name=body.display_name,
        role="user",
        status="pending",  # 待管理员审核
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return CurrentUser(
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """用户名 + 密码登录，返回 JWT（含失败锁定）"""
    _check_lock(body.username)
    user: User | None = db.query(User).filter(User.username == body.username).first()
    if not user or not user.is_active or not _verify_pw(body.password, user.hashed_password):
        _record_fail(body.username)
        _check_lock(body.username)  # 若刚触发锁定，抛出 423
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    _reset_fail(body.username)
    # 待审核 / 已拒绝账号禁止登录（区别于密码错误，不计入失败锁定）
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户待审核，请联系管理员激活",
        )
    token = create_access_token(user.username, user.display_name, user.role)
    _register_session(token, user.username)
    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )


@router.get("/me", response_model=CurrentUser)
def me(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    """获取当前登录用户信息"""
    return current_user


@router.post("/refresh", response_model=TokenResponse)
def refresh(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    """刷新 Token"""
    token = create_access_token(current_user.username, current_user.display_name, current_user.role)
    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw_strength(cls, v):
        if len(v) < 6:
            raise ValueError("密码至少6个字符")
        return v


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    current_user: Annotated[CurrentUser, Depends(require_auth)] = None,
    db: Session = Depends(get_db),
):
    """修改密码：校验旧密码 + 强度，成功后使当前 token 失效"""
    user: User | None = db.query(User).filter(User.username == current_user.username).first()
    if not user or not _verify_pw(body.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="旧密码错误")
    if body.old_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")
    user.hashed_password = _hash_pw(body.new_password)
    db.commit()
    _blacklist_token(authorization)  # 改密后强制重新登录
    return {"ok": True, "message": "密码已修改，请重新登录"}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None, alias="Authorization")):
    """登出：当前 token 加入黑名单"""
    _blacklist_token(authorization)
    return {"ok": True, "message": "已登出"}


@router.get("/sessions")
def list_sessions(
    authorization: str | None = Header(default=None, alias="Authorization"),
    current_user: Annotated[CurrentUser, Depends(require_auth)] = None,
):
    """列出当前用户的活跃登录会话（支持多端识别）"""
    mine = [jti for jti, u in _ACTIVE_SESSIONS.items() if u == current_user.username]
    cur_jti = None
    if authorization and authorization.startswith("Bearer "):
        try:
            p = jwt.decode(authorization[len("Bearer "):], get_settings().JWT_SECRET_KEY, algorithms=["HS256"])
            cur_jti = p.get("jti")
        except jwt.PyJWTError:
            pass
    return [{"jti": j[:8], "is_current": j == cur_jti} for j in mine]


@router.post("/logout-all")
def logout_all(
    authorization: str | None = Header(default=None, alias="Authorization"),
    current_user: Annotated[CurrentUser, Depends(require_auth)] = None,
):
    """踢出除当前设备外的所有该用户会话"""
    cur_jti = None
    if authorization and authorization.startswith("Bearer "):
        try:
            p = jwt.decode(authorization[len("Bearer "):], get_settings().JWT_SECRET_KEY, algorithms=["HS256"])
            cur_jti = p.get("jti")
        except jwt.PyJWTError:
            pass
    killed = 0
    for jti, u in list(_ACTIVE_SESSIONS.items()):
        if u == current_user.username and jti != cur_jti:
            TOKEN_BLACKLIST[jti] = None
            _ACTIVE_SESSIONS.pop(jti, None)
            killed += 1
    return {"ok": True, "revoked": killed}
