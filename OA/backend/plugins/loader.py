"""plugins/loader.py — 插件加载器"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI

from .registry import (
    PluginMetadata,
    PluginStatus,
    PluginRegistry,
    PluginManifestError,
    validate_manifest,
)
from .event_bus import EventBus, PluginEvent

logger = logging.getLogger("plugins.loader")

# ── import 白名单（沙箱限制） ──
ALLOWED_IMPORTS = {
    "fastapi", "pydantic", "sqlalchemy", "datetime",
    "typing", "json", "asyncio", "logging", "os",
    "re", "hashlib", "uuid", "time",
    "plugins.sdk",
}

PLUGINS_DIR = Path("/app/plugins_data")  # Docker 容器内路径


def _ensure_plugins_dir() -> Path:
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return PLUGINS_DIR


async def load_plugin(app: FastAPI, plugin_dir: Path,
                      registry: PluginRegistry,
                      event_bus: EventBus) -> Optional[PluginMetadata]:
    """加载单个插件。

    1. 读取 plugin.json
    2. 校验 manifest
    3. 加载路由模块 → include_router
    4. 注册事件订阅
    5. 注册前端模块
    6. 执行 on_load() 钩子（如有）
    """
    if not plugin_dir.is_dir():
        return None
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("plugin.json 读取失败 %s: %s", plugin_dir, e)
        return None

    try:
        validate_manifest(manifest)
    except PluginManifestError as e:
        logger.error("plugin.json 校验失败 %s: %s", manifest.get("id", plugin_dir.name), e)
        return None

    pid = manifest["id"]

    # ── 路由加载 ──
    routes_info = manifest.get("routes")
    if routes_info:
        router_module = routes_info.get("router", "")
        if router_module:
            module_path_str = str(plugin_dir / router_module.split(":")[0])
            attr_name = router_module.split(":")[1] if ":" in router_module else "router"
            try:
                # 注入全局引用到 sdk（让 @on_event 能注册到 event_bus）
                from . import sdk as _sdk
                _sdk.set_current_plugin_id(pid)
                _sdk._event_bus_ref = event_bus
                from database import SessionLocal
                _sdk._db_sessionmaker_ref = SessionLocal
                _sdk.PluginEvent = PluginEvent

                spec = importlib.util.spec_from_file_location(pid.replace("-", "_"), module_path_str)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[pid.replace("-", "_")] = mod
                    spec.loader.exec_module(mod)
                    plugin_router = getattr(mod, attr_name, None)
                    if plugin_router:
                        prefix = f"/api/plugin/{pid}"
                        # 逐个注册 APIRoute，插入到 Mount 之前（Mount 在列表末尾会吞掉所有请求）
                        added = 0
                        # 找到 Mount 的索引（通常是 app.mount("/") 的静态文件服务）
                        mount_idx = None
                        for i, r in enumerate(app.routes):
                            if type(r).__name__ == "Mount":
                                mount_idx = i
                                break
                        for route in plugin_router.routes:
                            full_path = prefix + route.path
                            methods = set(route.methods) if route.methods else {"GET"}
                            # 用 insert 而非 append，确保在 Mount 之前
                            from fastapi.routing import APIRoute as _AR
                            new_route = _AR(
                                path=full_path,
                                endpoint=route.endpoint,
                                methods=methods,
                                name=route.name,
                            )
                            if mount_idx is not None:
                                app.router.routes.insert(mount_idx, new_route)
                                mount_idx += 1  # 后续路由也插入到此之前
                            else:
                                app.router.routes.append(new_route)
                            added += 1
                        logger.info("插件 %s 路由已注册: %s (%d 条)", pid, prefix, added)
                # 清理注入
                _sdk._event_bus_ref = None
                _sdk._db_sessionmaker_ref = None
                _sdk.set_current_plugin_id(None)
            except Exception as e:
                import traceback
                logger.error("插件 %s 路由加载失败: %s", pid, e)
                traceback.print_exc()

    # ── 事件订阅注册 ──
    events = manifest.get("events", {})
    subscribe_events = events.get("subscribe", [])
    publish_events = events.get("publish", [])

    if publish_events:
        event_bus.set_publish_whitelist(pid, publish_events)

    # 事件 handler 在 routes.py 中通过 @on_event 装饰器注册，由 SDK 处理
    # 这里只需白名单设置

    # ── 前端模块 ──
    frontend_module = None
    fe = manifest.get("frontend")
    if fe:
        frontend_module = fe.get("module")
        if frontend_module:
            frontend_module["plugin_id"] = pid

    # ── 创建 metadata 并注册 ──
    metadata = PluginMetadata(
        id=pid,
        name=manifest["name"],
        version=manifest["version"],
        author=manifest.get("author", ""),
        description=manifest.get("description", ""),
        manifest=manifest,
        status=PluginStatus.ENABLED,
        config=manifest.get("config", {}),
        frontend_module=frontend_module,
    )
    registry.register(metadata)

    # ── on_load 钩子 ──
    hook_path = plugin_dir / "hook.py"
    if hook_path.exists():
        try:
            spec = importlib.util.spec_from_file_location(f"{pid}.hook", str(hook_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                on_load = getattr(mod, "on_load", None)
                if on_load and callable(on_load):
                    await asyncio.wait_for(on_load(), timeout=15.0)
        except Exception as e:
            logger.error("插件 %s on_load 钩子执行失败: %s", pid, e)

    return metadata


async def scan_and_load_plugins(app: FastAPI, registry: PluginRegistry,
                                event_bus: EventBus) -> List[PluginMetadata]:
    """扫描 plugins_data/ 目录并加载所有插件。"""
    ensure_dir = _ensure_plugins_dir()
    loaded = []
    for plugin_dir in sorted(ensure_dir.iterdir()):
        if plugin_dir.is_dir() and plugin_dir.name != "__pycache__":
            meta = await load_plugin(app, plugin_dir, registry, event_bus)
            if meta:
                loaded.append(meta)
    # 持久化到 DB
    registry.save_to_db()
    logger.info("插件加载完成: %d 个", len(loaded))
    return loaded
