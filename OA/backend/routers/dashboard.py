"""
routers/dashboard.py — 增强版 Dashboard
提供 quickstats: 待审批统计、未读通知、最近活动
"""
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session

from database import get_db, Notification
from routers.auth import require_auth

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

R = dict


class QuickStats(BaseModel):
    pending_approvals: int
    pending_by_type: dict
    unread_notifications: int
    recent_notifications: list
    total_employees: int
    total_projects: int
    total_contracts: int


class MarkReadRequest(BaseModel):
    ids: list[int] = []


@router.get("/quickstats")
def quickstats(db: Session = Depends(get_db),
               current_user=Depends(require_auth)):
    username = current_user.username

    notif_q = select(func.count()).select_from(Notification).where(
        Notification.recipient == username,
        Notification.is_read == False,
    )
    unread_count = db.execute(notif_q).scalar() or 0

    recent_notifs = db.execute(
        select(Notification).where(
            Notification.recipient == username
        ).order_by(desc(Notification.creation)).limit(5)
    ).scalars().all()
    recent_list = [{
        "id": n.id,
        "title": n.title,
        "body": (n.body or "")[:80],
        "ntype": n.ntype,
        "doctype": n.doctype,
        "doc_name": n.doc_name,
        "action": n.action,
        "is_read": n.is_read,
        "priority": n.priority,
        "created": n.creation.isoformat() if n.creation else None,
    } for n in recent_notifs]

    pending_by_type = _pending_by_type(db)
    pending_total = sum(pending_by_type.values())

    from database import Employee, Project, Contract
    total_employees = db.execute(select(func.count()).select_from(Employee)).scalar() or 0
    total_projects = db.execute(select(func.count()).select_from(Project)).scalar() or 0
    total_contracts = db.execute(select(func.count()).select_from(Contract)).scalar() or 0

    return QuickStats(
        pending_approvals=pending_total,
        pending_by_type=pending_by_type,
        unread_notifications=unread_count,
        recent_notifications=recent_list,
        total_employees=total_employees,
        total_projects=total_projects,
        total_contracts=total_contracts,
    )


@router.post("/notifications/mark-read")
def mark_notifications_read(
    body: MarkReadRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """批量标记通知已读"""
    if not body.ids:
        return R(message="ok")
    q = db.query(Notification).filter(
        Notification.id.in_(body.ids),
        Notification.recipient == current_user.username,
    )
    q.update({Notification.is_read: True}, synchronize_session="fetch")
    db.commit()
    return R(message="ok")


# ── 内部 ──

PENDING_STATUSES = {"Draft", "Submitted"}


def _pending_by_type(db: Session) -> dict:
    from database import Base
    result = {}
    for doctype, table_name in {
        "ExpenseClaim": "expense_claims",
        "PurchaseOrder": "purchase_orders",
        "JournalEntry": "journal_entries",
        "LeaveRequest": "leave_requests",
        "Contract": "contracts",
        "Project": "projects",
    }.items():
        tbl = Base.metadata.tables.get(table_name)
        if tbl is None:
            result[doctype] = 0
            continue
        status_col = tbl.c.get("status")
        if status_col is None:
            result[doctype] = 0
            continue
        q = select(func.count()).select_from(tbl).where(status_col.in_(PENDING_STATUSES))
        result[doctype] = db.execute(q).scalar() or 0
    return result
