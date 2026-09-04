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
from pydantic import BaseModel, ConfigDict

from plugins.event_bus import EventBus
from plugins.loader import load_plugin, scan_and_load_plugins, PLUGINS_DIR
from plugins.registry import PluginMetadata, PluginRegistry, PluginStatus, validate_manifest, PluginManifestError
from database import get_db
from routers.auth import require_admin

router = APIRouter(prefix="/api/plugins", tags=["Plugins"])
logger = logging.getLogger("plugins.api")


R = Dict[str, Any]


# ── 路由清理工具 ──
def _remove_plugin_routes(app, plugin_id: str) -> int:
    """移除所有匹配 /api/plugin/{plugin_id} 前缀的路由。"""
    prefix = f"/api/plugin/{plugin_id}"
    removed = 0
    to_remove = [r for r in app.router.routes if getattr(r, 'path', '').startswith(prefix)]
    for r in to_remove:
        app.router.routes.remove(r)
        removed += 1
    return removed


# ── 请求/响应模型 ──
class InstallPluginRequest(BaseModel):
    plugin_id: Optional[str] = None  # 从 zip 中提取，如不填则从 plugin.json 读取


class UpdateConfigRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    config: Optional[Dict[str, Any]] = None


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



# ── 事件总线 API ──
class EventRequest(BaseModel):
    event: str
    payload: Dict[str, Any] = {}


@router.post("/_events")
async def publish_event(request: EventRequest,
                        user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """发布插件事件并记录到数据库。"""
    ev = get_event_bus()
    result = await ev.publish(request.event, request.payload, source_plugin=None)
    # 写入事件日志
    from database import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        db.execute(text(
            "INSERT INTO plugin_event_log (plugin_id, event_name, payload) VALUES (:pid, :en, :pl)"
        ), {"pid": "_system", "en": request.event, "pl": json.dumps(request.payload)})
        db.commit()
    except Exception:
        pass
    finally:
        db.close()
    return {"ok": True, "result": result}


@router.get("/_events")
def list_events(request: Request,
                user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """查询事件日志。"""
    from database import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        result = db.execute(text(
            "SELECT event_name, payload, plugin_id, created_at "
            "FROM plugin_event_log ORDER BY created_at DESC LIMIT 100"
        ))
        rows = result.fetchall()
        events = []
        for r in rows:
            events.append({
                "event_name": r[0],
                "payload": json.loads(r[1]) if isinstance(r[1], str) else r[1],
                "source_plugin": r[2] if r[2] != "_system" else None,
                "created_at": str(r[3]) if r[3] else None,
            })
        return {"ok": True, "events": events}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        db.close()


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
    plugin_dir = PLUGINS_DIR / pid
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
async def enable_plugin(plugin_id: str, request: Request,
                        user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """启用插件：恢复路由 + 清理事件 + 更新状态。"""
    reg = get_registry()
    ev = get_event_bus()
    if not reg.update_status(plugin_id, PluginStatus.ENABLED):
        raise HTTPException(404, "插件不存在")
    # 清理可能的残留路由，然后重新加载
    _remove_plugin_routes(request.app, plugin_id)
    plugin_dir = PLUGINS_DIR / plugin_id
    if plugin_dir.exists():
        from plugins.loader import load_plugin
        await load_plugin(request.app, plugin_dir, reg, ev)
    return {"ok": True, "status": "enabled"}


@router.post("/{plugin_id}/disable")
def disable_plugin(plugin_id: str, request: Request,
                   user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """禁用插件：移除路由 + 清理事件 + 更新状态。"""
    reg = get_registry()
    ev = get_event_bus()
    if not reg.update_status(plugin_id, PluginStatus.DISABLED):
        raise HTTPException(404, "插件不存在")
    _remove_plugin_routes(request.app, plugin_id)
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

    # 卸载：清除路由 + 事件 + 注册表
    _remove_plugin_routes(request.app, plugin_id)
    ev.clear_plugin(plugin_id)
    reg.remove(plugin_id)

    # 重新加载
    plugin_dir = PLUGINS_DIR / plugin_id
    from plugins.loader import load_plugin
    app = request.app
    meta = await load_plugin(app, plugin_dir, reg, ev)
    if meta:
        return {"ok": True, "detail": f"插件 {plugin_id} 已重载"}
    raise HTTPException(500, f"重载失败: {plugin_id}")


@router.delete("/{plugin_id}")
def uninstall_plugin(plugin_id: str, request: Request,
                     user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """卸载插件：移除路由 + 清理事件 + 从注册表移除 + 删除文件。"""
    reg = get_registry()
    ev = get_event_bus()

    if not reg.get(plugin_id):
        raise HTTPException(404, "插件不存在")

    # 清理路由 + 事件 + 注册表
    _remove_plugin_routes(request.app, plugin_id)
    ev.clear_plugin(plugin_id)
    reg.remove(plugin_id)

    # 删除文件目录
    import shutil
    plugin_dir = PLUGINS_DIR / plugin_id
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
    """更新插件配置。兼容 {"config":{...}} 和扁平 {"key":val,...} 两种格式。"""
    reg = get_registry()
    if not reg.get(plugin_id):
        raise HTTPException(404, "插件不存在")
    cfg = request.config if request.config is not None else request.model_dump(exclude={"config"})
    reg.update_config(plugin_id, cfg)
    return {"ok": True, "config": cfg}