"""auth.py — 认证路由（JWT Bearer Token + DB User）"""
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Header, Body
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
import jwt
import hashlib

from database import get_db, User

router = APIRouter(prefix="/api/auth", tags=["认证"])

# ── 密钥 ──────────────────────────────────────────────────────
SECRET_KEY = os.getenv("OAUTH_SECRET_KEY", "zzcc-oa-dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
SALT = b"zzcc-oa-salt"
PBKDF2_ITER = 310_000

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


# ── 密码 ──────────────────────────────────────────────────────
def _hash_pw(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), SALT, PBKDF2_ITER).hex()

def _verify_pw(password: str, stored_hash: str) -> bool:
    return _hash_pw(password) == stored_hash

def create_access_token(username: str, display_name: str, role: str = "user") -> str:
    payload = {
        "sub": username,
        "display_name": display_name,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


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
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return CurrentUser(
                username=payload["sub"],
                display_name=payload["display_name"],
                role=payload.get("role", "user"),
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token 已过期，请重新登录")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="无效的 Token")

    if api_key == os.getenv("API_KEY", "zzcc_oadev_key_2024"):
        return CurrentUser(username="api-key-user", display_name="API 用户", role="api")

    raise HTTPException(
        status_code=401,
        detail="未认证，请先登录（POST /api/auth/login）或提供有效的 X-API-Key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _resolve_user(token: str | None, api_key: str | None, authorization: str | None) -> CurrentUser:
    """解析当前用户：Bearer JWT 优先，X-API-Key 兼容。任一有效即返回。"""
    raw = token
    if not raw and authorization and authorization.startswith("Bearer "):
        raw = authorization[len("Bearer "):]
    if raw:
        try:
            payload = jwt.decode(raw, SECRET_KEY, algorithms=[ALGORITHM])
            return CurrentUser(
                username=payload["sub"],
                display_name=payload.get("display_name", ""),
                role=payload.get("role", "user"),
            )
        except jwt.PyJWTError:
            pass
    if api_key == os.getenv("API_KEY", "zzcc_oadev_key_2024"):
        return CurrentUser(username="api-key-user", display_name="API 用户", role="api")
    raise HTTPException(
        status_code=401,
        detail="未认证，请提供有效的 Token 或 X-API-Key",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
    if user.role not in ("admin", "api"):
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
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return CurrentUser(username=user.username, display_name=user.display_name, role=user.role)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """用户名 + 密码登录，返回 JWT"""
    user: User | None = db.query(User).filter(User.username == body.username).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    if not _verify_pw(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    token = create_access_token(user.username, user.display_name, user.role)
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
