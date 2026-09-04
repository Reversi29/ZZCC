"""routers/plugin_marketplace.py — 插件广场 API

定位：类似 VSCode / DashScope 插件市场的“可分享插件包”。
当前阶段提供最小闭环：
- 发布插件 zip 到本机 market 目录
- 浏览 / 搜索已发布插件
- 按插件包名安装到当前插件系统
- 上传下载统计

存储：/data/plugin_market/<pkg_id>/<pkg_id>.zip（容器默认，可用 ZZCC_PLUGIN_MARKET_DIR 覆盖）
"""
from __future__ import annotations

import json
import logging
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from plugins.loader import PLUGINS_DIR, load_plugin
from plugins.registry import PluginManifestError, PluginStatus, validate_manifest
from routers.auth import get_current_user_dep
from routers.plugins import _persist, _plugin_dir, get_event_bus, get_registry

logger = logging.getLogger("plugins.marketplace")

router = APIRouter(prefix="/plugin-market", tags=["Plugin Marketplace"])
R = Dict[str, Any]

MARKET_DIR = Path(__import__("os").environ.get("ZZCC_PLUGIN_MARKET_DIR", "/app/plugin_market"))


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    category: str = "general"
    tags: List[str] = []
    readme: str = ""
    publisher: str = ""


class InstallResult(BaseModel):
    package_id: str
    plugin_id: str
    version: str
    installed: bool
    detail: str


def _market_dir() -> Path:
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    return MARKET_DIR


def _pkg_dir(pkg_id: str) -> Path:
    return _market_dir() / pkg_id


def _zip_path(pkg_id: str) -> Path:
    return _pkg_dir(pkg_id) / f"{pkg_id}.zip"


def _meta_path(pkg_id: str) -> Path:
    return _pkg_dir(pkg_id) / "market.json"


def _ensure_table() -> None:
    """懒初始化下载/安装统计；失败不阻塞市场 API 的本地浏览。"""
    # 实际建表在 lifespan 完成；这里保留 helper 便于将来迁移。


async def _read_meta(pkg_id: str) -> Dict[str, Any]:
    path = _meta_path(pkg_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def _write_meta(pkg_id: str, meta: Dict[str, Any]) -> None:
    d = _pkg_dir(pkg_id)
    d.mkdir(parents=True, exist_ok=True)
    _meta_path(pkg_id).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


async def _incr_counter(pkg_id: str, field: str) -> None:
    meta = await _read_meta(pkg_id)
    meta[field] = int(meta.get(field, 0)) + 1
    await _write_meta(pkg_id, meta)


def _public_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    data = {
        "package_id": meta.get("package_id"),
        "plugin_id": meta.get("plugin_id"),
        "name": meta.get("name"),
        "version": meta.get("version"),
        "author": meta.get("author"),
        "publisher": meta.get("publisher"),
        "description": meta.get("description"),
        "category": meta.get("category", "general"),
        "tags": meta.get("tags", []),
        "permissions": meta.get("permissions", []),
        "events": meta.get("events", {}),
        "readme": meta.get("readme", ""),
        "downloads": int(meta.get("downloads", 0)),
        "installs": int(meta.get("installs", 0)),
        "published_at": meta.get("published_at"),
        "updated_at": meta.get("updated_at"),
        "size_bytes": int(meta.get("size_bytes", 0)),
    }
    return {k: v for k, v in data.items() if v is not None}


def _read_manifest_from_zip(zip_path: Path) -> Dict[str, Any]:
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        names = zf.namelist()
        plugin_json_name = next((n for n in names if n == "plugin.json" or n.endswith("/plugin.json")), None)
        if not plugin_json_name:
            raise ValueError("zip 中缺少 plugin.json")
        manifest = json.loads(zf.read(plugin_json_name).decode("utf-8"))
    validate_manifest(manifest)
    return manifest


async def _list_packages() -> List[Dict[str, Any]]:
    root = _market_dir()
    if not root.exists():
        return []
    pkgs: List[Dict[str, Any]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not _zip_path(d.name).exists():
            continue
        meta = await _read_meta(d.name)
        if meta:
            pkgs.append(_public_meta(meta))
    pkgs.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return pkgs


async def _install_package(app, pkg_id: str) -> R:
    """从插件广场安装到当前插件系统。"""
    zip_path = _zip_path(pkg_id)
    if not zip_path.exists():
        raise HTTPException(404, "插件包不存在")

    manifest = _read_manifest_from_zip(zip_path)
    plugin_id = manifest["id"]
    plugin_dir = _plugin_dir(plugin_id)

    reg = get_registry()
    ev = get_event_bus()
    if reg.get(plugin_id):
        raise HTTPException(409, f"插件已安装，请先卸载: {plugin_id}")

    # 解压到安装目录
    plugin_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        names = zf.namelist()
        plugin_json_name = next((n for n in names if n == "plugin.json" or n.endswith("/plugin.json")), None)
        prefix = ""
        if plugin_json_name and "/" in plugin_json_name:
            prefix = plugin_json_name.rsplit("/", 1)[0] + "/"
        for name in names:
            if name.endswith("/"):
                continue
            target = name[len(prefix):] if prefix and name.startswith(prefix) else name
            if not target:
                continue
            zf.extract(name, str(plugin_dir))
            if prefix and target != name:
                src = plugin_dir / name
                dst = plugin_dir / target
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                for p in [plugin_dir / prefix]:
                    try:
                        shutil.rmtree(str(p), ignore_errors=True)
                    except Exception:
                        pass

    meta = await load_plugin(app, plugin_dir, reg, ev)
    await _persist(reg)
    await _incr_counter(pkg_id, "installs")
    if meta:
        return {
            "ok": True,
            "package_id": pkg_id,
            "plugin_id": plugin_id,
            "version": meta.version,
            "installed": True,
            "detail": f"插件 {plugin_id} 已从插件广场安装并加载",
        }
    return {
        "ok": True,
        "package_id": pkg_id,
        "plugin_id": plugin_id,
        "version": manifest.get("version"),
        "installed": False,
        "detail": f"插件 {plugin_id} 已安装但未加载，请检查 routes 配置",
    }


@router.get("/packages")
async def list_packages(
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    user: dict = Depends(get_current_user_dep),
) -> R:
    """列出插件广场中的可分享插件包。"""
    pkgs = await _list_packages()
    if category:
        pkgs = [p for p in pkgs if p.get("category") == category]
    if tag:
        pkgs = [p for p in pkgs if tag in (p.get("tags") or [])]
    if q:
        needle = q.lower()
        def matches(p: Dict[str, Any]) -> bool:
            hay = " ".join(str(p.get(k, "")) for k in ["plugin_id", "name", "description", "author", "publisher"])
            return needle in hay.lower() or any(needle in str(t).lower() for t in p.get("tags", []))
        pkgs = [p for p in pkgs if matches(p)]
    return {"ok": True, "count": len(pkgs), "packages": pkgs}


@router.get("/categories")
async def list_categories(user: dict = Depends(get_current_user_dep)) -> R:
    """返回插件分类聚合。"""
    pkgs = await _list_packages()
    counts: Dict[str, int] = {}
    for p in pkgs:
        c = p.get("category") or "general"
        counts[c] = counts.get(c, 0) + 1
    return {"ok": True, "categories": [{"name": k, "count": v} for k, v in sorted(counts.items())]}


@router.get("/packages/{pkg_id}")
async def get_package(pkg_id: str, user: dict = Depends(get_current_user_dep)) -> R:
    """获取插件包详情。"""
    zip_path = _zip_path(pkg_id)
    if not zip_path.exists():
        raise HTTPException(404, "插件包不存在")
    meta = await _read_meta(pkg_id)
    return {"ok": True, "package": _public_meta(meta)}


@router.post("/packages/{pkg_id}/download")
async def download_package(pkg_id: str, user: dict = Depends(get_current_user_dep)) -> R:
    """返回插件 zip 下载路径（生产可替换为流式文件下载）。"""
    zip_path = _zip_path(pkg_id)
    if not zip_path.exists():
        raise HTTPException(404, "插件包不存在")
    await _incr_counter(pkg_id, "downloads")
    return {"ok": True, "package_id": pkg_id, "path": str(zip_path), "size_bytes": zip_path.stat().st_size}


@router.post("/publish", status_code=201)
async def publish_package(
    file: UploadFile = File(...),
    category: str = Query("general"),
    tags: str = Query(""),
    readme: str = Query(""),
    publisher: str = Query(""),
    user: dict = Depends(get_current_user_dep),
) -> R:
    """上传并发布插件 zip 到插件广场。"""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "仅支持 zip 插件包")

    pkg_id = f"pkg_{uuid.uuid4().hex[:12]}"
    d = _pkg_dir(pkg_id)
    d.mkdir(parents=True, exist_ok=True)
    zip_path = d / f"{pkg_id}.zip"

    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(400, "插件包不能超过 20MB")
    zip_path.write_bytes(raw)

    try:
        manifest = _read_manifest_from_zip(zip_path)
    except (zipfile.BadZipFile, json.JSONDecodeError, ValueError, PluginManifestError) as e:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(400, f"插件包校验失败: {e}")

    from datetime import datetime, timezone

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    meta = {
        "package_id": pkg_id,
        "plugin_id": manifest["id"],
        "name": manifest.get("name", manifest["id"]),
        "version": manifest.get("version", ""),
        "author": manifest.get("author", ""),
        "publisher": publisher or manifest.get("author", ""),
        "description": manifest.get("description", ""),
        "category": category or "general",
        "tags": tag_list,
        "permissions": manifest.get("permissions", []),
        "events": manifest.get("events", {}),
        "readme": readme,
        "downloads": 0,
        "installs": 0,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": zip_path.stat().st_size,
    }
    await _write_meta(pkg_id, meta)
    return {"ok": True, "detail": f"插件包已发布: {pkg_id}", "package": _public_meta(meta)}


@router.post("/packages/{pkg_id}/install")
async def install_package(pkg_id: str, request: Request, user: dict = Depends(get_current_user_dep)) -> R:
    """从插件广场安装指定插件包到当前插件系统。"""
    return await _install_package(request.app, pkg_id)


@router.delete("/packages/{pkg_id}")
async def delete_package(pkg_id: str, user: dict = Depends(get_current_user_dep)) -> R:
    """删除已发布插件包（不影响已安装到插件系统的副本）。"""
    d = _pkg_dir(pkg_id)
    if not d.exists():
        raise HTTPException(404, "插件包不存在")
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": True, "detail": f"插件包已删除: {pkg_id}"}
