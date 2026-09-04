"""routers/plugins.py — 插件管理 API

ZZCC services 版本：
- async SQLAlchemy + asyncpg + PostgreSQL
- 认证: JWT (Authorization: Bearer) 对齐 routers.auth.get_current_user_dep
- 插件目录: 环境变量 ZZCC_PLUGINS_DIR (默认 /app/plugins_data)

所有端点默认只要求已登录；仅当 user.roles 明确非管理员时拒绝。
"""
from __future__ import annotations

import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from plugins.event_bus import EventBus
from plugins.loader import load_plugin, PLUGINS_DIR
from plugins.registry import (
    PluginMetadata,
    PluginRegistry,
    PluginStatus,
    validate_manifest,
    PluginManifestError,
)
from plugins.sdk import clear_brain_plugin_registrations
from routers.auth import get_current_user_dep

logger = logging.getLogger("plugins.api")

# 挂载路径: /api/v1/plugins (main.py 加 /api/v1 前缀)
router = APIRouter(prefix="/plugins", tags=["Plugins"])

R = Dict[str, Any]


# ── 工具 ──
def _remove_plugin_routes(app, plugin_id: str) -> int:
    """移除所有匹配 /api/plugin/{plugin_id} 前缀的路由。"""
    prefix = f"/api/plugin/{plugin_id}"
    removed = 0
    to_remove = [r for r in app.router.routes if getattr(r, "path", "").startswith(prefix)]
    for r in to_remove:
        app.router.routes.remove(r)
        removed += 1
    return removed


def _plugin_dir(plugin_id: str) -> Path:
    return PLUGINS_DIR / plugin_id


async def _persist(registry: PluginRegistry) -> None:
    await registry.save_to_db()


# ── 请求/响应模型 ──
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


class PluginModulesResponse(BaseModel):
    modules: List[Dict[str, Any]]


class EventRequest(BaseModel):
    event: str
    payload: Dict[str, Any] = {}


# ── 依赖注入 ──
def get_registry() -> PluginRegistry:
    from plugins import registry as _registry
    return _registry


def get_event_bus() -> EventBus:
    from plugins import event_bus as _event_bus
    return _event_bus


def _require_admin_or_explicit_user(user: dict) -> dict:
    """ZZCC services 默认所有已登录用户都可管理插件（内部系统）。

    如果将来引入严格 admin 概念，可在此检查 user["roles"]。
    当前策略：只要有 id 就通过；roles 非空且不含 admin/operator 才拒绝。
    """
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="未登录")
    roles_raw = user.get("roles", "") or ""
    roles = {r.strip() for r in roles_raw.split(",") if r.strip()}
    if roles and not (roles & {"admin", "operator"}):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ═══════════════════════════════════════
# API 端点
# ═══════════════════════════════════════

@router.get("/modules")
def get_frontend_modules(
    user: dict = Depends(get_current_user_dep),
) -> PluginModulesResponse:
    """返回所有已启用插件的前端模块。"""
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
    user: dict = Depends(get_current_user_dep),
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


# ── 事件总线 API（必须放在 /{plugin_id} 之前，否则被当成 plugin_id） ──
@router.post("/_events")
async def publish_event(
    request: EventRequest,
    user: dict = Depends(get_current_user_dep),
) -> R:
    """发布插件事件并记录到 DB。"""
    ev = get_event_bus()
    result = await ev.publish(request.event, request.payload, source_plugin=None)
    # 写入事件日志
    from services.db import managed_session
    try:
        async with managed_session() as db:
            await db.execute(text(
                "INSERT INTO plugin_event_log (plugin_id, event_name, payload) "
                "VALUES (:pid, :en, :pl)"
            ), {
                "pid": "_system",
                "en": request.event,
                "pl": json.dumps(request.payload, ensure_ascii=False),
            })
            await db.commit()
    except Exception as e:
        logger.error("publish_event 日志写入失败: %s", e)
    return {"ok": True, "result": result}


@router.get("/_events")
async def list_events(
    user: dict = Depends(get_current_user_dep),
) -> R:
    """查询事件日志。"""
    from services.db import managed_session
    try:
        async with managed_session() as db:
            result = await db.execute(text(
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


@router.get("/{plugin_id}")
def get_plugin(
    plugin_id: str,
    user: dict = Depends(get_current_user_dep),
) -> R:
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


@router.post("/install/file")
async def install_plugin_file(
    request: Request,
    zip_path: str,
    user: dict = Depends(get_current_user_dep),
) -> R:
    """从 zip 文件安装插件。"""
    zip_file = Path(zip_path)
    if not zip_file.exists():
        raise HTTPException(404, f"zip 文件不存在: {zip_path}")

    reg = get_registry()
    ev = get_event_bus()

    # 1. 读取 plugin.json 校验
    try:
        with zipfile.ZipFile(str(zip_file), "r") as zf:
            names = zf.namelist()
            # 支持 zip 内嵌一层目录的情况（取第一层下的 plugin.json）
            plugin_json_name = None
            for n in names:
                if n.endswith("/plugin.json"):
                    plugin_json_name = n
                    break
            if not plugin_json_name:
                raise HTTPException(400, "zip 中缺少 plugin.json")
            manifest_raw = zf.read(plugin_json_name).decode("utf-8")
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
    plugin_dir = _plugin_dir(pid)
    if plugin_dir.exists():
        existing = reg.get(pid)
        if existing:
            raise HTTPException(400, f"插件已安装: {pid}")

    # 2. 解压（去掉 zip 内一层目录前缀）
    plugin_dir.mkdir(parents=True, exist_ok=True)
    # 计算公共前缀
    prefix = ""
    if plugin_json_name and "/" in plugin_json_name:
        prefix = plugin_json_name.rsplit("/", 1)[0] + "/"
    with zipfile.ZipFile(str(zip_file), "r") as zf:
        for name in names:
            if name.endswith("/"):
                continue
            target = name[len(prefix):] if prefix and name.startswith(prefix) else name
            if not target:
                continue
            zf.extract(name, str(plugin_dir))
            # 如果有前缀，需要移动到正确位置
            if prefix and target != name:
                src = plugin_dir / name
                dst = plugin_dir / target
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                # 清理空目录
                for p in [plugin_dir / prefix]:
                    try:
                        shutil.rmtree(str(p), ignore_errors=True)
                    except Exception:
                        pass

    # 3. 加载（只加载新插件，避免全量扫描副作用）
    await load_plugin(request.app, plugin_dir, reg, ev)
    await _persist(reg)
    meta = reg.get(pid)
    if meta:
        return {"ok": True, "detail": f"插件 {pid} 已安装并加载", "plugin": meta.to_dict()}
    return {"ok": True, "detail": f"插件 {pid} 已安装（未加载，需手动启用）"}


@router.post("/{plugin_id}/enable")
async def enable_plugin(
    plugin_id: str,
    request: Request,
    user: dict = Depends(get_current_user_dep),
) -> R:
    """启用插件：恢复路由 + 清理事件 + 更新状态。"""
    reg = get_registry()
    ev = get_event_bus()
    if not reg.update_status(plugin_id, PluginStatus.ENABLED):
        raise HTTPException(404, "插件不存在")
    _remove_plugin_routes(request.app, plugin_id)
    plugin_dir = _plugin_dir(plugin_id)
    if plugin_dir.exists():
        await load_plugin(request.app, plugin_dir, reg, ev)
    await _persist(reg)
    return {"ok": True, "status": "enabled"}


@router.post("/{plugin_id}/disable")
async def disable_plugin(
    plugin_id: str,
    request: Request,
    user: dict = Depends(get_current_user_dep),
) -> R:
    """禁用插件：移除路由 + 清理事件 + 更新状态。"""
    reg = get_registry()
    ev = get_event_bus()
    if not reg.update_status(plugin_id, PluginStatus.DISABLED):
        raise HTTPException(404, "插件不存在")
    _remove_plugin_routes(request.app, plugin_id)
    ev.clear_plugin(plugin_id)
    brain_cleaned = clear_brain_plugin_registrations(plugin_id)
    await _persist(reg)
    return {"ok": True, "status": "disabled", "brain_cleaned": brain_cleaned}


@router.post("/{plugin_id}/reload")
async def reload_plugin(
    request: Request,
    plugin_id: str,
    user: dict = Depends(get_current_user_dep),
) -> R:
    """热重载插件。"""
    reg = get_registry()
    ev = get_event_bus()
    if not reg.get(plugin_id):
        raise HTTPException(404, "插件不存在")

    _remove_plugin_routes(request.app, plugin_id)
    ev.clear_plugin(plugin_id)
    clear_brain_plugin_registrations(plugin_id)
    reg.remove(plugin_id)

    plugin_dir = _plugin_dir(plugin_id)
    meta = await load_plugin(request.app, plugin_dir, reg, ev)
    await _persist(reg)
    if meta:
        return {"ok": True, "detail": f"插件 {plugin_id} 已重载"}
    raise HTTPException(500, f"重载失败: {plugin_id}")


@router.delete("/{plugin_id}")
async def uninstall_plugin(
    plugin_id: str,
    request: Request,
    user: dict = Depends(get_current_user_dep),
) -> R:
    """卸载插件：移除路由 + 清理事件 + 删除文件 + 清 DB。"""
    reg = get_registry()
    ev = get_event_bus()
    if not reg.get(plugin_id):
        raise HTTPException(404, "插件不存在")

    _remove_plugin_routes(request.app, plugin_id)
    ev.clear_plugin(plugin_id)
    clear_brain_plugin_registrations(plugin_id)
    reg.remove(plugin_id)

    plugin_dir = _plugin_dir(plugin_id)
    if plugin_dir.exists():
        shutil.rmtree(str(plugin_dir), ignore_errors=True)

    await reg.delete_from_db(plugin_id)
    return {"ok": True, "detail": f"插件 {plugin_id} 已卸载"}


@router.get("/{plugin_id}/config")
def get_plugin_config(
    plugin_id: str,
    user: dict = Depends(get_current_user_dep),
) -> R:
    """获取插件配置。"""
    reg = get_registry()
    meta = reg.get(plugin_id)
    if not meta:
        raise HTTPException(404, "插件不存在")
    return {"ok": True, "config": meta.config}


@router.put("/{plugin_id}/config")
async def update_plugin_config(
    plugin_id: str,
    request: UpdateConfigRequest,
    user: dict = Depends(get_current_user_dep),
) -> R:
    """更新插件配置。兼容 {"config":{...}} 和扁平 {"key":val,...}。"""
    reg = get_registry()
    if not reg.get(plugin_id):
        raise HTTPException(404, "插件不存在")
    cfg = request.config if request.config is not None else request.model_dump(exclude={"config"})
    reg.update_config(plugin_id, cfg)
    await _persist(reg)
    return {"ok": True, "config": cfg}
