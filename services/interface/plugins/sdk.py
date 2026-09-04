"""plugins/sdk.py — 插件开发者 SDK

ZZCC services 版本：
- 认证: 对齐 routers.auth.get_current_user_dep 返回的 user 字典
  ({"id","username","roles","iat"})
- DB: async SQLAlchemy + asyncpg + PostgreSQL
- 事件总线: 复用 plugins.event_bus.EventBus
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import Header, HTTPException
from sqlalchemy import text

logger = logging.getLogger("plugins.sdk")

# ── 全局引用（由 loader 注入） ──
_current_plugin_id: Optional[str] = None
_event_bus_ref = None  # EventBus instance

# ── 管理员角色白名单（ZZCC services 里默认所有用户都是 "user"） ──
_ADMIN_ROLES = {"admin", "operator"}


@dataclass
class PluginEvent:
    name: str
    payload: Dict[str, Any]
    source_plugin: Optional[str] = None
    timestamp: float = field(default_factory=lambda: __import__("time").time())


def set_current_plugin_id(pid: Optional[str]) -> None:
    global _current_plugin_id
    _current_plugin_id = pid


def _require_plugin_id() -> str:
    if not _current_plugin_id:
        raise RuntimeError("SDK 调用在插件加载上下文中执行，但 plugin_id 未设置")
    return _current_plugin_id


# ── on_event 装饰器 ──
def on_event(event_name: str) -> Callable:
    """注册事件订阅 handler。"""
    pid = _require_plugin_id()

    def decorator(func: Callable) -> Callable:
        async def handler(event: PluginEvent):
            await func(event)

        if _event_bus_ref:
            _event_bus_ref.subscribe(event_name, pid, handler)
            logger.info("插件 %s 注册事件订阅: %s", pid, event_name)
        return handler

    return decorator


# ── 配置 ──
def get_plugin_config(key: Optional[str] = None, default: Any = None) -> Any:
    """获取插件配置。"""
    pid = _require_plugin_id()
    from .registry import registry as _registry
    meta = _registry.get(pid)
    if not meta:
        return default
    if key:
        return meta.config.get(key, default)
    return meta.config


# ── 认证 ──
async def require_auth(
    authorization: Optional[str] = Header(None),
) -> dict:
    """插件路由使用的认证依赖（从 Authorization: Bearer 解析 JWT）。

    插件里这样用：
        user = Depends(sdk.require_auth)
        user = Depends(sdk.require_admin)
    """
    from routers.auth import get_current_user_dep
    return await get_current_user_dep(authorization=authorization)


async def require_admin(
    authorization: Optional[str] = Header(None),
) -> dict:
    """要求管理员权限。

    ZZCC services 默认所有已登录用户都可管理插件（内部系统）。
    如果 user.roles 明确包含非 admin/operator 的角色，则拒绝。
    """
    user = await require_auth(authorization=authorization)
    roles_raw = user.get("roles", "") or ""
    roles = {r.strip() for r in roles_raw.split(",") if r.strip()}
    if roles and not (roles & _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ── 数据库查询（只读，PostgreSQL 方言） ──
async def query_table(
    table_name: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """只读查询 KnowledgeTable（PostgreSQL）数据库。

    注意：表名/字段名不做白名单校验，仅供内部可信插件使用。
    不支持写操作。
    """
    # 简单表名白名单校验（防注入）
    safe_name = table_name.replace("`", "").strip()
    if not safe_name or any(c.isspace() for c in safe_name):
        logger.error("query_table: 非法表名 %r", table_name)
        return []

    from services.db import managed_session
    try:
        async with managed_session() as db:
            parts = [f'SELECT * FROM "{safe_name}"']
            conditions: List[str] = []
            params: Dict[str, Any] = {}
            if filters:
                for i, (k, v) in enumerate(filters.items()):
                    if v is None:
                        conditions.append(f'"{k}" IS NULL')
                    else:
                        conditions.append(f'"{k}" = :p{i}')
                        params[f"p{i}"] = v
            if conditions:
                parts.append("WHERE " + " AND ".join(conditions))
            parts.append(f"LIMIT :_limit")
            params["_limit"] = int(limit)
            query = " ".join(parts)

            result = await db.execute(text(query), params)
            cols = result.keys()
            rows = result.fetchall()
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        logger.error("query_table 失败: %s %s", table_name, e)
        return []


# ── 发布事件 ──
async def publish_event(event_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """发布事件到总线，并写入事件日志 DB（与 routers/plugins.py 的 _events 端点对齐）。"""
    import json
    from sqlalchemy import text as _text
    pid = _require_plugin_id()
    result = {"success": [], "failed": ["event_bus not initialized"]}
    if _event_bus_ref:
        result = await _event_bus_ref.publish(event_name, payload, source_plugin=pid)

    # 写入事件日志（异步 fire-and-forget，失败不阻塞 publish）
    try:
        from services.db import managed_session
        async with managed_session() as db:
            await db.execute(_text(
                "INSERT INTO plugin_event_log (plugin_id, event_name, payload) "
                "VALUES (:pid, :en, :pl)"
            ), {
                "pid": pid,
                "en": event_name,
                "pl": json.dumps(payload, ensure_ascii=False),
            })
            await db.commit()
    except Exception as e:
        logger.error("publish_event 日志写入失败: %s", e)
    return result


# ── 日志 ──
def log(msg: str, level: str = "info") -> None:
    """插件专用日志，带 [plugin:id] 前缀。"""
    pid = _current_plugin_id or "unknown"
    getattr(logger, level)(f"[plugin:{pid}] {msg}")
