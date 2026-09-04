"""plugins/event_bus.py — 进程内 pub/sub 事件总线"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Set

logger = logging.getLogger("plugins.event_bus")

@dataclass
class PluginEvent:
    name: str
    payload: Dict[str, Any]
    source_plugin: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """异步事件总线。

    订阅: subscribe("event.name", handler)
    发布: publish("event.name", payload, source_plugin)
    插件生命周期: 通过 registry 的 update_status 触发 on_load/on_unload
    """
    def __init__(self):
        # event_name → [(plugin_id, handler)]
        self._handlers: Dict[str, List[tuple]] = defaultdict(list)
        # 每个插件允许发布的事件白名单（在加载时设置）
        self._publish_whitelist: Dict[str, Set[str]] = {}

    def subscribe(self, event_name: str, plugin_id: str, handler: Callable[[PluginEvent], Awaitable[None]]) -> None:
        """注册事件处理器。"""
        self._handlers[event_name].append((plugin_id, handler))
        logger.info("插件 %s 订阅事件: %s", plugin_id, event_name)

    def unsubscribe(self, event_name: str, plugin_id: str) -> None:
        """移除插件在指定事件上的所有 handler。"""
        self._handlers[event_name] = [
            (pid, h) for pid, h in self._handlers[event_name] if pid != plugin_id
        ]

    def set_publish_whitelist(self, plugin_id: str, allowed_events: List[str]) -> None:
        self._publish_whitelist[plugin_id] = set(allowed_events)

    async def publish(self, event_name: str, payload: Dict[str, Any],
                      source_plugin: Optional[str] = None) -> Dict[str, Any]:
        """发布事件，异步通知所有订阅者。

        返回: {success: [...], failed: [...] }
        """
        # 校验插件是否允许发布此事件
        if source_plugin and source_plugin in self._publish_whitelist:
            if event_name not in self._publish_whitelist.get(source_plugin, set()):
                logger.warning("插件 %s 无权发布事件 %s", source_plugin, event_name)
                return {"success": [], "failed": [f"{source_plugin}: unauthorized"]}

        handlers = self._handlers.get(event_name, [])
        if not handlers:
            return {"success": [], "failed": []}

        event = PluginEvent(name=event_name, payload=payload, source_plugin=source_plugin)
        results = {"success": [], "failed": []}

        for plugin_id, handler in handlers:
            try:
                await asyncio.wait_for(handler(event), timeout=30.0)
                results["success"].append(plugin_id)
            except asyncio.TimeoutError:
                results["failed"].append(f"{plugin_id}: timeout (30s)")
                logger.error("事件处理超时: plugin=%s event=%s", plugin_id, event_name)
            except Exception as e:
                results["failed"].append(f"{plugin_id}: {e}")
                logger.error("事件处理失败: plugin=%s event=%s err=%s", plugin_id, event_name, e)

        return results

    def clear_plugin(self, plugin_id: str) -> None:
        """清理插件所有订阅。"""
        for event_name in list(self._handlers.keys()):
            self._handlers[event_name] = [
                (pid, h) for pid, h in self._handlers[event_name] if pid != plugin_id
            ]
        self._publish_whitelist.pop(plugin_id, None)


# ── 全局单例（供 __init__.py from .event_bus import event_bus 引用） ──
event_bus = EventBus()
