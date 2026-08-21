"""
routers/workflow.py — 审批工作流引擎
支持：ExpenseClaim / PurchaseOrder / JournalEntry 状态流转
表名遵循 SQLite snake_case 约定
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Annotated
from database import get_db, ExpenseClaim, PurchaseOrder, JournalEntry, LeaveRequest, WorkflowHistory, Notification, ApprovalRule, Delegation, User, Budget, StockEntry, StockLedger, StockBalance
from routers.auth import get_current_user, CurrentUser
from routers.notifications import notify
from routers._org import budget_for
from sqlalchemy import or_

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# ── 表名映射（Python 类名 → 实际表名）─────────────────────────────
TABLE_MAP = {
    "ExpenseClaim":  "expense_claims",
    "PurchaseOrder": "purchase_orders",
    "JournalEntry":  "journal_entries",
    "LeaveRequest":  "leave_requests",
    "Contract":     "contracts",
    "StockEntry":   "stock_entries",
    "Project":      "projects",
}
# 状态字段
STATUS_COL = {
    "ExpenseClaim":  "approval_status",
    "PurchaseOrder": "status",
    "JournalEntry":  "docstatus",
    "LeaveRequest":  "status",
    "Contract":     "status",
    "StockEntry":   "status",
    "Project":      "status",
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
    "LeaveRequest": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted", "label": "提交审批", "color": "#2563eb"},
        {"action": "approve", "from": "Submitted", "to": "Approved",  "label": "批准",     "color": "#16a34a"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected", "label": "拒绝",     "color": "#dc2626"},
        {"action": "cancel",  "from": "Draft",     "to": "Cancelled", "label": "撤销",     "color": "#6b7280"},
    ],
    "Contract": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted", "label": "提交审批", "color": "#2563eb"},
        {"action": "approve", "from": "Submitted", "to": "Approved",  "label": "批准生效", "color": "#16a34a"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected",  "label": "拒绝",     "color": "#dc2626"},
        {"action": "cancel",  "from": "Draft",     "to": "Cancelled", "label": "撤销",     "color": "#6b7280"},
    ],
    "StockEntry": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted", "label": "提交审批", "color": "#2563eb"},
        {"action": "approve", "from": "Submitted", "to": "Approved",  "label": "批准执行", "color": "#16a34a"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected",  "label": "拒绝",     "color": "#dc2626"},
        {"action": "cancel",  "from": "Draft",     "to": "Cancelled", "label": "撤销",     "color": "#6b7280"},
    ],
    "Project": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted", "label": "提交立项", "color": "#2563eb"},
        {"action": "approve", "from": "Submitted", "to": "Approved",  "label": "批准立项", "color": "#16a34a"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected",  "label": "拒绝",     "color": "#dc2626"},
        {"action": "cancel",  "from": "Draft",     "to": "Cancelled", "label": "撤销",     "color": "#6b7280"},
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
    # LeaveRequest 用 id，其他用 name
    pk_col = "id" if doctype == "LeaveRequest" else "name"
    row = db.execute(text(f"SELECT {col} FROM {tbl} WHERE {pk_col}=:pk"), {"pk": name}).fetchone()
    if not row:
        raise HTTPException(404, f"单据不存在: {name}")
    val = row[0]
    if val is None:
        raise HTTPException(404, f"单据不存在: {name}")
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
        # LeaveRequest 用 id 列，其他用 name 列；动态探测可用列
        if doctype == "LeaveRequest":
            name_col = "id"
            amt_col = None
            cols_to_select = "id, creation"
        else:
            name_col = "name"
            amt_col = {
                "ExpenseClaim": "claim_amount",
                "PurchaseOrder": "total",
                "Contract": "contract_value",
                "StockEntry": "items_json",   # items_json 无金额汇总，pending 列表不显示金额
                "Project": None,              # 项目无金额
            }.get(doctype, "total")
            cols_to_select = f"name, creation" if amt_col is None else f"name, {amt_col}, creation"
        rows = db.execute(
            text(f"SELECT {cols_to_select} FROM {tbl} WHERE {col} = :s"),
            {"s": "Submitted"}
        ).fetchall()
        if doctype == "LeaveRequest":
            return [{"name": str(r[0]), "created": r[1]} for r in rows]
        if amt_col is None:
            return [{"name": r[0], "created": r[1]} for r in rows]
        return [{"name": r[0], "amount": r[1], "created": r[2]} for r in rows]


def _title(doctype: str, name: str, db: Session) -> str:
    tbl = TABLE_MAP[doctype]
    pk_col = "id" if doctype == "LeaveRequest" else "name"
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
    elif doctype == "LeaveRequest":
        r = db.execute(text(
            f"SELECT leave_type, start_date, end_date, employee FROM {tbl} WHERE id=:pk"
        ), {"pk": name}).fetchone()
        if r:
            return f"请假 {r[0]} | {r[1]}~{r[2]} | {r[3]}"
        return f"请假申请 {name}"
    elif doctype == "Contract":
        r = db.execute(text(
            f"SELECT contract_name, contract_value, party_a, party_b FROM {tbl} WHERE name=:n"
        ), {"n": name}).fetchone()
        if r:
            val = f"¥{r[1]:,.0f}" if r[1] else ""
            return f"{r[0]} | {r[2]}↔{r[3]} | {val}".strip().rstrip("|")
        return name
    elif doctype == "Project":
        r = db.execute(text(
            f"SELECT project_name, priority, percent_complete FROM {tbl} WHERE name=:n"
        ), {"n": name}).fetchone()
        if r:
            return f"{r[0]} | {r[1]} | {r[2]:.0f}%"
        return name
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
def _post_stock_ledger(db: Session, stock_entry_name: str) -> None:
    """StockEntry 审批通过后，将 items_json 解析并写入库存台账和余额表"""
    import json
    from datetime import date
    entry = db.query(StockEntry).filter_by(name=stock_entry_name).first()
    if not entry:
        return
    items = []
    try:
        items = json.loads(entry.items_json or "[]")
    except Exception:
        return
    if not items:
        return

    posting_date = entry.modified.date() if entry.modified else date.today()
    warehouse = entry.to_warehouse or entry.from_warehouse or "Default"

    for item_row in items:
        item_code = item_row.get("item_code") or item_row.get("item")
        qty = float(item_row.get("qty") or item_row.get("quantity") or 0)
        rate = float(item_row.get("rate") or item_row.get("valuation_rate") or 0)
        if not item_code or qty == 0:
            continue

        # 计算 IN/OUT
        if entry.stock_entry_type == "Material Receipt":
            incoming, outgoing = qty, 0.0
        elif entry.stock_entry_type == "Material Issue":
            incoming, outgoing = 0.0, qty
        elif entry.stock_entry_type == "Material Transfer":
            # 转出先减，转入后加（这里只处理入库侧）
            incoming, outgoing = qty, 0.0
        else:
            incoming, outgoing = qty, 0.0

        # 查询当前余额
        bal = db.query(StockBalance).filter_by(
            item_code=item_code, warehouse=warehouse
        ).first()

        if bal:
            bal.actual_qty = float(bal.actual_qty or 0) + incoming - outgoing
            bal.stock_value = bal.actual_qty * rate
            bal.last_updated = posting_date
            bal.modified = datetime.utcnow()
        else:
            bal = StockBalance(
                item_code=item_code, warehouse=warehouse,
                actual_qty=incoming - outgoing,
                reserved_qty=0.0, ordered_qty=0.0,
                valuation_rate=rate,
                stock_value=(incoming - outgoing) * rate,
                last_updated=posting_date,
            )
            db.add(bal)

        # 写入台账明细
        balance_qty = (bal.actual_qty if bal.id else (incoming - outgoing))
        db.add(StockLedger(
            item_code=item_code, warehouse=warehouse,
            stock_entry_type=entry.stock_entry_type,
            stock_entry_name=entry.name,
            posting_date=posting_date,
            incoming_qty=incoming, outgoing_qty=outgoing,
            balance_qty=balance_qty,
            valuation_rate=rate,
            stock_value=balance_qty * rate,
            description=f"{entry.stock_entry_type}: {entry.name}",
        ))


@router.post("/action")
def do_action(
    body: WorkflowActionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    prefix_map = {"EXP-": "ExpenseClaim", "PO-": "PurchaseOrder", "JE-": "JournalEntry",
                  "LR-": "LeaveRequest", "CONTRACT-": "Contract", "SE-": "StockEntry", "PRJ-": "Project"}
    doctype = next((d for p, d in prefix_map.items() if body.name.startswith(p)), None)
    if not doctype:
        raise HTTPException(400, f"无法识别单据类型: {body.name}")

    # ── 预算控制（ExpenseClaim 提交时校验是否超预算）──
    if body.action == "submit" and doctype == "ExpenseClaim":
        _enforce_budget(db, body.name)

    # ── 多级审批规则（仅 ExpenseClaim 支持）───────────────────
    # 部门专用规则优先（dept_id DESC → NULL 排最后）；同一部门按 level 升序
    user = db.query(User).filter_by(username=current_user.username).first()
    user_dept = getattr(user, "department_id", None) if user else None
    dept_filter = (
        or_(ApprovalRule.department_id == user_dept, ApprovalRule.department_id.is_(None))
        if user_dept
        else True
    )
    rules = (
        db.query(ApprovalRule)
          .filter_by(doctype=doctype)
          .filter(dept_filter)
          .order_by(
              ApprovalRule.department_id.desc(),   # 非 NULL（部门专用）排前面，NULL（全局）兜底
              ApprovalRule.level.asc(),
          )
          .all()
    )
    if rules and doctype == "ExpenseClaim":
        return _do_multilevel_action(body, current_user, db, doctype, rules)

    # ── 权限控制：提交（submit）任何登录用户可做；审批类动作仅限管理员 ──
    APPROVAL_ONLY = ("approve", "reject", "pay", "order", "receive")
    if body.action in APPROVAL_ONLY and current_user.role not in ("admin", "api"):
        raise HTTPException(
            403,
            f"审批动作「{body.action}」需要管理员权限（当前角色: {current_user.role}）",
        )

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

    pk = "id" if doctype == "LeaveRequest" else "name"
    db.execute(
        text(f"UPDATE {tbl} SET {col} = :v, modified = :m WHERE {pk} = :pk"),
        {"v": new_val, "m": datetime.utcnow(), "pk": body.name}
    )
    # 写入审批历史
    db.add(WorkflowHistory(
        doc_name=body.name,
        doctype=doctype,
        action=body.action,
        from_status=current,
        to_status=matched["to"],
        comment=body.comment,
        operator=current_user.username,
        field_changes=json.dumps({"status": {"from": current, "to": matched["to"]}}),
    ))

    # ── 审批通知 ───────────────────────────────────────────────
    # 通知审批人（固定发给 admin）
    ACTION_LABELS = {
        "submit":  "提交了",
        "approve": "批准了",
        "reject":  "拒绝了",
        "pay":     "确认付款",
        "order":   "确认订购",
        "receive": "确认收货",
    }
    _actor = ACTION_LABELS.get(body.action, body.action)
    if body.action in ("submit",):
        notify(db,
            recipient="admin",
            title=f"【{doctype}】{body.name} 已提交待审批",
            body=f"{_actor} {body.name}，请及时审批处理。",
            ntype="approval_request",
            doctype=doctype, doc_name=body.name, action=body.action,
            priority="urgent",
        )
    elif body.action in ("approve", "reject", "pay", "order", "receive"):
        notify(db,
            recipient="admin",
            title=f"【{doctype}】{body.name} 已{_actor}",
            body=f"审批动作「{_actor}」已完成，单据：{body.name}。",
            ntype="approval_result",
            doctype=doctype, doc_name=body.name, action=body.action,
            priority="normal",
        )

    if matched["to"] == "Approved" and doctype == "ExpenseClaim":
        _consume_budget(db, doctype, body.name)

    # StockEntry 审批通过后更新库存台账和余额
    if matched["to"] == "Approved" and doctype == "StockEntry":
        _post_stock_ledger(db, body.name)

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


def _do_multilevel_action(body, current_user, db, doctype, rules):
    """多级审批引擎：提交后逐级审批，末级通过方为 Approved。
    状态序列：Draft → Submitted → Pending-L2 → ... → Pending-LN → Approved / Rejected
    """
    current = _get_status(doctype, body.name, db)
    max_level = len(rules)
    if body.action == "submit":
        if current != "Draft":
            raise HTTPException(400, f"动作 'submit' 不适用于当前状态 '{current}'（{doctype}）")
        new_status = "Submitted"
    elif body.action == "approve":
        if current == "Submitted":
            level = 1
        elif current.startswith("Pending-L"):
            level = int(current.split("-L")[1])
        else:
            raise HTTPException(400, f"动作 'approve' 不适用于当前状态 '{current}'（{doctype}）")
        rule = rules[level - 1]
        if current_user.role not in (rule.approver_role, "admin", "api"):
            if not _is_delegate_for_role(db, current_user.username, rule.approver_role, doctype):
                raise HTTPException(
                    403,
                    f"第 {level} 级审批需要角色 '{rule.approver_role}'（当前角色: {current_user.role}）",
                )
        new_status = "Approved" if level >= max_level else f"Pending-L{level + 1}"
    elif body.action == "reject":
        new_status = "Rejected"
    else:
        raise HTTPException(400, f"动作 '{body.action}' 不支持多级审批")

    tbl = TABLE_MAP[doctype]
    col = STATUS_COL[doctype]
    pk = "id" if doctype == "LeaveRequest" else "name"
    db.execute(
        text(f"UPDATE {tbl} SET {col} = :v, modified = :m WHERE {pk} = :pk"),
        {"v": new_status, "m": datetime.utcnow(), "pk": body.name},
    )
    db.add(WorkflowHistory(
        doc_name=body.name, doctype=doctype, action=body.action,
        from_status=current, to_status=new_status, comment=body.comment,
        operator=current_user.username,
        field_changes=json.dumps({"status": {"from": current, "to": new_status}}),
    ))
    ACTION_LABELS = {
        "submit": "提交了", "approve": "批准了", "reject": "拒绝了",
        "pay": "确认付款", "order": "确认订购", "receive": "确认收货",
    }
    _actor = ACTION_LABELS.get(body.action, body.action)
    if body.action == "submit":
        notify(db, recipient="admin",
                title=f"【{doctype}】{body.name} 已提交待审批",
                body=f"{_actor} {body.name}，请及时审批处理。",
                ntype="approval_request", doctype=doctype, doc_name=body.name,
                action=body.action, priority="urgent")
    elif body.action in ("approve", "reject"):
        notify(db, recipient="admin",
                title=f"【{doctype}】{body.name} 已{_actor}",
                body=f"审批动作「{_actor}」已完成，单据：{body.name}。",
                ntype="approval_result", doctype=doctype, doc_name=body.name,
                action=body.action, priority="normal")
    if new_status == "Approved" and doctype == "ExpenseClaim":
        _consume_budget(db, doctype, body.name)
    db.commit()
    return {
        "ok": True, "name": body.name, "doctype": doctype,
        "action_label": body.action, "from": current, "to": new_status,
        "comment": body.comment, "multilevel": True, "level": max_level,
    }


def _is_delegate_for_role(db, delegate_username: str, target_role: str, doctype: str) -> bool:
    """判断 delegate_username 是否是具有 target_role 的某用户的生效代理人（可限定 doctype）"""
    now = datetime.utcnow()
    dels = db.query(Delegation).filter_by(delegate=delegate_username).all()
    for d in dels:
        if d.doctype and d.doctype != doctype:
            continue
        if d.start_date and d.start_date > now:
            continue
        if d.end_date and d.end_date < now:
            continue
        grantor = db.query(User).filter_by(username=d.grantor).first()
        if grantor and grantor.role == target_role:
            return True
    return False


def _enforce_budget(db, name: str):
    """提交 ExpenseClaim 时校验是否超出月度预算（支持部门级预算，兜底全局）"""
    exp = db.query(ExpenseClaim).filter_by(name=name).first()
    if not exp or not exp.claim_amount:
        return
    period = datetime.utcnow().strftime("%Y-%m")
    emp = db.query(User).filter_by(username=exp.employee).first()
    dept_id = getattr(emp, "department_id", None) if emp else None
    budget = budget_for(db, "ExpenseClaim", period, dept_id)
    if budget and budget.limit_amount is not None:
        remaining = budget.limit_amount - (budget.used_amount or 0)
        if exp.claim_amount > remaining:
            raise HTTPException(
                400,
                f"超出月度预算：单据金额 {exp.claim_amount}，剩余预算 {remaining:.2f}",
            )


def _consume_budget(db, doctype: str, name: str):
    """审批通过后扣减预算（支持部门级预算，兜底全局）"""
    if doctype != "ExpenseClaim":
        return
    exp = db.query(ExpenseClaim).filter_by(name=name).first()
    if not exp or not exp.claim_amount:
        return
    period = datetime.utcnow().strftime("%Y-%m")
    emp = db.query(User).filter_by(username=exp.employee).first()
    dept_id = getattr(emp, "department_id", None) if emp else None
    budget = budget_for(db, "ExpenseClaim", period, dept_id)
    if budget:
        budget.used_amount = (budget.used_amount or 0) + exp.claim_amount


# ── GET /api/workflow/doc/{doctype}/{name} ─────────────────────
@router.get("/doc/{doctype}/{name}")
def get_doc_workflow(
    doctype: str, name: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    if doctype not in TABLE_MAP:
        raise HTTPException(400, f"不支持: {doctype}")

    tbl = TABLE_MAP[doctype]
    pk = "id" if doctype == "LeaveRequest" else "name"
    row = db.execute(text(f"SELECT * FROM {tbl} WHERE {pk}=:pk"), {"pk": name}).fetchone()
    if not row:
        raise HTTPException(404, f"单据不存在: {name}")

    # 列名从 model 元数据读取，MariaDB/SQLite 通用
    model_cls = {"ExpenseClaim": ExpenseClaim, "PurchaseOrder": PurchaseOrder, "JournalEntry": JournalEntry, "LeaveRequest": LeaveRequest}[doctype]
    cols = [c.name for c in model_cls.__table__.columns]
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
def workflow_stats(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
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


# ── GET /api/workflow/notifications ──────────────────────────────
@router.get("/notifications")
def get_notifications(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    recipient: str = "admin",
    unread_only: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(Notification).filter(Notification.recipient == recipient)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    rows = q.order_by(Notification.id.desc()).limit(50).all()
    unread_count = db.query(Notification).filter(
        Notification.recipient == recipient,
        Notification.is_read == False,
    ).count()
    return {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "body": r.body,
                "ntype": r.ntype,
                "doctype": r.doctype,
                "doc_name": r.doc_name,
                "action": r.action,
                "priority": r.priority,
                "is_read": r.is_read,
                "created": str(r.creation) if r.creation else None,
            }
            for r in rows
        ],
        "unread_count": unread_count,
    }


# ── POST /api/workflow/notifications/{id}/read ─────────────────
@router.post("/notifications/{id}/read")
def mark_notification_read(
    id: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    n = db.query(Notification).filter(Notification.id == id).first()
    if not n:
        raise HTTPException(404, "通知不存在")
    n.is_read = True
    db.commit()
    return {"ok": True}


# ── POST /api/workflow/notifications/read-all ─────────────────
@router.post("/notifications/read-all")
def mark_all_read(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    recipient: str = "admin",
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(
        Notification.recipient == recipient,
        Notification.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"ok": True}


# ── GET /api/workflow/history/{doctype}/{name} ─────────────────
@router.get("/history/{doctype}/{name}")
def get_workflow_history(
    doctype: str, name: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """返回指定单据的审批历史记录"""
    if doctype not in TABLE_MAP:
        raise HTTPException(400, f"不支持的 doctype: {doctype}")
    
    rows = db.query(WorkflowHistory).filter(
        WorkflowHistory.doc_name == name,
        WorkflowHistory.doctype == doctype
    ).order_by(WorkflowHistory.id.desc()).all()
    
    return [{
        "id": r.id,
        "action": r.action,
        "from_status": r.from_status,
        "to_status": r.to_status,
        "comment": r.comment,
        "operator": r.operator,
        "field_changes": r.field_changes,
        "created_at": r.creation.isoformat() if r.creation else None,
        "created": str(r.creation) if r.creation else None,
    } for r in rows]
