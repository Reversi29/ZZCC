"""plugins/registry.py — 插件注册表（持久化到 DB）

ZZCC services 版本：async SQLAlchemy + asyncpg + PostgreSQL。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger("plugins.registry")

# ── 数据库方言标记：用于 SQL 生成 ──
# ZZCC services 使用 PostgreSQL


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
    """插件注册表 — 内存 + DB 双层持久化。"""

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
            return True
        return False

    def update_config(self, plugin_id: str, config: Dict[str, Any]) -> bool:
        if plugin_id in self._plugins:
            self._plugins[plugin_id].config = config
            return True
        return False

    def remove(self, plugin_id: str) -> None:
        self._plugins.pop(plugin_id, None)

    async def save_to_db(self) -> bool:
        """批量持久化内存中的插件到 DB（upsert）。"""
        from services.db import managed_session
        try:
            async with managed_session() as db:
                for pid, meta in self._plugins.items():
                    stmt = text("""
                        INSERT INTO plugin_registry (
                            id, name, version, author, description,
                            manifest, status, config,
                            installed_at, updated_at
                        ) VALUES (
                            :id, :name, :version, :author, :desc,
                            :manifest, :status, :config,
                            NOW(), NOW()
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            version = EXCLUDED.version,
                            author = EXCLUDED.author,
                            description = EXCLUDED.description,
                            manifest = EXCLUDED.manifest,
                            status = EXCLUDED.status,
                            config = EXCLUDED.config,
                            updated_at = NOW()
                    """)
                    await db.execute(stmt, {
                        "id": pid, "name": meta.name, "version": meta.version,
                        "author": meta.author, "desc": meta.description,
                        "manifest": json.dumps(meta.manifest, ensure_ascii=False),
                        "status": meta.status.value,
                        "config": json.dumps(meta.config, ensure_ascii=False),
                    })
                await db.commit()
            return True
        except Exception as e:
            logger.error("registry save_to_db 失败: %s", e)
            return False

    async def load_from_db(self) -> List[Dict[str, Any]]:
        """从 DB 加载已注册插件记录。"""
        from services.db import managed_session
        try:
            async with managed_session() as db:
                result = await db.execute(text("SELECT * FROM plugin_registry"))
                cols = result.keys()
                rows = result.fetchall()
                return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.error("registry load_from_db 失败: %s", e)
            return []

    async def delete_from_db(self, plugin_id: str) -> bool:
        """从 DB 删除插件记录。"""
        from services.db import managed_session
        try:
            async with managed_session() as db:
                await db.execute(
                    text("DELETE FROM plugin_registry WHERE id = :pid"),
                    {"pid": plugin_id},
                )
                await db.commit()
            return True
        except Exception as e:
            logger.error("registry delete_from_db 失败: %s", e)
            return False

    async def get_config_from_db(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """从 DB 读取指定插件的配置（用于加载时恢复）。"""
        from services.db import managed_session
        try:
            async with managed_session() as db:
                row = (await db.execute(
                    text("SELECT config FROM plugin_registry WHERE id = :pid"),
                    {"pid": plugin_id},
                )).fetchone()
                if row and row[0]:
                    return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception as e:
            logger.error("registry get_config_from_db 失败: %s", e)
        return None


# ── 全局单例 ──
registry = PluginRegistry()
