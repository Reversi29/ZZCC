"""
routers/workflow.py — 审批工作流引擎
支持：ExpenseClaim / PurchaseOrder / JournalEntry 状态流转
表名遵循 SQLite snake_case 约定
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from database import get_db, ExpenseClaim, PurchaseOrder, JournalEntry

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# ── 表名映射（Python 类名 → 实际表名）─────────────────────────────
TABLE_MAP = {
    "ExpenseClaim":  "expense_claims",
    "PurchaseOrder": "purchase_orders",
    "JournalEntry":  "journal_entries",
}
# 状态字段
STATUS_COL = {
    "ExpenseClaim":  "approval_status",
    "PurchaseOrder": "status",
    "JournalEntry":  "docstatus",
}
# JournalEntry docstatus: 0=Draft, 1=Submitted, 2=Approved, 3=Rejected
JE_TO_INT  = {"Draft": 0, "Submitted": 1, "Approved": 2, "Rejected": 3}
JE_TO_STR  = {v: k for k, v in JE_TO_INT.items()}

# ── 状态机 ─────────────────────────────────────────────────────
APPROVAL_ACTIONS = {
    "ExpenseClaim": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted", "label": "提交审批", "color": "#2563eb"},
        {"action": "approve", "from": "Submitted", "to": "Approved",  "label": "批准",     "color": "#16a34a"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected",  "label": "拒绝",     "color": "#dc2626"},
        {"action": "pay",     "from": "Approved",  "to": "Paid",      "label": "确认付款", "color": "#7c3aed"},
    ],
    "PurchaseOrder": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted", "label": "提交审批", "color": "#2563eb"},
        {"action": "approve", "from": "Submitted", "to": "Approved",  "label": "批准下单", "color": "#16a34a"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected",  "label": "拒绝",     "color": "#dc2626"},
        {"action": "order",   "from": "Approved",  "to": "Ordered",   "label": "确认订购", "color": "#0891b2"},
        {"action": "receive", "from": "Ordered",   "to": "Received",  "label": "确认收货", "color": "#059669"},
    ],
    "JournalEntry": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted", "label": "提交审批", "color": "#2563eb"},
        {"action": "approve", "from": "Submitted", "to": "Approved",  "label": "批准记账", "color": "#16a34a"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected",  "label": "拒绝",     "color": "#dc2626"},
    ],
}


# ── 请求模型 ───────────────────────────────────────────────────
class WorkflowActionRequest(BaseModel):
    name: str
    action: str
    comment: Optional[str] = None


# ── 核心工具 ───────────────────────────────────────────────────
def _get_status(doctype: str, name: str, db: Session) -> str:
    tbl = TABLE_MAP[doctype]
    col = STATUS_COL[doctype]
    row = db.execute(text(f"SELECT {col} FROM {tbl} WHERE name=:n"), {"n": name}).fetchone()
    if not row or row[0] is None:
        return "Draft"
    val = row[0]
    if doctype == "JournalEntry":
        return JE_TO_STR.get(int(val), "Draft")
    return str(val)


def _pending_rows(doctype: str, db: Session) -> list:
    """返回所有 Submitted 状态的记录"""
    tbl = TABLE_MAP[doctype]
    col = STATUS_COL[doctype]
    if doctype == "JournalEntry":
        rows = db.execute(text(f"SELECT name, title, posting_date FROM {tbl} WHERE docstatus = 1")).fetchall()
        return [{"name": r[0], "title": r[1], "amount": None, "created": r[2]} for r in rows]
    else:
        amt_col = "claim_amount" if doctype == "ExpenseClaim" else "total"
        rows = db.execute(
            text(f"SELECT name, {amt_col}, creation FROM {tbl} WHERE {col} = :s"),
            {"s": "Submitted"}
        ).fetchall()
        return [{"name": r[0], "amount": r[1], "created": r[2]} for r in rows]


def _title(doctype: str, name: str, db: Session) -> str:
    tbl = TABLE_MAP[doctype]
    if doctype == "ExpenseClaim":
        r = db.execute(text(
            f"SELECT employee, expense_type, claim_amount FROM {tbl} WHERE name=:n"
        ), {"n": name}).fetchone()
        return f"{r[0]} - {r[1]} - ¥{r[2]:,.0f}" if r else name
    elif doctype == "PurchaseOrder":
        r = db.execute(text(
            f"SELECT supplier, total FROM {tbl} WHERE name=:n"
        ), {"n": name}).fetchone()
        total = f"¥{r[1]:,.0f}" if r and r[1] else ""
        return f"PO-{name} | {r[0] if r else ''} | {total}".strip().rstrip("|")
    else:  # JournalEntry
        r = db.execute(text(
            f"SELECT title, posting_date FROM {tbl} WHERE name=:n"
        ), {"n": name}).fetchone()
        return f"{r[0]} ({r[1]})" if r else name


# ── GET /api/workflow/pending ──────────────────────────────────
@router.get("/pending")
def get_pending(db: Session = Depends(get_db)):
    results = []
    for doctype in TABLE_MAP:
        for row in _pending_rows(doctype, db):
            results.append({
                "name":       row["name"],
                "doctype":    doctype,
                "title":      _title(doctype, row["name"], db),
                "amount":     row["amount"],
                "status":     "Submitted",
                "created":    str(row["created"])[:16] if row.get("created") else None,
                "submitter":  None,
                "actions":    APPROVAL_ACTIONS.get(doctype, []),
            })

    results.sort(key=lambda x: (x["doctype"], x["name"]))
    return {"pending": results, "total": len(results)}


# ── POST /api/workflow/action ──────────────────────────────────
@router.post("/action")
def do_action(body: WorkflowActionRequest, db: Session = Depends(get_db)):
    prefix_map = {"EXP-": "ExpenseClaim", "PO-": "PurchaseOrder", "JE-": "JournalEntry"}
    doctype = next((d for p, d in prefix_map.items() if body.name.startswith(p)), None)
    if not doctype:
        raise HTTPException(400, f"无法识别单据类型: {body.name}")

    current = _get_status(doctype, body.name, db)
    actions = APPROVAL_ACTIONS.get(doctype, [])
    matched = next(
        (a for a in actions if a["action"] == body.action and a["from"] == current),
        None
    )
    if not matched:
        raise HTTPException(
            400, f"动作 '{body.action}' 不适用于当前状态 '{current}'（{doctype} {body.name}）"
        )

    tbl = TABLE_MAP[doctype]
    col = STATUS_COL[doctype]
    new_val = matched["to"]
    if doctype == "JournalEntry":
        new_val = JE_TO_INT[new_val]

    db.execute(
        text(f"UPDATE {tbl} SET {col} = :v, modified = datetime('now') WHERE name = :n"),
        {"v": new_val, "n": body.name}
    )
    db.commit()
    return {
        "ok":          True,
        "name":        body.name,
        "doctype":     doctype,
        "action_label": matched["label"],
        "from":        current,
        "to":          matched["to"],
        "comment":     body.comment,
    }


# ── GET /api/workflow/doc/{doctype}/{name} ─────────────────────
@router.get("/doc/{doctype}/{name}")
def get_doc_workflow(doctype: str, name: str, db: Session = Depends(get_db)):
    if doctype not in TABLE_MAP:
        raise HTTPException(400, f"不支持: {doctype}")

    tbl = TABLE_MAP[doctype]
    row = db.execute(text(f"SELECT * FROM {tbl} WHERE name=:n"), {"n": name}).fetchone()
    if not row:
        raise HTTPException(404, f"单据不存在: {name}")

    cols = [c[1] for c in db.execute(text(f"PRAGMA table_info({tbl})")).fetchall()]
    data = dict(zip(cols, row))

    current = _get_status(doctype, name, db)
    available = [a for a in APPROVAL_ACTIONS.get(doctype, []) if a["from"] == current]

    return {
        "doc":               data,
        "current_status":    current,
        "available_actions": available,
        "status_col":        STATUS_COL.get(doctype, "status"),
    }


# ── GET /api/workflow/stats ────────────────────────────────────
@router.get("/stats")
def workflow_stats(db: Session = Depends(get_db)):
    stats = {}
    for doctype, tbl in TABLE_MAP.items():
        col = STATUS_COL[doctype]
        if doctype == "JournalEntry":
            rows = db.execute(text(f"SELECT docstatus, COUNT(*) FROM {tbl} GROUP BY docstatus")).fetchall()
            stats[doctype] = {JE_TO_STR.get(int(r[0]) if r[0] is not None else 0, "Draft"): r[1] for r in rows}
        else:
            rows = db.execute(text(f"SELECT {col}, COUNT(*) FROM {tbl} GROUP BY {col}")).fetchall()
            stats[doctype] = {str(r[0]): r[1] for r in rows}
    return stats
