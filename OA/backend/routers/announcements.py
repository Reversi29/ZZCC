"""
routers/announcements.py — 企业公告管理
路径：/api/resource/Announcement
权限：admin 可发布/置顶/删除，普通用户只读
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db, Announcement
from routers._db import seq_for
from routers.auth import require_auth, require_admin

router = APIRouter(prefix="/api/resource", tags=["Announcements"])

R = dict  # simplified response alias

@router.get("/Announcement")
def list_announcements(
    status: Optional[str] = Query(None, description="filter by status: draft/published"),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    q = db.query(Announcement).filter(Announcement.status == "published")
    q = q.order_by(
        Announcement.is_pinned.desc(),
        Announcement.creation.desc(),
    )
    if status:
        q = q.filter(Announcement.status == status)
    total = q.count()
    rows = q.limit(limit).offset(0).all()
    return R(data={"items": [md(r) for r in rows], "length": total})

def md(a: Announcement) -> dict:
    """Announcement → dict"""
    return {
        "id": a.id,
        "title": a.title,
        "body": a.body,
        "published_by": a.published_by,
        "status": a.status,
        "is_pinned": a.is_pinned,
        "expires_at": (a.expires_at.isoformat() if isinstance(a.expires_at, datetime) else a.expires_at) if a.expires_at else None,
        "view_count": a.view_count,
        "created": (a.creation.isoformat() if isinstance(a.creation, datetime) else a.creation) if a.creation else None,
        "modified": (a.modified.isoformat() if isinstance(a.modified, datetime) else a.modified) if a.modified else None,
    }

@router.post("/Announcement")
def create_announcement(
    data: dict,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    a = Announcement(
        title=data["title"],
        body=data.get("body", ""),
        published_by=current_user.username,
        status=data.get("status", "draft"),
        is_pinned=data.get("is_pinned", False),
        expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
    )
    db.add(a); db.commit(); db.refresh(a)
    return R(data={"id": a.id}, message="Announcement created")

@router.get("/Announcement/{aid}")
def get_announcement(aid: int, db: Session = Depends(get_db), current_user=Depends(require_auth)):
    a = db.query(Announcement).filter(Announcement.id == aid).first()
    if not a:
        raise HTTPException(404, "Announcement not found")
    a.view_count = (a.view_count or 0) + 1
    db.commit()
    return R(data=md(a))

@router.put("/Announcement/{aid}")
def update_announcement(
    aid: int, data: dict,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    a = db.query(Announcement).filter(Announcement.id == aid).first()
    if not a:
        raise HTTPException(404, "Announcement not found")
    if "title" in data: a.title = data["title"]
    if "body" in data: a.body = data["body"]
    if "status" in data: a.status = data["status"]
    if "is_pinned" in data: a.is_pinned = data["is_pinned"]
    if "expires_at" in data and data["expires_at"]:
        a.expires_at = datetime.fromisoformat(data["expires_at"])
    elif "expires_at" in data:
        a.expires_at = None
    db.commit(); db.refresh(a)
    return R(data={"id": a.id}, message="Announcement updated")

@router.delete("/Announcement/{aid}")
def delete_announcement(
    aid: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    a = db.query(Announcement).filter(Announcement.id == aid).first()
    if not a:
        raise HTTPException(404, "Announcement not found")
    db.delete(a); db.commit()
    return R(message="Announcement deleted", status_code=204)