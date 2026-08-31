"""
User & Auth database models — SQLAlchemy ORM + Pydantic schemas.
Tables: users, user_identities, auth_codes (via SQLAlchemy).
Raw DDL tables chat_user/chat_identity_binding are managed in user_db.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    """核心用户表。UID 是前端生成的 32 位 hex，username 是用户可选设置的唯一名。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="前端生成的 32 位 hex UID",
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(128), unique=True, nullable=True, index=True,
        comment="用户自选用户名（可选，唯一）",
    )
    password_hash: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="bcrypt hash",
    )
    display_name: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True,
        comment="显示名称",
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    identities: Mapped[list[UserIdentity]] = relationship(
        "UserIdentity", back_populates="user", cascade="all, delete-orphan",
    )
    codes: Mapped[list[AuthCode]] = relationship(
        "AuthCode", back_populates="user", cascade="all, delete-orphan",
    )


class UserIdentity(Base):
    """用户身份绑定表。一个用户可绑定多个手机号/邮箱。"""
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("identity_type", "identity_value", name="uq_identity_type_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    identity_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="phone | email",
    )
    identity_value: Mapped[str] = mapped_column(
        String(256), nullable=False, index=True,
        comment="手机号或邮箱地址",
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="是否为主登录身份",
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="验证时间",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="identities")


class AuthCode(Base):
    """验证码表。用于邮箱/手机验证码登录和身份绑定。"""
    __tablename__ = "auth_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True,
    )
    identity_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="phone | email",
    )
    identity_value: Mapped[str] = mapped_column(
        String(256), nullable=False, index=True,
    )
    code_hash: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="验证码的 sha256 hash（不存明文）",
    )
    code_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="bind_identity | login | password_reset",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="验证尝试次数",
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False,
    )

    user: Mapped[Optional[User]] = relationship("User", back_populates="codes")


# ════════════════════════════════════════════════════════════════════
# Pydantic request/response schemas
# ════════════════════════════════════════════════════════════════════

class ChatUserCreate(BaseModel):
    username: str
    password: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    client_uid: Optional[str] = None


class ChatUserRegister(BaseModel):
    """Register with password (online account)."""
    username: str
    password: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    client_uid: Optional[str] = None


class ChatUserLogin(BaseModel):
    username: str
    password: str


class ChatUserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    is_deleted: Optional[bool] = None


class ChatUserRead(BaseModel):
    id: str
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    matrix_user_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login_at: Optional[str] = None
    is_active: bool = True
    sync_status: str = "local"
    client_uid: Optional[str] = None


class ChatUserListResponse(BaseModel):
    data: list[ChatUserRead] = Field(default_factory=list)
    length: int = 0


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str
    username: str


class PasswordResetCodeRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    code: str
    new_password: str


class VerificationCodeSend(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None


class IdentityBindingCreate(BaseModel):
    binding_type: str  # email | phone | matrix
    binding_value: str
    verified: bool = False


class IdentityBindingRead(BaseModel):
    user_id: str
    binding_type: str
    binding_value: str
    verified: bool
    verified_method: Optional[str] = None
    created_at: Optional[str] = None


class IdentityBindingListResponse(BaseModel):
    items: list[IdentityBindingRead] = Field(default_factory=list)


class ChatUserSyncRequest(BaseModel):
    """Batch sync local users to server."""
    users: list[ChatUserCreate] = Field(default_factory=list)


class ChatUserSyncResponse(BaseModel):
    created: int = 0
    updated: int = 0
    conflicts: list[str] = Field(default_factory=list)
