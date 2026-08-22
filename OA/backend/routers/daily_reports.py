"""
routers/daily_reports.py — 日报/周报
"""
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, date
from pydantic import BaseModel
from database import get_db, DailyReport
from routers.auth import require_auth

router = APIRouter(prefix="/api/reports", tags=["DailyReports"])

R = dict

class ReportCreate(BaseModel):
    title: str = ""
    report_type: str = "daily"
    report_date: str = ""
    content: str = ""
    status: str = "draft"

class ReportUpdate(BaseModel):
    title: str = ""
    content: str = ""
    status: str = ""

def _to_dict(r):
    return {
        "id": r.id,
        "title": r.title,
        "report_type": r.report_type,
        "report_date": (r.report_date.isoformat() if isinstance(r.report_date, date) else r.report_date) if r.report_date else "",
        "content": r.content,
        "author": r.author,
        "status": r.status,
        "created": (r.creation.isoformat() if isinstance(r.creation, datetime) else r.creation) if r.creation else "",
        "modified": (r.modified.isoformat() if isinstance(r.modified, datetime) else r.modified) if r.modified else "",
    }

@router.get("/list")
def report_list(
    report_type: str = Query("daily", description="daily/weekly"),
    author: str = Query(None, description="按作者过滤"),
    from_date: str = Query(None),
    to_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    q = db.query(DailyReport).filter(DailyReport.report_type == report_type)
    if author:
        q = q.filter(DailyReport.author == author)
    if from_date:
        q = q.filter(DailyReport.report_date >= date.fromisoformat(from_date))
    if to_date:
        q = q.filter(DailyReport.report_date <= date.fromisoformat(to_date))
    rows = q.order_by(DailyReport.report_date.desc()).all()
    return R(data={"items": [_to_dict(r) for r in rows], "length": len(rows)})

@router.post("/create")
def report_create(body: ReportCreate = Body(...),
                  db: Session = Depends(get_db),
                  current_user=Depends(require_auth)):
    dt = date.fromisoformat(body.report_date) if body.report_date else date.today()
    r = DailyReport(
        title=body.title,
        report_type=body.report_type,
        report_date=dt,
        content=body.content,
        author=current_user.username,
        status=body.status,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return R(data=_to_dict(r), message="Report created")

@router.put("/update/{id}")
def report_update(id: int, body: ReportUpdate = Body(...),
                  db: Session = Depends(get_db),
                  current_user=Depends(require_auth)):
    r = db.query(DailyReport).get(id)
    if not r or r.author != current_user.username:
        raise HTTPException(status_code=403, detail="禁止操作")
    if body.title: r.title = body.title
    if body.content: r.content = body.content
    if body.status: r.status = body.status
    db.commit()
    db.refresh(r)
    return R(data=_to_dict(r), message="Report updated")

@router.delete("/delete/{id}")
def report_delete(id: int, db: Session = Depends(get_db),
                  current_user=Depends(require_auth)):
    r = db.query(DailyReport).get(id)
    if not r or r.author != current_user.username:
        raise HTTPException(status_code=403, detail="禁止操作")
    db.delete(r)
    db.commit()
    return R(message="Report deleted", status_code=204)