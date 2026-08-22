"""routers/performance.py — 绩效考核"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, desc, func, Column, Integer, String, Text, DateTime, Float, JSON
from sqlalchemy.orm import Session

from database import get_db, Base
from routers.auth import require_auth

router = APIRouter(prefix="/api/performance", tags=["performance"])
R = dict

import datetime

class PerfModel(Base):
    __tablename__ = "performance_reviews"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_name = Column(String(255), nullable=False, index=True)
    department = Column(String(255))
    period = Column(String(20), nullable=False)  # 2026Q1 / 2026-H1
    self_score = Column(Float)
    self_review = Column(Text)
    manager_score = Column(Float)
    manager_review = Column(Text)
    overall_score = Column(Float)
    status = Column(String(20), default="self_review")  # self_review / manager_review / finalized
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)


@router.get("")
def list_reviews(period: str = None, status: str = None, db: Session = Depends(get_db), _=Depends(require_auth)):
    if "performance_reviews" not in Base.metadata.tables:
        return R(total=0, items=[])
    q = select(PerfModel)
    if period:
        q = q.where(PerfModel.period == period)
    if status:
        q = q.where(PerfModel.status == status)
    q = q.order_by(desc(PerfModel.updated_at))
    items = db.execute(q).scalars().all()
    total = len(items)
    data = [{
        "id": r.id, "employee_name": r.employee_name, "department": r.department,
        "period": r.period, "self_score": r.self_score, "self_review": r.self_review or "",
        "manager_score": r.manager_score, "manager_review": r.manager_review or "",
        "overall_score": r.overall_score, "status": r.status,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in items]
    return R(total=total, items=data)


@router.post("")
def create_review(body: dict, db: Session = Depends(get_db), _=Depends(require_auth)):
    r = PerfModel(
        employee_name=body["employee_name"],
        department=body.get("department", ""),
        period=body["period"],
        self_score=body.get("self_score"),
        self_review=body.get("self_review", ""),
        manager_score=body.get("manager_score"),
        manager_review=body.get("manager_review", ""),
        overall_score=body.get("overall_score"),
        status=body.get("status", "self_review"),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return R(id=r.id)


@router.put("/{review_id}")
def update_review(review_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_auth)):
    r = db.execute(select(PerfModel).where(PerfModel.id == review_id)).scalar_one_or_none()
    if not r:
        return R(message="not found")
    for k, v in body.items():
        if hasattr(r, k) and v is not None:
            setattr(r, k, v)
    r.updated_at = datetime.datetime.now()
    db.commit()
    return R(message="ok")


@router.delete("/{review_id}", status_code=204)
def delete_review(review_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    r = db.execute(select(PerfModel).where(PerfModel.id == review_id)).scalar_one_or_none()
    if r:
        db.delete(r)
        db.commit()
