"""
routers/hr.py — 人力资源
LeaveRequest / AttendanceRecord / SalaryRecord / Employee
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from pydantic import BaseModel
from datetime import date, time
from typing import Optional
from database import get_db, Employee, LeaveRequest, AttendanceRecord, SalaryRecord, User
from routers.auth import require_auth, require_admin, CurrentUser
from routers._db import model_to_dict, seq_for


router = APIRouter(prefix="/api/hr", tags=["HR"])
_md = lambda m: model_to_dict(m)


# ── Request models ────────────────────────────────────────────
class LeaveApplyReq(BaseModel):
    leave_type: str          # Annual / Sick / Personal / Unpaid
    start_date: str          # ISO date
    end_date: str
    reason: Optional[str] = None


class AttendanceReq(BaseModel):
    employee: str
    date: str
    check_in: Optional[str] = None   # HH:MM
    check_out: Optional[str] = None
    status: Optional[str] = "Normal"
    remark: Optional[str] = None


class SalaryReq(BaseModel):
    employee: str
    year_month: str          # "2025-08"
    base_salary: float = 0.0
    bonus: float = 0.0
    deductions: float = 0.0
    net_salary: Optional[float] = None
    pay_date: Optional[str] = None
    remark: Optional[str] = None


# ── Employee CRUD (admin only) ─────────────────────────────────
@router.get("/employees")
def list_employees(
    db: Session = Depends(get_db),
    dept_id: Optional[int] = None,
    current_user: CurrentUser = Depends(require_admin),
):
    q = db.query(Employee)
    if dept_id:
        q = q.filter(Employee.department_id == dept_id)
    return {"data": [_md(e) for e in q.all()]}


@router.post("/employees")
def create_employee(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_admin)):
    name = data.get("name") or seq_for("EMP", db)
    if db.query(Employee).filter(Employee.name == name).first():
        raise HTTPException(400, "Employee already exists")
    e = Employee(name=name, employee_name=data.get("employee_name", name))
    for k, v in data.items():
        if k not in ("name",) and hasattr(e, k):
            setattr(e, k, v)
    db.add(e); db.commit(); db.refresh(e)
    return {"data": _md(e)}


@router.get("/employees/{name}")
def get_employee(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    e = db.query(Employee).filter(Employee.name == name).first()
    if not e:
        raise HTTPException(404, "Employee not found")
    return {"data": _md(e)}


@router.put("/employees/{name}")
def update_employee(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_admin)):
    e = db.query(Employee).filter(Employee.name == name).first()
    if not e:
        raise HTTPException(404, "Employee not found")
    for k, v in data.items():
        if k not in ("name",) and hasattr(e, k):
            setattr(e, k, v)
    db.commit(); db.refresh(e)
    return {"data": _md(e)}


# ── LeaveRequest ──────────────────────────────────────────────
@router.get("/leaves")
def list_leaves(
    db: Session = Depends(get_db),
    status: Optional[str] = None,
    employee: Optional[str] = None,
    current_user: CurrentUser = Depends(require_auth),
):
    q = db.query(LeaveRequest)
    if employee:
        q = q.filter(LeaveRequest.employee == employee)
    elif current_user.role == "user":
        q = q.filter(LeaveRequest.employee == current_user.username)
    if status:
        q = q.filter(LeaveRequest.status == status)
    rows = q.order_by(LeaveRequest.id.desc()).all()
    return {"data": [_md(r) for r in rows]}


@router.post("/leaves")
def apply_leave(req: LeaveApplyReq, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    # 自动生成 name（LR-YYYY-NNNN）
    prefix = f"LR-{req.start_date[:4]}-"
    last = db.execute(
        __import__("sqlalchemy").text(
            "SELECT name FROM leave_requests WHERE name LIKE :p ORDER BY name DESC LIMIT 1"
        ), {"p": prefix + "%"}
    ).fetchone()
    n = int(last[0].split("-")[-1]) + 1 if last else 1
    lr = LeaveRequest(
        name=f"{prefix}{n:04d}",
        employee=current_user.username,
        leave_type=req.leave_type,
        start_date=date.fromisoformat(req.start_date),
        end_date=date.fromisoformat(req.end_date),
        reason=req.reason,
        status="Draft",
    )
    # 计算天数
    delta = lr.end_date - lr.start_date
    lr.days = max(1.0, delta.days + 1)
    db.add(lr); db.commit(); db.refresh(lr)
    lr.status = "Submitted"
    db.commit()
    return {"data": _md(lr), "message": "请假申请已提交审批", "id": lr.id}


@router.get("/leaves/{id}")
def get_leave(id: int, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    lr = db.query(LeaveRequest).filter(LeaveRequest.id == id).first()
    if not lr:
        raise HTTPException(404, "Leave request not found")
    if current_user.role == "user" and lr.employee != current_user.username:
        raise HTTPException(403, "无权限查看")
    return {"data": _md(lr)}


# ── Attendance ────────────────────────────────────────────────
@router.get("/attendance")
def list_attendance(
    db: Session = Depends(get_db),
    employee: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: CurrentUser = Depends(require_auth),
):
    q = db.query(AttendanceRecord)
    if employee:
        q = q.filter(AttendanceRecord.employee == employee)
    elif current_user.role == "user":
        q = q.filter(AttendanceRecord.employee == current_user.username)
    if start_date:
        q = q.filter(AttendanceRecord.date >= date.fromisoformat(start_date))
    if end_date:
        q = q.filter(AttendanceRecord.date <= date.fromisoformat(end_date))
    rows = q.order_by(AttendanceRecord.date.desc()).limit(200).all()
    return {"data": [_md(r) for r in rows]}


@router.post("/attendance")
def create_attendance(req: AttendanceReq, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_admin)):
    r = AttendanceRecord(
        employee=req.employee,
        date=date.fromisoformat(req.date),
        check_in=time.fromisoformat(req.check_in) if req.check_in else None,
        check_out=time.fromisoformat(req.check_out) if req.check_out else None,
        status=req.status or "Normal",
        remark=req.remark,
    )
    db.add(r); db.commit(); db.refresh(r)
    return {"data": _md(r)}


# ── Salary ─────────────────────────────────────────────────────
@router.get("/salary")
def list_salary(
    db: Session = Depends(get_db),
    employee: Optional[str] = None,
    year_month: Optional[str] = None,
    current_user: CurrentUser = Depends(require_auth),
):
    q = db.query(SalaryRecord)
    if employee:
        q = q.filter(SalaryRecord.employee == employee)
    elif current_user.role == "user":
        q = q.filter(SalaryRecord.employee == current_user.username)
    if year_month:
        q = q.filter(SalaryRecord.year_month == year_month)
    rows = q.order_by(SalaryRecord.year_month.desc()).limit(200).all()
    return {"data": [_md(r) for r in rows]}


@router.post("/salary")
def create_salary(req: SalaryReq, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_admin)):
    r = SalaryRecord(
        employee=req.employee,
        year_month=req.year_month,
        base_salary=req.base_salary,
        bonus=req.bonus,
        deductions=req.deductions,
        net_salary=req.net_salary or (req.base_salary + req.bonus - req.deductions),
        pay_date=date.fromisoformat(req.pay_date) if req.pay_date else None,
        remark=req.remark,
    )
    db.add(r); db.commit(); db.refresh(r)
    return {"data": _md(r)}


@router.get("/salary/{id}")
def get_salary(id: int, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    r = db.query(SalaryRecord).filter(SalaryRecord.id == id).first()
    if not r:
        raise HTTPException(404, "Salary record not found")
    if current_user.role == "user" and r.employee != current_user.username:
        raise HTTPException(403, "无权限查看")
    return {"data": _md(r)}
