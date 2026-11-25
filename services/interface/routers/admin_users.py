"""管理后台专用用户管理接口。

与 /chat/users 的关键区别: 鉴权方式。

- /chat/users      → get_current_user_dep, 要求登录用户的 Bearer token。
- /admin/users    → X-Admin-Key 密钥头。管理后台是内部运维工具, 静态页面拿不到
                    也不该拿用户 token; 否则运维要看用户列表还得先登录一个账号。

密钥来自环境变量 ZZCC_ADMIN_API_KEY。未配置时接口直接 503 拒绝,
绝不回落成"无鉴权"——否则管理后台等于把用户表裸奔到 /admin 同源路径下。
"""

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from services.user_db import managed_session
from sqlalchemy import text

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

_ADMIN_KEY_ENV = "ZZCC_ADMIN_API_KEY"


async def require_admin_key(x_admin_key: Optional[str] = Header(None)) -> None:
    expected = os.environ.get(_ADMIN_KEY_ENV)
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="管理接口未启用: 服务器未配置 " + _ADMIN_KEY_ENV,
        )
    if not x_admin_key or x_admin_key.strip() != expected:
        raise HTTPException(status_code=401, detail="管理密钥无效")




class AdminUserUpdate(BaseModel):
    """管理后台可写的字段。刻意只留这两个:
    封禁位 + 角色。资料类字段(username/email/avatar...)走用户自己的 /chat/users PATCH。

    Literal 在 Pydantic 层就拦下非法 role, 无需路由里重复校验;
    extra=forbid 防止未知字段静默丢弃被当成"已更新"。
    """

    model_config = ConfigDict(extra="forbid")

    is_active: Optional[bool] = None
    role: Optional[Literal["user", "admin"]] = None


def _to_read(row: dict) -> dict:
    def _iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else v
    return {
        "id": str(row["id"]),
        "username": row["username"],
        "display_name": row.get("display_name"),
        "email": row.get("email"),
        "phone": row.get("phone"),
        "avatar_url": row.get("avatar_url"),
        "matrix_user_id": row.get("matrix_user_id"),
        "is_active": bool(row.get("is_active", True)),
        "role": str(row.get("role") or "user"),
        "sync_status": row.get("sync_status", "local"),
        "client_uid": row.get("client_uid"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "last_login_at": _iso(row.get("last_login_at")),
    }


@router.get("")
async def admin_list_users(
    q: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _admin: None = Depends(require_admin_key),
):
    """用户列表: 搜索 + 分页。管理后台默认带全量视角(不过滤被封禁用户)。"""
    where = "WHERE is_deleted = FALSE"
    params: dict = {"limit": limit, "skip": skip}
    if q and q.strip():
        where += (" AND (username ILIKE :q OR display_name ILIKE :q"
                  " OR email ILIKE :q OR phone ILIKE :q)")
        params["q"] = f"%{q.strip()}%"
    async with managed_session() as sess:
        result = await sess.execute(
            text(
                "SELECT * FROM chat_user "
                f"{where} ORDER BY created_at DESC LIMIT :limit OFFSET :skip"
            ),
            params,
        )
        rows = [dict(r) for r in result.mappings()]
        count = (await sess.execute(
            text(f"SELECT count(*) AS n FROM chat_user {where}"), params,
        )).scalar_one()
    return {"data": [_to_read(r) for r in rows], "length": len(rows), "total": int(count)}


@router.patch("/{user_id}")
async def admin_update_user(
    user_id: str,
    patch: AdminUserUpdate,
    _admin: None = Depends(require_admin_key),
):
    """封禁/启用 + 角色变更。管理后台唯一的写入口。"""
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="无更新内容")
    sets = ", ".join(f"{k} = :{k}" for k in data)
    params = {**data, "id": user_id}
    sql = (f"UPDATE chat_user SET {sets}, updated_at = NOW() "
           f"WHERE id = CAST(:id AS UUID) AND is_deleted = FALSE")
    async with managed_session() as sess:
        res = await sess.execute(text(sql), params)
        await sess.commit()
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="用户不存在")
        row = (await sess.execute(
            text("SELECT * FROM chat_user WHERE id = CAST(:id AS UUID)"),
            {"id": user_id},
        )).mappings().first()
    return _to_read(dict(row))


@router.post("/{user_id}/ban")
async def admin_ban_user(
    user_id: str,
    _admin: None = Depends(require_admin_key),
):
    """封禁用户。同时置 is_active=FALSE。

    登录接口 (routers/auth.py) 已校验 is_active, 故封禁即时生效:
    被封用户在 token 过期前已签发的 token 仍能访问旧接口,
    但下次登录被拒, 属于既有行为, 不在此扩大改动面。
    """
    async with managed_session() as sess:
        res = await sess.execute(text(
            "UPDATE chat_user SET is_active = FALSE, updated_at = NOW() "
            "WHERE id = CAST(:id AS UUID) AND is_deleted = FALSE"
        ), {"id": user_id})
        await sess.commit()
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="用户不存在")
        row = (await sess.execute(
            text("SELECT * FROM chat_user WHERE id = CAST(:id AS UUID)"),
            {"id": user_id},
        )).mappings().first()
    return _to_read(dict(row))


@router.post("/{user_id}/unban")
async def admin_unban_user(
    user_id: str,
    _admin: None = Depends(require_admin_key),
):
    """解封用户。"""
    async with managed_session() as sess:
        res = await sess.execute(text(
            "UPDATE chat_user SET is_active = TRUE, updated_at = NOW() "
            "WHERE id = CAST(:id AS UUID) AND is_deleted = FALSE"
        ), {"id": user_id})
        await sess.commit()
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="用户不存在")
        row = (await sess.execute(
            text("SELECT * FROM chat_user WHERE id = CAST(:id AS UUID)"),
            {"id": user_id},
        )).mappings().first()
    return _to_read(dict(row))


# 注: 不提供 /stats 聚合端点。两个原因:
# 1. 路由顺序 —— "stats" 会被 /{user_id} 通配匹配走(PATCH 已如此),
#    必须先注册才不被吞, 维护心智负担不值。
# 2. 管理后台 KPI 直接从列表页首屏数据本地聚合即可, 多一个端点等于多一处鉴权面。


def _admin_key_configured() -> bool:
    return bool(os.environ.get(_ADMIN_KEY_ENV))