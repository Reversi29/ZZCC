"""
广场内容服务层 — SRS 推流交互 + 本地媒体存储 + 内容读写.

SRS 5.x 实测约定（见 docker logs srs-server 的 listen 行）：
- HTTP API 监听 1985（http_api 的 listen 配置被忽略，硬编码 1985）
- HTTP Server（HLS）监听容器内 8080，映射到宿主机 8090

直播推流链路：
    主播端 RTMP 推 rtmp://1935/live/{stream_id}
      → SRS 收流 → dvr 录制 MP4（segment）+ HLS 切片
      → Web 端拉 http://8090/hls/live/{stream_id}/index.m3u8
    后端用 SRS API /api/v1/hooks/pub 回调检测推流开始/结束。
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx

from config import get_settings
from models.user_models import Base  # noqa: F401  (declarative Base，供 create_all)
from models.feed_models import FeedContent, FeedInteraction, FeedLive, FeedMedia  # noqa: F401

_log = logging.getLogger(__name__)


async def ensure_tables() -> None:
    """建表（幂等）。只建不存在的表，不动既有表。

    放在 lifespan 里调用；ORM 模型由 Base.metadata.create_all 统一创建。
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from config import get_settings as _gs

    dsn = _gs().database.dsn.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(dsn, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()

# 允许的媒体扩展名 → MIME
_MEDIA_MIME = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".ts": "video/mp2t",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
_MAX_EXT = set(_MEDIA_MIME)
_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB


def _safe_ext(name: str) -> str:
    """取安全扩展名，默认 .bin（不可播放）."""
    ext = Path(name or "").suffix.lower()
    return ext if ext in _MAX_EXT else ".bin"


def new_media_id() -> str:
    return uuid.uuid4().hex[:16]


# ============================================================
# 本地媒体存储
# ============================================================
class MediaStore:
    """本地磁盘媒体存储。目录来自 ./data 挂载点。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.root = Path(settings.streaming.upload_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, media_id: str, ext: str, data: bytes) -> tuple[Path, str]:
        """落盘，返回 (绝对路径, 可访问 URL)."""
        path = self.root / f"{media_id}{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path, f"/feed-media/{media_id}{ext}"

    def exists(self, media_id: str, ext: str) -> bool:
        return (self.root / f"{media_id}{ext}").exists()

    def resolve(self, filename: str) -> Optional[Path]:
        """安全解析请求文件名（防目录穿越）。"""
        target = (self.root / filename).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            return None
        return target if target.exists() else None


_store: Optional[MediaStore] = None


def media_store() -> MediaStore:
    global _store
    if _store is None:
        _store = MediaStore()
    return _store


# ============================================================
# SRS 客户端
# ============================================================
class SrsClient:
    """SRS HTTP API 客户端。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.api = settings.streaming.api_url.rstrip("/")
        self.hls_base = settings.streaming.hls_base.rstrip("/")
        self.rtmp_base = settings.streaming.rtmp_base.rstrip("/")

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self.api}/api/v1/versions")
                return r.status_code == 200
        except Exception:
            return False

    async def get_stream_info(
        self, app: str, stream: str,
    ) -> dict[str, Any]:
        """查询流状态。返回 {active, viewers, ...}."""
        url = f"{self.api}/api/v1/streams?app={quote(app)}&stream={quote(stream)}"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    return {"active": False}
                data = r.json()
                streams = data.get("data") or []
                # 匹配 action=publish 的流
                for item in streams:
                    if item.get("name") == "publish":
                        return {
                            "active": True,
                            "viewers": int(item.get("viewers") or 0),
                            "bytesin": int(item.get("bytesin") or 0),
                            "duration": item.get("duration"),
                        }
                return {"active": bool(streams), "viewers": 0}
        except Exception as e:  # pragma: no cover
            _log.warning("srs get_stream_info failed: %s", e)
            return {"active": False}

    def build_hls_url(self, stream_id: str) -> str:
        return f"{self.hls_base}/live/{quote(stream_id)}/index.m3u8"

    def build_rtmp_push_url(self, stream_id: str) -> str:
        return f"{self.rtmp_base}/{quote(stream_id)}"


_srs: Optional[SrsClient] = None


def srs_client() -> SrsClient:
    global _srs
    if _srs is None:
        _srs = SrsClient()
    return _srs


# ============================================================
# 内容类型校验
# ============================================================
FEED_TYPES = {"recommend", "video", "audio", "article", "app", "project", "live"}


def validate_type(t: str) -> str:
    t = (t or "").strip().lower()
    if t not in FEED_TYPES:
        raise ValueError(f"非法内容类型: {t}")
    return t


# SRS 流名（app/stream）需为安全字符
_STREAM_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def validate_stream_id(stream_id: str) -> str:
    s = (stream_id or "").strip()
    if not _STREAM_NAME_RE.match(s):
        raise ValueError("流名需为 1-64 位字母/数字/_/-")
    return s