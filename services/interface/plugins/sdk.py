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
_brain_plugin_registrations: Dict[str, Dict[str, List[str]]] = {}

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


def _get_brain_registrations(plugin_id: str) -> Dict[str, List[str]]:
    return _brain_plugin_registrations.setdefault(plugin_id, {"rules": [], "actions": [], "events": []})


def clear_brain_plugin_registrations(plugin_id: str) -> dict:
    """清理插件注册的 Brain 规则/动作/事件订阅。

    用于插件 disable/uninstall/reload 生命周期。事件清理由 EventBus.clear_plugin 完成。
    除 SDK 明确记录的注册项外，也会兜底清理同一 plugin_id 前缀下由 API/自定义规则创建的 Brain 注册。
    """
    from services.brain import action_executor as brain_action_executor
    from services.brain import rules as brain_rules

    reg = _brain_plugin_registrations.get(plugin_id, {"rules": [], "actions": [], "events": []})
    tracked_rules = reg.get("rules", [])
    tracked_actions = reg.get("actions", [])
    tracked_events = reg.get("events", [])

    rules_to_remove = [r.id for r in brain_rules.list_rules(enabled_only=False) if r.id.startswith(f"{plugin_id}.")]
    for rid in tracked_rules:
        if rid not in rules_to_remove:
            rules_to_remove.append(rid)

    rules_removed = 0
    for rid in rules_to_remove:
        if brain_rules.unregister_rule(rid):
            rules_removed += 1

    actions_removed = 0
    _EXEC = getattr(brain_action_executor, "_EXECUTORS", {})
    actions_to_remove = [aid for aid in list(_EXEC.keys()) if aid.startswith(f"{plugin_id}.")]
    for aid in tracked_actions:
        if aid not in actions_to_remove:
            actions_to_remove.append(aid)
    for aid in actions_to_remove:
        if _EXEC.pop(aid, None) is not None:
            actions_removed += 1

    _brain_plugin_registrations.pop(plugin_id, None)
    return {"rules": rules_removed, "actions": actions_removed, "events": len(tracked_events)}


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

# ── Brain AI 扩展 ──
def _brain_rule_id(plugin_id: str, rule_id: Optional[str]) -> str:
    """确保插件规则 id 唯一，避免覆盖内置/其他插件规则。"""
    rid = rule_id or ""
    if not rid:
        raise ValueError("brain_rule 需要 rule_id")
    if rid.startswith(f"{plugin_id}."):
        return rid
    return f"{plugin_id}.{rid}"


def brain_rule(
    rule_id: str,
    module: Optional[str] = None,
    action: str = "flag",
    confidence: float = 0.8,
    description: str = "",
) -> Callable:
    """注册 Brain AI L1 规则。

    handler 签名：async def handler(payload: dict, context: dict) -> bool
    返回 True 表示规则命中，随后执行 action。
    """
    pid = _require_plugin_id()
    from models.brain import BrainRule
    from services.brain import rules as brain_rules

    def decorator(func: Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[bool]] | Callable[[Dict[str, Any], Dict[str, Any]], bool]) -> Callable:
        async def condition_wrapper(payload: Dict[str, Any], context: Dict[str, Any]) -> bool:
            result = func(payload, context)
            if hasattr(result, "__await__"):
                result = await result
            return bool(result)

        rid = _brain_rule_id(pid, rule_id)
        rule = BrainRule(
            id=rid,
            module=module or pid,
            condition=condition_wrapper,
            action=action,
            confidence=confidence,
            description=description or f"[{pid}] {rule_id}",
            enabled=True,
        )
        brain_rules.register_rule(rule)
        _get_brain_registrations(pid)["rules"].append(rid)
        logger.info("插件 %s 注册 Brain 规则: %s -> %s", pid, rid, action)
        return func

    return decorator


def brain_action(action_type: str) -> Callable:
    """注册 Brain AI 自定义行动执行器。

    handler 签名：async def handler(action, cognition, db) -> dict
    action_type 会自动加插件名前缀，例如 plugin.test -> test-plugin.test_action。
    """
    pid = _require_plugin_id()
    from services.brain import action_executor as brain_action_executor

    def decorator(func: Callable[..., Awaitable[dict]]) -> Callable:
        full_type = action_type if action_type.startswith(f"{pid}.") else f"{pid}.{action_type}"

        async def executor(action, cognition, db) -> dict:
            try:
                result = await func(action, cognition, db)
                if not isinstance(result, dict):
                    result = {"ok": True, "result": result}
                result.setdefault("ok", True)
                result["action"] = full_type
                result["action_type"] = full_type
                result["plugin_id"] = pid
                return result
            except Exception as e:
                logger.error("brain_action_failed: plugin=%s action=%s error=%s", pid, full_type, str(e))
                return {
                    "ok": False,
                    "action": full_type,
                    "action_type": full_type,
                    "plugin_id": pid,
                    "error": str(e),
                }

        brain_action_executor.register_executor(full_type, executor)
        _get_brain_registrations(pid)["actions"].append(full_type)
        logger.info("插件 %s 注册 Brain Action: %s", pid, full_type)
        return func

    return decorator


def brain_signal_handler(event_type: str) -> Callable:
    """订阅插件事件并把事件转发为 Brain signal，由 /brain/observe 规则处理。

    插件里这样用：
        @sdk.brain_signal_handler("risk.detected")
        async def on_risk(event: sdk.PluginEvent):
            return {"type": "risk_detected", "payload": event.payload, "urgency": 70}

    handler 返回 None 时不会创建 Brain signal。
    """
    pid = _require_plugin_id()

    def decorator(func: Callable[[PluginEvent], Awaitable[Optional[Dict[str, Any]]]]) -> Callable:
        async def handler(event: PluginEvent):
            try:
                signal_data = func(event)
                if hasattr(signal_data, "__await__"):
                    signal_data = await signal_data
                if not signal_data:
                    return
                await publish_brain_signal(pid, event, signal_data)
            except Exception as e:
                logger.error("brain_signal_handler_failed: plugin=%s event=%s error=%s", pid, event_type, str(e))

        if _event_bus_ref:
            _event_bus_ref.subscribe(event_type, pid, handler)
            _get_brain_registrations(pid)["events"].append(event_type)
            logger.info("插件 %s 注册 Brain 信号处理器: %s", pid, event_type)
        return handler

    return decorator


async def publish_brain_signal(
    source: str,
    event_or_payload: "PluginEvent | Dict[str, Any]",
    signal_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """插件发布 Brain AI 信号。

    优先写入 brain_signal 表；失败时退回到内存工作记忆。
    """
    from models.brain import NeuralSignal
    from services.brain import memory as brain_memory
    from services.db import managed_session

    if isinstance(event_or_payload, PluginEvent):
        payload = signal_data or dict(event_or_payload.payload or {})
    else:
        payload = signal_data or dict(event_or_payload or {})

    signal = NeuralSignal(
        type=str(payload.pop("type", f"plugin.{source}")),
        payload=dict(payload.pop("payload", payload)),
        source=f"plugin:{source}",
        urgency=int(payload.pop("urgency", 50)),
        context=payload.pop("context", {}) or {"event": payload},
    )
    try:
        async with managed_session() as db:
            await brain_memory.enqueue_signal(db, signal.to_dict())
            await db.commit()
        return {"ok": True, "signal_id": signal.id, "type": signal.type}
    except Exception as e:
        brain_memory.working_memory.append(signal.to_dict())
        logger.warning("brain_signal_db_write_failed: %s", str(e))
        return {"ok": False, "signal_id": signal.id, "type": signal.type, "warning": str(e)}
