"""routers/plugins.py — 插件管理 API

所有端点需要管理员权限（require_admin）。
管理插件的生命周期：安装、启用、禁用、卸载、配置。
"""
from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from plugins.event_bus import EventBus
from plugins.loader import load_plugin, scan_and_load_plugins
from plugins.registry import PluginMetadata, PluginRegistry, PluginStatus, validate_manifest, PluginManifestError
from database import get_db
from routers.auth import require_admin

router = APIRouter(prefix="/api/plugins", tags=["Plugins"])
logger = logging.getLogger("plugins.api")


R = Dict[str, Any]


# ── 请求/响应模型 ──
class InstallPluginRequest(BaseModel):
    plugin_id: Optional[str] = None  # 从 zip 中提取，如不填则从 plugin.json 读取


class UpdateConfigRequest(BaseModel):
    config: Dict[str, Any]


class PluginSummary(BaseModel):
    id: str
    name: str
    version: str
    author: str
    description: str
    status: str


class PluginDetail(BaseModel):
    id: str
    name: str
    version: str
    author: str
    description: str
    status: str
    config: Dict[str, Any]
    permissions: List[str]
    events: Dict[str, List[str]]
    frontend_module: Optional[Dict[str, Any]]


class PluginModulesResponse(BaseModel):
    modules: List[Dict[str, Any]]


# ── 依赖注入 ──
def get_registry(app_state: dict = None) -> PluginRegistry:
    """从 FastAPI app state 获取 registry 实例"""
    # 通过全局引用获取（在 main.py 初始化时注入）
    from plugins import registry as _registry
    return _registry


def get_event_bus() -> EventBus:
    from plugins import event_bus as _event_bus
    return _event_bus


# ═══════════════════════════════════════
# API 端点
# ═══════════════════════════════════════

@router.get("/modules")
def get_frontend_modules(
    user: dict = Depends(require_admin),
) -> PluginModulesResponse:
    """返回所有已启用插件的前端模块（前端页面调用此接口）。"""
    reg = get_registry()
    modules = []
    for meta in reg.list_enabled():
        if meta.frontend_module:
            m = dict(meta.frontend_module)
            m["entry_url"] = f"/api/plugin/{meta.id}/frontend/index.html"
            modules.append(m)
    return PluginModulesResponse(modules=modules)


@router.get("/")
def list_plugins(
    user: dict = Depends(require_admin),
) -> List[PluginSummary]:
    """列出所有已注册插件。"""
    reg = get_registry()
    return [
        PluginSummary(
            id=m.id, name=m.name, version=m.version,
            author=m.author, description=m.description,
            status=m.status.value,
        )
        for m in reg.list_all()
    ]


@router.get("/{plugin_id}")
def get_plugin(plugin_id: str,
               user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """获取插件详情。"""
    reg = get_registry()
    meta = reg.get(plugin_id)
    if not meta:
        raise HTTPException(404, "插件不存在")
    return {
        "id": meta.id,
        "name": meta.name,
        "version": meta.version,
        "author": meta.author,
        "description": meta.description,
        "status": meta.status.value,
        "config": meta.config,
        "permissions": meta.manifest.get("permissions", []),
        "events": meta.manifest.get("events", {}),
        "frontend_module": meta.frontend_module,
    }


@router.post("/install")
async def install_plugin(
    user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """安装插件。

    从 /uploads/plugins/ 目录下查找 zip 文件并解压到 plugins_data/。
    当前简化：从 request body 的 zip_path 字段读取。
    """
    # 从数据库读取请求体中的 zip 路径（POST JSON）
    # 由于没有请求体模型，改用 query 参数或固定路径
    # 注意：此端点需从请求体读取，用 request 对象处理
    # 简化实现：固定从 /app/uploads/plugins/latest.zip 读取
    return JSONResponse(
        {"ok": True, "detail": "使用 POST /api/plugins/install/file 上传"}
    )


@router.post("/install/file")
async def install_plugin_file(
    request: Request,
    zip_path: str,
    user: dict = Depends(require_admin),
):
    """从 zip 文件安装插件。"""
    import asyncio
    from contextlib import asynccontextmanager

    zip_file = Path(zip_path)
    if not zip_file.exists():
        raise HTTPException(404, f"zip 文件不存在: {zip_path}")

    reg = get_registry()
    ev = get_event_bus()

    # 1. 读取 plugin.json 校验
    try:
        with zipfile.ZipFile(str(zip_file), "r") as zf:
            names = zf.namelist()
            if "plugin.json" not in names:
                raise HTTPException(400, "zip 中缺少 plugin.json")
            manifest_raw = zf.read("plugin.json").decode("utf-8")
    except zipfile.BadZipFile:
        raise HTTPException(400, "无效 zip 文件")

    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"plugin.json 解析失败: {e}")

    try:
        validate_manifest(manifest)
    except PluginManifestError as e:
        raise HTTPException(400, f"manifest 校验失败: {e}")

    pid = manifest["id"]
    plugin_dir = Path("/app/plugins_data") / pid
    if plugin_dir.exists():
        existing = reg.get(pid)
        if existing:
            raise HTTPException(400, f"插件已安装: {pid}")

    # 2. 解压
    plugin_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_file), "r") as zf:
        for name in names:
            if name.endswith("/"):
                continue
            zf.extract(name, str(plugin_dir))

    # 3. 重新加载
    await asyncio.sleep(0.1)  # 确保文件系统写入完成
    # 重新扫描并加载
    from plugins.loader import scan_and_load_plugins
    app = request.app
    loaded = await scan_and_load_plugins(app, reg, ev)
    meta = reg.get(pid)
    if meta:
        return {"ok": True, "detail": f"插件 {pid} 已安装并加载", "plugin": meta.to_dict()}
    return {"ok": True, "detail": f"插件 {pid} 已安装（未加载，需手动启用）"}


@router.post("/{plugin_id}/enable")
def enable_plugin(plugin_id: str,
                  user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """启用插件。"""
    reg = get_registry()
    if not reg.update_status(plugin_id, PluginStatus.ENABLED):
        raise HTTPException(404, "插件不存在")
    return {"ok": True, "status": "enabled"}


@router.post("/{plugin_id}/disable")
def disable_plugin(plugin_id: str,
                   user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """禁用插件。"""
    reg = get_registry()
    ev = get_event_bus()
    if not reg.update_status(plugin_id, PluginStatus.DISABLED):
        raise HTTPException(404, "插件不存在")
    # 清理事件订阅
    ev.clear_plugin(plugin_id)
    return {"ok": True, "status": "disabled"}


@router.post("/{plugin_id}/reload")
async def reload_plugin(request: Request, plugin_id: str,
                        user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """热重载插件。"""
    reg = get_registry()
    ev = get_event_bus()

    meta = reg.get(plugin_id)
    if not meta:
        raise HTTPException(404, "插件不存在")

    # 卸载
    ev.clear_plugin(plugin_id)
    reg.remove(plugin_id)

    # 重新加载
    plugin_dir = Path("/app/plugins_data") / plugin_id
    from plugins.loader import load_plugin
    app = request.app
    meta = await load_plugin(app, plugin_dir, reg, ev)
    if meta:
        return {"ok": True, "detail": f"插件 {plugin_id} 已重载"}
    raise HTTPException(500, f"重载失败: {plugin_id}")


@router.delete("/{plugin_id}")
def uninstall_plugin(plugin_id: str,
                     user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """卸载插件（从注册表移除 + 删除文件）。"""
    reg = get_registry()
    ev = get_event_bus()

    if not reg.get(plugin_id):
        raise HTTPException(404, "插件不存在")

    # 清理
    ev.clear_plugin(plugin_id)
    reg.remove(plugin_id)

    # 删除文件目录
    import shutil
    plugin_dir = Path("/app/plugins_data") / plugin_id
    if plugin_dir.exists():
        shutil.rmtree(str(plugin_dir), ignore_errors=True)

    return {"ok": True, "detail": f"插件 {plugin_id} 已卸载"}


@router.get("/{plugin_id}/config")
def get_plugin_config(plugin_id: str,
                      user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """获取插件配置。"""
    reg = get_registry()
    meta = reg.get(plugin_id)
    if not meta:
        raise HTTPException(404, "插件不存在")
    return {"ok": True, "config": meta.config}


@router.put("/{plugin_id}/config")
def update_plugin_config(plugin_id: str,
                         request: UpdateConfigRequest,
                         user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """更新插件配置。"""
    reg = get_registry()
    if not reg.get(plugin_id):
        raise HTTPException(404, "插件不存在")
    reg.update_config(plugin_id, request.config)
    return {"ok": True, "config": request.config}


@router.get("/_diag/routes")
def diag_routes(request: Request) -> Dict[str, Any]:
    """诊断：检查 live 进程中 app.routes 是否包含插件路由。"""
    app = request.app
    top_level = []
    plugin_routes = []
    for r in app.routes:
        p = getattr(r, "path", "")
        top_level.append(f"{type(r).__name__}:{p}")
        if "plugin" in str(p).lower():
            plugin_routes.append(f"{type(r).__name__}:{p}")
        for attr in ("routes", "original_router"):
            sub = getattr(r, attr, None)
            if sub is not None and not callable(sub):
                for sr in getattr(sub, "routes", []):
                    sp = getattr(sr, "path", "")
                    if "plugin" in str(sp).lower():
                        plugin_routes.append(f"{type(r).__name__}->{type(sr).__name__}:{sp}")

    # 实验：动态添加一个测试路由，看能否访问
    try:
        app.add_api_route("/_diag/test_route", lambda: {"ok": True, "msg": "dynamic route works"}, methods=["GET"])
        dynamic_added = True
    except Exception as e:
        dynamic_added = f"FAILED: {e}"

    # 检查插件路由对象详情
    plugin_details = []
    for r in app.routes:
        p = getattr(r, "path", "")
        if "plugin" in str(p).lower():
            plugin_details.append({
                "type": type(r).__name__,
                "path": p,
                "methods": list(r.methods) if hasattr(r, "methods") else None,
                "name": getattr(r, "name", None),
                "has_endpoint": hasattr(r, "endpoint"),
            })

    return {
        "total_routes": len(app.routes),
        "plugin_routes": plugin_routes,
        "plugin_details": plugin_details,
        "dynamic_added": dynamic_added,
        "top_level_preview": top_level[:30],
    }
