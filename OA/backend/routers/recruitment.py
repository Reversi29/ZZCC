"""routers/recruitment.py — 招聘管理"""
import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, desc, func, Column, Integer, String, Text, DateTime, Float, JSON
from sqlalchemy.orm import Session

from database import get_db, Base
from routers.auth import require_auth

router = APIRouter(prefix="/api/recruitment", tags=["recruitment"])
R = dict


class RecruitmentModel(Base):
    __tablename__ = "recruitments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    position = Column(String(255), nullable=False)
    department = Column(String(255))
    headcount = Column(Integer, default=1)
    description = Column(Text)
    status = Column(String(30), default="open")  # open / paused / closed / cancelled
    priority = Column(String(20), default="normal")
    salary_range = Column(String(100))
    contact = Column(String(255))
    resume_count = Column(Integer, default=0)
    interview_count = Column(Integer, default=0)
    offer_count = Column(Integer, default=0)
    hire_count = Column(Integer, default=0)
    tags = Column(String(500))
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)


@router.get("")
def list_all(status: str = None, department: str = None, db: Session = Depends(get_db), _=Depends(require_auth)):
    q = select(RecruitmentModel)
    if status:
        q = q.where(RecruitmentModel.status == status)
    if department:
        q = q.where(RecruitmentModel.department == department)
    q = q.order_by(desc(RecruitmentModel.updated_at))
    items = db.execute(q).scalars().all()
    return R(total=len(items), items=[{
        "id": r.id, "position": r.position, "department": r.department, "headcount": r.headcount,
        "description": r.description or "", "status": r.status, "priority": r.priority,
        "salary_range": r.salary_range or "", "contact": r.contact or "",
        "resume_count": r.resume_count, "interview_count": r.interview_count,
        "offer_count": r.offer_count, "hire_count": r.hire_count,
        "tags": r.tags or "", "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in items])


@router.post("")
def create(body: dict, db: Session = Depends(get_db), _=Depends(require_auth)):
    r = RecruitmentModel(
        position=body["position"], department=body.get("department", ""),
        headcount=body.get("headcount", 1), description=body.get("description", ""),
        status=body.get("status", "open"), priority=body.get("priority", "normal"),
        salary_range=body.get("salary_range", ""), contact=body.get("contact", ""),
        tags=body.get("tags", ""),
    )
    db.add(r); db.commit(); db.refresh(r)
    return R(id=r.id)


@router.put("/{rid}")
def update(rid: int, body: dict, db: Session = Depends(get_db), _=Depends(require_auth)):
    r = db.execute(select(RecruitmentModel).where(RecruitmentModel.id == rid)).scalar_one_or_none()
    if not r:
        return R(message="not found")
    for k, v in body.items():
        if hasattr(r, k) and v is not None:
            setattr(r, k, v)
    r.updated_at = datetime.datetime.now()
    db.commit()
    return R(message="ok")


@router.delete("/{rid}", status_code=204)
def delete(rid: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    r = db.execute(select(RecruitmentModel).where(RecruitmentModel.id == rid)).scalar_one_or_none()
    if r:
        db.delete(r); db.commit()


@router.post("/{rid}/resume")
def add_resume(rid: int, body: dict, db: Session = Depends(get_db), _=Depends(require_auth)):
    r = db.execute(select(RecruitmentModel).where(RecruitmentModel.id == rid)).scalar_one_or_none()
    if r:
        r.resume_count = (r.resume_count or 0) + 1
        db.commit()
        return R(message="ok", resume_count=r.resume_count)
    return R(message="not found")
