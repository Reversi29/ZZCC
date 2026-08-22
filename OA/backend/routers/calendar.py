"""
routers/calendar.py — 日程/日历聚合
从 Project/Task/Contract/LeaveRequest/AttendanceRecord 聚合所有有日期的事件
返回：{ events: [{id,title,doctype,date_start,date_end,color,icon,data}], total }
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from database import get_db
from database import Project, Task, Contract, LeaveRequest, AttendanceRecord
from routers.auth import require_auth

router = APIRouter(prefix="/api/calendar", tags=["Calendar"])

R = dict

def _fmt(dt) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(dt, date):
        return dt.isoformat()
    return ""

def _add_event(events, doctype, doc_name, title, start, end, icon, color):
    if not start:
        return
    events.append({
        "id": doc_name or "",
        "title": title or doc_name or "",
        "doctype": doctype,
        "date_start": _fmt(start),
        "date_end": _fmt(end),
        "icon": icon,
        "color": color,
        "data": doc_name or "",
    })

@router.get("/events")
def calendar_events(
    from_date: str = Query(None, description="YYYY-MM-DD"),
    to_date: str = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """聚合所有带日期的事件"""
    events = []
    start = datetime.fromisoformat(from_date).date() if from_date else date.today()
    end = datetime.fromisoformat(to_date).date() if to_date else (start + timedelta(days=31))

    # Project
    for p in db.query(Project).filter(Project.start_date <= end, Project.end_date >= start).all():
        _add_event(events, "Project", p.name, p.project_name, p.start_date, p.end_date, "📁", "#4a90d9")

    # Task
    for t in db.query(Task).filter(Task.start_date <= end, Task.end_date >= start).all():
        _add_event(events, "Task", t.name, t.subject, t.start_date, t.end_date, "✅", "#27ae60")

    # Contract
    for c in db.query(Contract).filter(Contract.start_date <= end, Contract.end_date >= start).all():
        _add_event(events, "Contract", c.name, c.contract_name, c.start_date, c.end_date, "⚖️", "#8e44ad")

    # LeaveRequest
    for l in db.query(LeaveRequest).filter(LeaveRequest.start_date <= end, LeaveRequest.end_date >= start).all():
        icon = "📅"
        color = {"Submitted":"#f39c12","Approved":"#27ae60","Rejected":"#e74c3c"}.get(l.status or "", "#95a5a6")
        _add_event(events, "LeaveRequest", l.name, f"{l.employee_name or l.name} {l.leave_type}", l.start_date, l.end_date, icon, color)

    # AttendanceRecord (只加最近7天)
    recent = start - timedelta(days=7)
    for a in db.query(AttendanceRecord).filter(AttendanceRecord.date >= recent, AttendanceRecord.date <= end).all():
        icon = "🕐"
        color = "#16a085" if a.check_in and a.check_out else "#f1c40f"
        _add_event(events, "Attendance", f"att-{a.employee}-{a.date}", f"考勤 {a.employee}", a.date, a.date, icon, color)

    events.sort(key=lambda e: e["date_start"])
    return R(data={"events": events, "length": len(events)})