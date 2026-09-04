"""plugins/sdk.py — 插件开发者 SDK

提供给插件开发者的最小 SDK：
- on_event: 注册事件订阅 handler
- get_plugin_config: 获取插件配置
- require_auth: 认证依赖
- query_table: 只读数据库查询
- publish_event: 发布事件
- PluginEvent: 事件数据类
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, HTTPException

logger = logging.getLogger("plugins.sdk")

# ── 全局引用（由 loader 注入） ──
_current_plugin_id: Optional[str] = None
_event_bus_ref = None  # EventBus instance
_db_sessionmaker_ref = None  # SessionLocal callable

@dataclass
class PluginEvent:
    name: str
    payload: Dict[str, Any]
    source_plugin: Optional[str] = None
    timestamp: float = field(default_factory=lambda: __import__("time").time())


def set_current_plugin_id(pid: str) -> None:
    global _current_plugin_id
    _current_plugin_id = pid


def _require_plugin_id() -> str:
    if not _current_plugin_id:
        raise RuntimeError("SDK 调用在插件加载上下文中执行，但 plugin_id 未设置")
    return _current_plugin_id


# ── on_event 装饰器 ──
def on_event(event_name: str) -> Callable:
    """注册事件订阅 handler。

    用法：
        @on_event("approval.approved")
        async def handle_approval(event: PluginEvent):
            po = event.payload
            await publish_event("inventory.low_stock", {"sku": po["sku"]})
    """
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
def get_plugin_config(key: str = None, default: Any = None) -> Any:
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
async def require_auth(user: dict) -> dict:
    """插件路由使用的认证依赖，直接透传已认证用户。"""
    return user


async def require_admin(user: dict) -> dict:
    """要求管理员权限。"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ── 数据库查询（只读） ──
async def query_table(table_name: str, filters: Dict[str, Any] = None,
                      limit: int = 100) -> List[Dict[str, Any]]:
    """只读查询 OA 数据库。

    使用 ORM 动态查找表模型，不支持写操作。
    """
    from sqlalchemy import text
    if not _db_sessionmaker_ref:
        return []

    db = _db_sessionmaker_ref()
    try:
        # 构建只读 SELECT 查询
        query = f"SELECT * FROM `{table_name}`"
        conditions = []
        params = {}
        if filters:
            for i, (k, v) in enumerate(filters.items()):
                if v is None:
                    conditions.append(f"`{k}` IS NULL")
                else:
                    conditions.append(f"`{k}` = :p{i}")
                    params[f"p{i}"] = v
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f" LIMIT {limit}"

        result = db.execute(text(query), params)
        rows = result.fetchall()
        cols = result.keys()
        return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        logger.error("query_table 失败: %s %s", table_name, e)
        return []
    finally:
        db.close()


# ── 发布事件 ──
async def publish_event(event_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """发布事件到总线。"""
    pid = _require_plugin_id()
    if not _event_bus_ref:
        return {"success": [], "failed": ["event_bus not initialized"]}
    return await _event_bus_ref.publish(event_name, payload, source_plugin=pid)


# ── 日志 ──
def log(msg: str, level: str = "info") -> None:
    """插件专用日志，带 [plugin:id] 前缀。"""
    pid = _current_plugin_id or "unknown"
    getattr(logger, level)(f"[plugin:{pid}] {msg}")
