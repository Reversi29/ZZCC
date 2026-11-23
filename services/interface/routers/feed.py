"""
广场内容（Feed）API 路由.

内容模型对齐前端 FeedContent（8 类：recommend/video/audio/article/app/project/live）。
视频/直播走 SRS 流媒体：
  - 点播视频：RTMP 推流 + dvr 录制 MP4，Web 拉 HLS
  - 直播：RTMP 推流，Web 拉 HLS（4s 切片，秒级延迟）

端点：
  GET    /feed/{type}              按类型分页拉取
  GET    /feed/{type}/{content_id} 单条详情
  POST   /feed/content             创建内容
  POST   /feed/upload              上传媒体（封面/音频/小视频）
  POST   /feed/{content_id}/interact  互动（like/comment/share）
  GET    /feed/media/{filename}     静态媒体
  POST   /feed/live                开播（分配流名 + 推流地址）
  POST   /feed/live/{live_id}/end  下播
  GET    /feed/live/{live_id}/status 直播状态
  GET    /feed/live/pull/{live_id} 拉流地址
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Path, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.feed_models import FeedContent, FeedInteraction, FeedLive, FeedMedia, utcnow
from routers.auth import get_current_user_dep
from services.db import get_session
from services import feed as feed_svc

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/feed", tags=["feed"])


# ============================================================
# Schemas
# ============================================================
class FeedContentIn(BaseModel):
    """创建内容。"""
    type: str = Field(..., description="内容类型")
    content_id: Optional[str] = Field(default=None, max_length=64, description="不传则自动生成")
    title: str = Field(..., max_length=512)
    description: Optional[str] = None
    author: str = Field(default="", max_length=128)
    author_avatar: Optional[str] = None
    cover_image: Optional[str] = None
    tags: List[str] = Field(default=[])
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    audio_waveform: Optional[str] = None
    duration_text: Optional[str] = None
    app_category: Optional[str] = None
    app_downloads: Optional[int] = None
    app_icon: Optional[str] = None
    app_version: Optional[str] = None
    package_name: Optional[str] = None
    sort_weight: int = 0


class FeedInteractIn(BaseModel):
    kind: str = Field(..., description="like/comment/share")
    user_id: str = Field(default="anonymous", max_length=64)
    payload: Optional[str] = Field(default=None, max_length=2000, description="评论正文等")


class FeedInstallIn(BaseModel):
    user_id: str = Field(default="anonymous", max_length=64)
    package_name: Optional[str] = Field(default=None, max_length=256)


def _to_dict(c: FeedContent) -> dict[str, Any]:
    """ORM → 前端 FeedContent JSON。"""
    try:
        tags = json.loads(c.tags) if c.tags else []
        if not isinstance(tags, list):
            tags = []
    except Exception:
        tags = []
    return {
        "id": c.content_id,
        "type": c.type,
        "title": c.title,
        "description": c.description or "",
        "author": c.author,
        "author_avatar": c.author_avatar or "",
        "cover_image": c.cover_image or "",
        "tags": tags,
        "likes": c.likes,
        "comments": c.comments,
        "shares": c.shares,
        "views": c.views,
        "video_url": c.video_url,
        "audio_url": c.audio_url,
        "audio_waveform": c.audio_waveform,
        "duration_text": c.duration_text,
        "app_category": c.app_category,
        "app_downloads": c.app_downloads,
        "app_icon": c.app_icon,
        "app_version": c.app_version,
        "package_name": c.package_name,
        "is_live": c.is_live,
        "viewer_count": c.viewer_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ============================================================
# 内容查询
# ============================================================
@router.get("/{content_type}")  # 见下方 _TYPE_RE 约束
async def list_feed(
    content_type: str = Path(..., pattern=r"recommend|video|audio|article|app|project|live"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str | None = Query(
        None, description="newest|hot；缺省时 recommend 走 hot、其余走 newest"
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """按类型分页拉取内容。"""
    try:
        ctype = feed_svc.validate_type(content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    stmt = select(FeedContent).where(FeedContent.type == ctype)
    # 推荐流默认按热度排（短视频平台语义：新内容靠时间衰减、热内容靠互动加权）；
    # 其余类型默认按时间倒序，避免运营/新建内容被旧热内容压住。
    effective_sort = sort or ("hot" if ctype == "recommend" else "newest")
    if effective_sort == "hot":
        # 热度分 = (互动加权分) / ln(2 + 发布小时数)
        # 对数时间衰减：新内容衰减慢、旧内容随时间快速降权；
        # 互动权重 comments > shares > likes > views（评论/分享意图强于浏览）。
        # 注意：PostgreSQL 无 log2()，用 ln() 等价（单调，排序结果一致）。
        age_hours = (
            (func.extract("epoch", func.now())
             - func.extract("epoch", FeedContent.created_at))
            / 3600.0
        )
        decay = func.ln(func.greatest(2.0, 2.0 + age_hours))
        hot_expr = ((
            FeedContent.likes * 1.0
            + FeedContent.comments * 3.0
            + FeedContent.shares * 5.0
            + FeedContent.views * 0.5
        ) / decay).label("hot_score")
        # 人工权重 sort_weight 优先（运营置顶），其次热度分；
        # created_at 作第三键：互动全 0 时 hot 分并列，需稳定排序（无此键 PG 对
        # 并列值顺序不确定，列表会随机抖动）。
        stmt = stmt.order_by(
            FeedContent.sort_weight.desc(), hot_expr.desc(),
            FeedContent.created_at.desc()
        )
    else:
        stmt = stmt.order_by(FeedContent.sort_weight.desc(), FeedContent.created_at.desc())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()

    total = (
        await session.execute(
            select(func.count()).select_from(FeedContent).where(FeedContent.type == ctype)
        )
    ).scalar_one()

    return {
        "ok": True,
        "type": ctype,
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "items": [_to_dict(c) for c in rows],
    }


@router.post("/content")
async def create_feed_content(
    body: FeedContentIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """创建内容（管理端/内容生产）。content_id 不传则自动生成。"""
    try:
        ctype = feed_svc.validate_type(body.type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    prefix = ctype[:3]
    if body.content_id:
        content_id = body.content_id
    else:
        n = (
            await session.execute(
                select(func.count()).select_from(FeedContent).where(FeedContent.type == ctype)
            )
        ).scalar_one()
        content_id = f"{prefix}_{n}"
        while (
            await session.execute(
                select(FeedContent).where(FeedContent.content_id == content_id)
            )
        ).scalar_one_or_none() is not None:
            n += 1
            content_id = f"{prefix}_{n}"
    obj = FeedContent(
        content_id=content_id,
        type=ctype,
        title=body.title,
        description=body.description,
        author=body.author,
        author_avatar=body.author_avatar,
        cover_image=body.cover_image,
        tags=json.dumps(body.tags, ensure_ascii=False),
        video_url=body.video_url,
        audio_url=body.audio_url,
        audio_waveform=body.audio_waveform,
        duration_text=body.duration_text,
        app_category=body.app_category,
        app_downloads=body.app_downloads,
        app_icon=body.app_icon,
        app_version=body.app_version,
        package_name=body.package_name,
        is_live=ctype == "live",
        sort_weight=body.sort_weight,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return {"ok": True, "item": _to_dict(obj)}


# ============================================================
# 应用安装
# ============================================================
@router.post("/view/{content_id}/report")
async def report_view(
    content_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """观看数上报（播放埋点）。

    每次播放/起播上报一次，views +1。前端在视频/音频实际开始
    播放时调用（不是加载列表时），使热度公式的 views×0.5 项生效。

    注：本路由必须以字面量 'view' 开头注册在通配 /{content_type}
    之前，否则 'view' 会被当作 content_type 匹配失败。
    """
    row = (
        await session.execute(
            select(FeedContent).where(FeedContent.content_id == content_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="content not found")

    row.views = (row.views or 0) + 1
    await session.commit()
    return {"ok": True, "content_id": content_id, "views": row.views}


@router.post("/{content_id}/install")
async def install_app(
    content_id: str,
    body: FeedInstallIn = Body(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """应用安装计数。幂等：同用户同应用只 +1。"""
    obj = (
        await session.execute(
            select(FeedContent).where(FeedContent.content_id == content_id)
        )
    ).scalars().first()
    if obj is None:
        raise HTTPException(status_code=404, detail="内容不存在")
    if obj.type != "app":
        raise HTTPException(status_code=400, detail="仅应用可安装")

    uid = body.user_id or "anonymous"
    added = False
    try:
        session.add(FeedInteraction(
            content_id=content_id, user_id=uid, kind="install", payload=body.package_name,
        ))
        await session.flush()
        obj.app_downloads = (obj.app_downloads or 0) + 1
        await session.commit()
        added = True
    except IntegrityError:
        await session.rollback()
        fresh = (
            await session.execute(
                select(FeedContent).where(FeedContent.content_id == content_id)
            )
        ).scalars().first()
        return {"ok": True, "added": False,
                "count": getattr(fresh, "app_downloads", 0) if fresh is not None else 0}

    return {"ok": True, "added": added, "count": obj.app_downloads}


# ============================================================
# 互动
# ============================================================
@router.post("/{content_id}/interact")
async def interact(
    content_id: str,
    body: FeedInteractIn = Body(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """点赞/评论/分享。like 幂等，comment/share 防刷（时间窗口）。"""
    kind = (body.kind or "").strip().lower()
    if kind not in {"like", "comment", "share"}:
        raise HTTPException(status_code=400, detail="kind 需为 like/comment/share")

    if kind == "comment" and not (body.payload or "").strip():
        raise HTTPException(status_code=400, detail="评论内容不能为空")

    col = {
        "like": FeedContent.likes,
        "comment": FeedContent.comments,
        "share": FeedContent.shares,
    }[kind]

    obj = (
        await session.execute(
            select(FeedContent).where(FeedContent.content_id == content_id)
        )
    ).scalars().first()
    if obj is None:
        raise HTTPException(status_code=404, detail="内容不存在")

    uid = body.user_id or "anonymous"
    added = False
    try:
        # like 幂等：同用户同内容只一次（UniqueConstraint 拦截）
        # comment/share 防刷：同一用户 30s 内同内容同类型只一次
        if kind != "like":
            from datetime import timedelta
            recent = (
                await session.execute(
                    select(FeedInteraction).where(
                        FeedInteraction.content_id == content_id,
                        FeedInteraction.user_id == uid,
                        FeedInteraction.kind == kind,
                        FeedInteraction.created_at >= utcnow() - timedelta(seconds=30),
                    )
                )
            ).scalars().first()
            if recent is not None:
                return {"ok": True, "added": False, "count": getattr(obj, col.key),
                        "reason": "rate_limited"}

        session.add(FeedInteraction(
            content_id=content_id, user_id=uid, kind=kind, payload=body.payload,
        ))
        await session.flush()
        setattr(obj, col.key, getattr(obj, col.key) + 1)
        await session.commit()
        added = True
    except IntegrityError:
        # like 已存在：幂等返回当前计数（不回滚后复用已坏 session，重新查询）
        await session.rollback()
        fresh = (
            await session.execute(
                select(FeedContent).where(FeedContent.content_id == content_id)
            )
        ).scalars().first()
        count = getattr(fresh, col.key, 0) if fresh is not None else 0
        return {"ok": True, "added": False, "count": count}

    return {"ok": True, "added": added, "count": getattr(obj, col.key)}


# ============================================================
# 媒体上传
# ============================================================
@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    content_id: Optional[str] = Query(None),
    user=Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """上传媒体（封面/音频/小视频）。返回可访问 URL。"""
    data = await file.read()
    if len(data) > feed_svc._MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件过大")

    ext = feed_svc._safe_ext(file.filename or "")
    store = feed_svc.media_store()
    media_id = feed_svc.new_media_id()
    path, url = store.save(media_id, ext, data)

    mime = feed_svc._MEDIA_MIME.get(ext, file.content_type or "application/octet-stream")
    media = FeedMedia(
        media_id=media_id,
        content_id=content_id,
        kind="cover" if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else (
            "audio" if ext in {".mp3", ".m4a", ".aac"} else "video"
        ),
        storage="local",
        path=str(path),
        url=url,
        bytes=len(data),
        mime=mime,
    )
    session.add(media)
    await session.commit()

    return {"ok": True, "media_id": media_id, "url": url, "bytes": len(data), "mime": mime}


@router.get("/media/{filename}")
async def serve_media(filename: str) -> FileResponse:
    """静态媒体文件（本地存储）。"""
    path = feed_svc.media_store().resolve(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    mime = feed_svc._MEDIA_MIME.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=mime)


# ============================================================
# 直播
# ============================================================
@router.post("/live")
async def start_live(
    content_id: str,
    author: str = Query(default="", max_length=128),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """开播：分配流名 + 返回 RTMP 推流地址与 HLS 播放地址。

    主播端用返回的 push_url 推流；Web 端用 play_url 播放。
    """
    obj = (
        await session.execute(
            select(FeedContent).where(FeedContent.content_id == content_id)
        )
    ).scalars().first()
    if obj is None:
        raise HTTPException(status_code=404, detail="内容不存在")
    if obj.type != "live":
        raise HTTPException(status_code=400, detail="内容类型不是 live")

    client = feed_svc.srs_client()
    live = FeedLive(
        live_id=content_id,
        content_id=content_id,
        author=author or obj.author,
        stream_key=client.build_rtmp_push_url(content_id),
        hls_url=client.build_hls_url(content_id),
        is_live=True,
    )
    obj.is_live = True
    session.add(live)
    await session.commit()

    return {
        "ok": True,
        "live_id": content_id,
        "push_url": live.stream_key,
        "play_url": live.hls_url,
        "srs_healthy": await client.healthy(),
    }


@router.post("/live/{live_id}/end")
async def end_live(live_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    live = (
        await session.execute(select(FeedLive).where(FeedLive.live_id == live_id))
    ).scalars().first()
    if live is None:
        raise HTTPException(status_code=404, detail="直播不存在")
    from models.user_models import utcnow
    live.is_live = False
    live.ended_at = utcnow()
    obj = (
        await session.execute(
            select(FeedContent).where(FeedContent.content_id == live.content_id)
        )
    ).scalars().first()
    if obj is not None:
        obj.is_live = False
    await session.commit()
    return {"ok": True, "live_id": live_id}


@router.get("/live/{live_id}/status")
async def live_status(
    live_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """直播状态：是否有人正在推流 + 观看人数。"""
    feed_svc.validate_stream_id(live_id)
    client = feed_svc.srs_client()
    info = await client.get_stream_info("live", live_id)

    obj = (
        await session.execute(
            select(FeedContent).where(FeedContent.content_id == live_id)
        )
    ).scalars().first()
    if obj is not None and info.get("active"):
        obj.viewer_count = info.get("viewers", 0)
        await session.commit()

    return {
        "ok": True,
        "live_id": live_id,
        "active": bool(info.get("active")),
        "viewers": info.get("viewers", 0),
        "srs_healthy": await client.healthy(),
    }


@router.get("/live/pull/{live_id}")
async def live_pull(live_id: str) -> dict[str, Any]:
    """拉流地址。"""
    feed_svc.validate_stream_id(live_id)
    return {
        "ok": True,
        "live_id": live_id,
        "play_url": feed_svc.srs_client().build_hls_url(live_id),
    }


@router.get("/system/status")
async def feed_status() -> dict[str, Any]:
    """服务状态。挂到 /feed/system/status 避免与 /feed/{content_type} 路径冲突。"""
    client = feed_svc.srs_client()
    return {
        "ok": True,
        "srs_healthy": await client.healthy(),
        "srs_api": client.api,
        "media_root": str(feed_svc.media_store().root),
        "types": sorted(feed_svc.FEED_TYPES),
    }


# ============================================================
# 通配路由（放末尾：避免抢占 /system/status、/media/、/live/ 等具体路由）
# ============================================================
@router.get("/{content_type}/{content_id}")
async def get_feed_item(
    content_id: str = Path(..., pattern=r"[A-Za-z0-9_\-]{1,64}"),
    content_type: str = Path(..., pattern=r"recommend|video|audio|article|app|project|live"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(FeedContent)
            .where(FeedContent.content_id == content_id)
            .where(FeedContent.type == content_type)
        )
    ).scalars().first()
    if rows is None:
        raise HTTPException(status_code=404, detail="内容不存在")
    return {"ok": True, "item": _to_dict(rows)}