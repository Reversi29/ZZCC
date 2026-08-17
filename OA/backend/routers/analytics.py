"""
GET /api/analytics/overview — 全局经营概览
"""
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db, WorkflowHistory
from routers.auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# 终态之外都是待审批
TERMINAL_STATUSES = {"Approved", "Rejected"}


def _pending_statuses() -> set[str]:
    """Draft / Submitted 以及 Pending-LN 等中间态均为待审批"""
    return {"Draft", "Submitted"}


def _pending_by_type(db: Session) -> dict[str, int]:
    result = {}
    from database import Base
    for doctype, model_cls in {
        "ExpenseClaim": Base.metadata.tables.get("expense_claims"),
        "PurchaseOrder": Base.metadata.tables.get("purchase_orders"),
        "JournalEntry": Base.metadata.tables.get("journal_entries"),
        "LeaveRequest": Base.metadata.tables.get("leave_requests"),
        "Contract": Base.metadata.tables.get("contracts"),
        "Project": Base.metadata.tables.get("projects"),
        "StockMovement": Base.metadata.tables.get("stock_movements"),
    }.items():
        if model_cls is None:
            result[doctype] = 0
            continue
        status_col = model_cls.columns.get("status")
        if status_col is None:
            result[doctype] = 0
            continue
        pend = _pending_statuses()
        q = select(func.count()).select_from(model_cls).where(status_col.in_(pend))
        result[doctype] = db.execute(q).scalar() or 0
    return result


def _monthly_actions(db: Session) -> tuple[int, int]:
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    approved = (
        db.execute(
            select(func.count())
            .select_from(WorkflowHistory)
            .where(WorkflowHistory.action == "approve")
            .where(WorkflowHistory.creation >= start)
        ).scalar()
        or 0
    )
    rejected = (
        db.execute(
            select(func.count())
            .select_from(WorkflowHistory)
            .where(WorkflowHistory.action == "reject")
            .where(WorkflowHistory.creation >= start)
        ).scalar()
        or 0
    )
    return approved, rejected


def _hr_stats(db: Session) -> dict:
    from database import Employee, LeaveRequest

    total = db.execute(select(func.count()).select_from(Employee)).scalar() or 0

    today = datetime.utcnow().date()
    pend = _pending_statuses()
    on_leave = db.execute(
        select(func.count())
        .select_from(LeaveRequest)
        .where(LeaveRequest.status == "Approved")
        .where(LeaveRequest.start_date <= today)
        .where(LeaveRequest.end_date >= today)
    ).scalar() or 0

    pending_lr = (
        db.execute(
            select(func.count())
            .select_from(LeaveRequest)
            .where(LeaveRequest.status.in_(pend))
        ).scalar()
        or 0
    )
    return {"total_employees": total, "on_leave_today": on_leave, "pending_leave_requests": pending_lr}


def _crm_stats(db: Session) -> dict:
    from database import Lead, Contact, Opportunity, Contract

    leads = db.execute(select(func.count()).select_from(Lead)).scalar() or 0
    contacts = db.execute(select(func.count()).select_from(Contact)).scalar() or 0
    opportunities = db.execute(select(func.count()).select_from(Opportunity)).scalar() or 0

    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    contracts_signed = (
        db.execute(
            select(func.count())
            .select_from(Contract)
            .where(Contract.status == "Approved")
            .where(Contract.creation >= start)
        ).scalar()
        or 0
    )
    return {
        "leads": leads,
        "contacts": contacts,
        "opportunities": opportunities,
        "contracts_signed_this_month": contracts_signed,
    }


def _stock_stats(db: Session) -> dict:
    from database import Item, Warehouse

    total_items = db.execute(select(func.count()).select_from(Item)).scalar() or 0
    warehouses = db.execute(select(func.count()).select_from(Warehouse)).scalar() or 0
    return {"total_items": total_items, "low_stock_items": 0, "total_warehouses": warehouses}


@router.get("/overview")
def overview(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """
    全局经营概览：
    - workflow: 待审批单据（按类型）+ 本月审批/驳回数
    - hr:      员工总数 + 今日请假 + 待审批请假
    - crm:     线索/联系人/商机数 + 本月签约合同
    - stock:   物料总数 + 仓库数
    """
    pending = _pending_by_type(db)
    approved, rejected = _monthly_actions(db)
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "workflow": {
            "pending_by_type": pending,
            "approved_this_month": approved,
            "rejected_this_month": rejected,
            "total_pending": sum(pending.values()),
        },
        "hr": _hr_stats(db),
        "crm": _crm_stats(db),
        "stock": _stock_stats(db),
    }
