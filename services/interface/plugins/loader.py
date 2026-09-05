"""plugins/loader.py — 插件加载器

ZZCC services 版本：async SQLAlchemy + asyncpg + PostgreSQL。
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute as _AR

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

# 插件数据目录（默认 /app/plugins_data，可用 ZZCC_PLUGINS_DIR 覆盖）
PLUGINS_DIR = Path(os.environ.get("ZZCC_PLUGINS_DIR", "/app/plugins_data"))


def _ensure_plugins_dir() -> Path:
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return PLUGINS_DIR


async def _load_config_from_db(registry: PluginRegistry, plugin_id: str) -> Optional[Dict[str, Any]]:
    """从 DB 加载插件配置（兼容卸载后重装场景）。"""
    return await registry.get_config_from_db(plugin_id)


def _make_plugin_ctx_depender(plugin_id: str):
    """为插件路由注入 plugin_id 上下文（运行时由 SDK 读取）。"""
    def _ctx_depender() -> dict:
        from . import sdk as _sdk_inner
        _sdk_inner._current_plugin_id = plugin_id
        return {}
    return _ctx_depender


def _build_content_type(path: str) -> str:
    if path.endswith(".css"): return "text/css"
    if path.endswith(".js"): return "application/javascript"
    if path.endswith(".json"): return "application/json"
    if path.endswith(".png"): return "image/png"
    if path.endswith((".jpg", ".jpeg")): return "image/jpeg"
    if path.endswith(".svg"): return "image/svg+xml"
    if path.endswith(".ico"): return "image/x-icon"
    return "text/html"


async def load_plugin(app: FastAPI, plugin_dir: Path,
                      registry: PluginRegistry,
                      event_bus: EventBus) -> Optional[PluginMetadata]:
    """加载单个插件。"""
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
                # DB sessionmaker 由插件运行时按需 async 获取，无需注入 sync SessionLocal
                _sdk.PluginEvent = PluginEvent

                spec = importlib.util.spec_from_file_location(
                    pid.replace("-", "_"), module_path_str
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[pid.replace("-", "_")] = mod
                    spec.loader.exec_module(mod)
                    plugin_router = getattr(mod, attr_name, None)
                    if plugin_router:
                        prefix = f"/api/v1/plugin/{pid}"
                        added = 0
                        mount_idx = None
                        for i, r in enumerate(app.routes):
                            if type(r).__name__ == "Mount":
                                mount_idx = i
                                break

                        for route in plugin_router.routes:
                            full_path = prefix + route.path
                            methods = set(route.methods) if route.methods else {"GET"}
                            new_route = _AR(
                                path=full_path,
                                endpoint=route.endpoint,
                                methods=methods,
                                name=route.name,
                                dependencies=[Depends(_make_plugin_ctx_depender(pid))],
                            )
                            if mount_idx is not None:
                                app.router.routes.insert(mount_idx, new_route)
                                mount_idx += 1
                            else:
                                app.router.routes.append(new_route)
                            added += 1

                        # 前端文件服务路由
                        frontend_dir = plugin_dir / "frontend"
                        if frontend_dir.is_dir():
                            def _serve_frontend(path: str,
                                                _plugin_dir=plugin_dir,
                                                _pid=pid):
                                file_path = (_plugin_dir / "frontend" / path).resolve()
                                # 防目录穿越
                                if not str(file_path).startswith(str(frontend_dir.resolve())):
                                    return JSONResponse({"detail": "Not Found"}, status_code=404)
                                if not file_path.is_file():
                                    return JSONResponse({"detail": "Not Found"}, status_code=404)
                                return FileResponse(
                                    str(file_path),
                                    media_type=_build_content_type(path),
                                )

                            new_route = _AR(
                                path=f"/api/v1/plugin/{pid}/frontend/{{path:path}}",
                                endpoint=_serve_frontend,
                                methods=["GET"],
                                name=f"{pid}_frontend_serve",
                            )
                            if mount_idx is not None:
                                app.router.routes.insert(mount_idx, new_route)
                            else:
                                app.router.routes.append(new_route)
                            added += 1

                        logger.info("插件 %s 路由已注册: %s (%d 条)", pid, prefix, added)

                # 清理注入
                _sdk._event_bus_ref = None
                _sdk.set_current_plugin_id(None)
            except Exception as e:
                import traceback
                logger.error("插件 %s 路由加载失败: %s", pid, e)
                traceback.print_exc()

    # ── 事件订阅白名单 ──
    events = manifest.get("events", {})
    publish_events = events.get("publish", [])
    if publish_events:
        event_bus.set_publish_whitelist(pid, publish_events)

    # ── 前端模块 ──
    frontend_module = None
    fe = manifest.get("frontend")
    if fe:
        frontend_module = fe.get("module")
        if frontend_module:
            frontend_module["plugin_id"] = pid

    # ── 恢复 DB 里的配置（避免重启/卸载后重装 config 回默认值） ──
    existing_meta = registry.get(pid)
    db_config = await _load_config_from_db(registry, pid)
    if db_config:
        config = db_config
    elif existing_meta and existing_meta.config:
        config = existing_meta.config
    else:
        config = manifest.get("config", {})
        schema = manifest.get("config_schema", {})
        if isinstance(schema, dict):
            defaults = {}
            for key, spec in schema.items():
                if isinstance(spec, dict) and "default" in spec:
                    defaults[key] = spec["default"]
            if defaults:
                config = {**defaults, **config}

    metadata = PluginMetadata(
        id=pid,
        name=manifest["name"],
        version=manifest["version"],
        author=manifest.get("author", ""),
        description=manifest.get("description", ""),
        manifest=manifest,
        status=PluginStatus.ENABLED,
        config=config,
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
    await registry.save_to_db()
    logger.info("插件加载完成: %d 个", len(loaded))
    return loaded
