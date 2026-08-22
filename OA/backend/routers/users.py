"""routers/users.py — 用户管理（Admin CRUD）"""
import json
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db, User, Department
from routers.auth import require_admin, require_auth, CurrentUser, _hash_pw
from routers.notifications import notify

router = APIRouter(prefix="/api/users", tags=["用户管理"])


# ── 请求/响应模型 ──────────────────────────────────────────────
class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "user"
    department_id: str | None = None

    @field_validator("username")
    @classmethod
    def username_len(cls, v):
        if len(v) < 3 or not v.isalnum():
            raise ValueError("用户名至少3个字符，只能包含字母和数字")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("密码至少6个字符")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v):
        if v not in ("user", "admin", "manager", "finance", "hr", "operator", "reader"):
            raise ValueError("无效的角色")
        return v


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    department_id: str | None = None
    is_active: bool | None = None
    ext: dict | None = None  # 合并到现有 ext（JSON patch）

    @field_validator("role")
    @classmethod
    def role_valid(cls, v):
        if v is not None and v not in ("user", "admin", "manager", "finance", "hr"):
            raise ValueError("无效的角色")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class ResetPasswordRequest(BaseModel):
    new_password: str
    invalidate_sessions: bool = True

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("密码至少6个字符")
        return v


class UserResponse(BaseModel):
    username: str
    display_name: str
    role: str
    department_id: str | None
    is_active: bool
    status: str = "active"
    ext: dict | None
    creation: datetime

    @classmethod
    def from_user(cls, u: User) -> "UserResponse":
        ext = None
        if u.ext:
            try:
                ext = json.loads(u.ext)
            except Exception:
                ext = {}
        return cls(
            username=u.username,
            display_name=u.display_name,
            role=u.role,
            department_id=u.department_id,
            is_active=u.is_active,
            status=u.status,
            ext=ext,
            creation=u.creation,
        )


# ── 辅助 ───────────────────────────────────────────────────────
def _parse_ext(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ── 端点 ──────────────────────────────────────────────────────
@router.get("", response_model=list[UserResponse])
def list_users(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
    role: str | None = None,
    department_id: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
):
    """管理员列出所有用户（支持按 role/department/is_active/search 过滤）"""
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    if department_id:
        q = q.filter(User.department_id == department_id)
    if is_active is not None:
        q = q.filter(User.is_active == is_active)
    if search:
        q = q.filter(
            or_(
                User.username.contains(search),
                User.display_name.contains(search),
            )
        )
    users = q.order_by(User.creation.desc()).all()
    return [UserResponse.from_user(u) for u in users]


@router.get("/{username}", response_model=UserResponse)
def get_user(
    username: str,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """获取指定用户详情"""
    u = db.query(User).filter(User.username == username).first()
    if not u:
        raise HTTPException(status_code=404, detail=f"用户不存在: {username}")
    return UserResponse.from_user(u)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """管理员创建新用户"""
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    if body.department_id:
        dept = db.query(Department).filter(Department.name == body.department_id).first()
        if not dept:
            raise HTTPException(status_code=400, detail=f"部门不存在: {body.department_id}")
    user = User(
        username=body.username,
        hashed_password=_hash_pw(body.password),
        display_name=body.display_name,
        role=body.role,
        department_id=body.department_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.from_user(user)




# ═══ 个人设置：修改自己的 display_name ═══
class SelfUpdateRequest(BaseModel):
    display_name: str | None = None

@router.patch("/me", response_model=UserResponse)
def update_self(
    body: SelfUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_auth)],
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.username == current_user.username).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if body.display_name is not None:
        u.display_name = body.display_name
    db.commit()
    db.refresh(u)
    return UserResponse.from_user(u)


# ═══ 个人设置：修改密码 ═══
@router.post("/me/password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    current_user: Annotated[CurrentUser, Depends(require_auth)],
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.username == current_user.username).first()
    if not u:
        raise HTTPException(status_code=401, detail="用户不存在")
    # 验证旧密码
    if u.hashed_password != _hash_pw(body.current_password):
        raise HTTPException(status_code=400, detail="旧密码不正确")
    u.hashed_password = _hash_pw(body.new_password)
    db.commit()


@router.patch("/{username}", response_model=UserResponse)
def update_user(
    username: str,
    body: UpdateUserRequest,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """管理员修改用户信息（display_name / role / department / is_active / ext）"""
    u = db.query(User).filter(User.username == username).first()
    if not u:
        raise HTTPException(status_code=404, detail=f"用户不存在: {username}")
    if body.display_name is not None:
        u.display_name = body.display_name
    if body.role is not None:
        u.role = body.role
    if body.department_id is not None:
        if body.department_id == "":
            u.department_id = None
        else:
            dept = db.query(Department).filter(Department.name == body.department_id).first()
            if not dept:
                raise HTTPException(status_code=400, detail=f"部门不存在: {body.department_id}")
            u.department_id = body.department_id
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.ext is not None:
        current_ext = _parse_ext(u.ext)
        current_ext.update(body.ext)
        u.ext = json.dumps(current_ext)
    db.commit()
    db.refresh(u)
    return UserResponse.from_user(u)


@router.post("/{username}/reset-password")
def reset_password(
    username: str,
    body: ResetPasswordRequest,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """管理员重置用户密码（无需旧密码，可选使其所有会话失效）"""
    if username == "admin":
        raise HTTPException(status_code=400, detail="不能重置 admin 密码（建议直接操作数据库）")
    u = db.query(User).filter(User.username == username).first()
    if not u:
        raise HTTPException(status_code=404, detail=f"用户不存在: {username}")
    u.hashed_password = _hash_pw(body.new_password)
    if body.invalidate_sessions:
        # 清掉该用户所有活跃会话（实际生产应通过 Redis key 模式删除）
        from routers.auth import _ACTIVE_SESSIONS, TOKEN_BLACKLIST
        to_remove = [jti for jti, u2 in _ACTIVE_SESSIONS.items() if u2 == username]
        for jti in to_remove:
            TOKEN_BLACKLIST[jti] = None
            _ACTIVE_SESSIONS.pop(jti, None)
    db.commit()
    return {"ok": True, "message": f"用户 {username} 的密码已重置"}


@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    username: str,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """管理员禁用用户（软删除：is_active=False）"""
    if username == "admin":
        raise HTTPException(status_code=400, detail="不能禁用 admin 账号")
    if username == current_user.username:
        raise HTTPException(status_code=400, detail="不能禁用自己的账号")
    u = db.query(User).filter(User.username == username).first()
    if not u:
        raise HTTPException(status_code=404, detail=f"用户不存在: {username}")
    u.is_active = False
    db.commit()
    # 禁用后踢掉该用户所有会话
    from routers.auth import _ACTIVE_SESSIONS, TOKEN_BLACKLIST
    to_remove = [jti for jti, u2 in _ACTIVE_SESSIONS.items() if u2 == username]
    for jti in to_remove:
        TOKEN_BLACKLIST[jti] = None
        _ACTIVE_SESSIONS.pop(jti, None)


# ── 注册审批流（管理员审核模式，零 SMTP 依赖）────────────────
@router.get("/registrations/pending", response_model=list[UserResponse])
def list_pending_registrations(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """列出所有待审核的注册申请"""
    users = db.query(User).filter(User.status == "pending").all()
    return [UserResponse.from_user(u) for u in users]


@router.post("/{username}/approve", response_model=UserResponse)
def approve_registration(
    username: str,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """批准注册申请：激活账号并站内通知用户"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.status != "pending":
        raise HTTPException(status_code=400, detail="该账号不在待审核状态，无法审批")
    user.status = "active"
    user.is_active = True
    notify(
        db,
        recipient=username,
        title="账号已激活",
        body=f"您的账号 {username} 已通过管理员审核，现在可以登录了。",
        ntype="info",
    )
    db.commit()
    db.refresh(user)
    return UserResponse.from_user(user)


@router.post("/{username}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_registration(
    username: str,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """拒绝注册申请：禁用账号并通知用户"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.status != "pending":
        raise HTTPException(status_code=400, detail="该账号不在待审核状态，无法审批")
    user.status = "rejected"
    user.is_active = False
    notify(
        db,
        recipient=username,
        title="注册申请未通过",
        body=f"您的注册申请（{username}）未通过管理员审核。",
        ntype="info",
    )
    db.commit()
    return None
