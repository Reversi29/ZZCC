"""plugins/registry.py — 插件注册表（持久化到 DB）"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("plugins.registry")

class PluginStatus(str, Enum):
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"

class PluginManifestError(Exception):
    """插件 manifest 校验失败"""
    pass

@dataclass
class PluginMetadata:
    id: str
    name: str
    version: str
    author: str
    description: str
    manifest: Dict[str, Any]
    status: PluginStatus
    config: Dict[str, Any] = field(default_factory=dict)
    frontend_module: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id, "name": self.name, "version": self.version,
            "author": self.author, "description": self.description,
            "status": self.status.value, "config": self.config,
        }
        if self.frontend_module:
            d["frontend_module"] = self.frontend_module
        return d

def validate_manifest(m: Dict[str, Any]) -> None:
    required = ["id", "name", "version"]
    for k in required:
        if k not in m:
            raise PluginManifestError(f"manifest 缺少必填字段: {k}")
    if not isinstance(m["id"], str) or not m["id"]:
        raise PluginManifestError("manifest.id 必须为非空字符串")

    # 校验 manifest 结构
    if "events" in m and not isinstance(m["events"], dict):
        raise PluginManifestError("manifest.events 必须为 dict")
    if "frontend" in m:
        if not isinstance(m["frontend"], dict):
            raise PluginManifestError("manifest.frontend 必须为 dict")
        if "module" in m["frontend"] and not isinstance(m["frontend"]["module"], dict):
            raise PluginManifestError("manifest.frontend.module 必须为 dict")

    perms = m.get("permissions", [])
    if not isinstance(perms, list):
        raise PluginManifestError("manifest.permissions 必须为列表")
    valid_perms = {"database", "http", "event:subscribe", "event:publish"}
    for p in perms:
        if p not in valid_perms:
            raise PluginManifestError(f"无效权限: {p}")

class PluginRegistry:
    def __init__(self):
        self._plugins: Dict[str, PluginMetadata] = {}

    def register(self, metadata: PluginMetadata) -> None:
        self._plugins[metadata.id] = metadata
        logger.info("插件注册: %s (%s)", metadata.name, metadata.version)

    def get(self, plugin_id: str) -> Optional[PluginMetadata]:
        return self._plugins.get(plugin_id)

    def list_all(self) -> List[PluginMetadata]:
        return list(self._plugins.values())

    def list_enabled(self) -> List[PluginMetadata]:
        return [p for p in self._plugins.values() if p.status == PluginStatus.ENABLED]

    def update_status(self, plugin_id: str, status: PluginStatus) -> bool:
        if plugin_id in self._plugins:
            self._plugins[plugin_id].status = status
            self.save_to_db()
            return True
        return False

    def update_config(self, plugin_id: str, config: Dict[str, Any]) -> bool:
        if plugin_id in self._plugins:
            self._plugins[plugin_id].config = config
            self.save_to_db()
            return True
        return False

    def remove(self, plugin_id: str) -> None:
        self._plugins.pop(plugin_id, None)

    def save_to_db(self):
        """持久化到 plugin_registry 表。"""
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            for pid, meta in self._plugins.items():
                stmt = text("""
                    INSERT INTO plugin_registry
                        (id, name, version, author, description, manifest, status, config, installed_at, updated_at)
                    VALUES
                        (:id, :name, :version, :author, :desc, :manifest, :status, :config, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name), version = VALUES(version),
                        manifest = VALUES(manifest), status = VALUES(status),
                        config = VALUES(config), updated_at = NOW()
                """)
                db.execute(stmt, {
                    "id": pid, "name": meta.name, "version": meta.version,
                    "author": meta.author, "desc": meta.description,
                    "manifest": json.dumps(meta.manifest, ensure_ascii=False),
                    "status": meta.status.value,
                    "config": json.dumps(meta.config, ensure_ascii=False),
                })
            db.commit()
        except Exception as e:
            logger.error("registry save_to_db 失败: %s", e)
            db.rollback()
        finally:
            db.close()

    def load_from_db(self) -> List[Dict[str, Any]]:
        """从 DB 加载已注册插件记录。"""
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            result = db.execute(text("SELECT * FROM plugin_registry"))
            cols = result.keys()
            rows = result.fetchall()
            return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.error("registry load_from_db 失败: %s", e)
            return []
        finally:
            db.close()


# ── 全局单例（供 sdk.py from .registry import registry 引用） ──
registry = PluginRegistry()