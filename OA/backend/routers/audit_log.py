"""routers/audit_log.py — 操作审计日志"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc, Column, Integer, String, DateTime, Text, Index
from sqlalchemy.orm import Session

from database import get_db, Base
from routers.auth import require_admin

router = APIRouter(prefix="/api/audit-log", tags=["audit-log"])
R = dict


class AuditEntry(Base):
    __tablename__ = "audit_entries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    module = Column(String(50), nullable=False)
    detail = Column(Text)
    ip = Column(String(45))
    created_at = Column(DateTime, default=datetime.now, index=True)


class AuditFilter(BaseModel):
    username: str = ""
    action: str = ""
    module: str = ""
    start: str = ""
    end: str = ""
    page: int = 1
    page_size: int = 50


@router.get("")
def list_entries(db: Session = Depends(get_db), _=Depends(require_admin)):
    """审计日志列表"""
    q = select(AuditEntry).order_by(desc(AuditEntry.created_at))
    total = db.execute(select(func.count()).select_from(AuditEntry)).scalar() or 0
    results = db.execute(q.limit(500)).scalars().all()
    items = [{
        "id": e.id,
        "username": e.username,
        "action": e.action,
        "module": e.module,
        "detail": e.detail or "",
        "ip": e.ip or "",
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in results]
    return R(total=total, items=items)


@router.post("/record")
def record(db: Session = Depends(get_db), body: dict = {}):
    """记录一条审计日志（供 middleware 调用）"""
    e = AuditEntry(
        username=body.get("username", "unknown"),
        action=body.get("action", "other"),
        module=body.get("module", "system"),
        detail=body.get("detail", ""),
        ip=body.get("ip", ""),
    )
    db.add(e)
    db.commit()
    return R(message="ok")


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    e = db.execute(select(AuditEntry).where(AuditEntry.id == entry_id)).scalar_one_or_none()
    if not e:
        raise HTTPException(404)
    db.delete(e)
    db.commit()
