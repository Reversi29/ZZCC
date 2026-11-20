"""
广场内容（Feed）数据库模型 — SQLAlchemy ORM.

Tables: feed_contents, feed_media, feed_lives

设计对齐前端 FeedContent 模型（lib/data/models/feed_content_model.dart）。
互动计数采用「物化计数 + 幂等键」：likes/comments/shares/views 直接存列，
interact 端点用唯一约束去重，避免每次实时聚合。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from .user_models import Base, utcnow


# ============================================================
# 内容主体
# ============================================================
class FeedContent(Base):
    """广场内容。8 类内容统一存储，type 区分。"""
    __tablename__ = "feed_contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="业务 ID（如 rec_0/vid_2/live_1）",
    )
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="recommend/video/audio/article/app/project/live",
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    author_avatar: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cover_image: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="JSON 数组字符串",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True,
    )

    # 互动计数（物化）
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(BigInteger, default=0)
    shares: Mapped[int] = mapped_column(BigInteger, default=0)
    views: Mapped[int] = mapped_column(BigInteger, default=0)

    # 视频/音频播放地址
    video_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    audio_waveform: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_text: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # 应用特有
    app_category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    app_downloads: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    app_icon: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    app_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    package_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # 直播特有
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    viewer_count: Mapped[int] = mapped_column(Integer, default=0)

    # 排序权重（推荐用）
    sort_weight: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FeedContent {self.content_id} {self.type}>"


# ============================================================
# 互动去重（幂等键）
# ============================================================
class FeedInteraction(Base):
    """用户互动记录，用于点赞/评论/分享幂等。

    (content_id, user_id, kind) 唯一 → 同一用户同一内容同一类型只记一次。
    """
    __tablename__ = "feed_interactions"
    __table_args__ = (
        UniqueConstraint("content_id", "user_id", "kind", name="uq_interaction"),
        Index("ix_feed_inter_content", "content_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # like/comment/share
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ============================================================
# 媒体文件
# ============================================================
class FeedMedia(Base):
    """上传的媒体文件元数据。"""
    __tablename__ = "feed_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
    )
    content_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
    )
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="cover/video/audio",
    )
    storage: Mapped[str] = mapped_column(
        String(32), default="local", comment="local/srs",
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    mime: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ============================================================
# 直播会话
# ============================================================
class FeedLive(Base):
    """直播会话状态。"""
    __tablename__ = "feed_lives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    live_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
    )
    content_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    stream_key: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="SRS 推流地址",
    )
    hls_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="Web 播放地址",
    )
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    viewer_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)