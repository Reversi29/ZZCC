"""
services/auto_approval.py — AI 审批自动化引擎

核心流程：规则引擎评分 → LLM 辅助判断（可选） → 输出决策
  - auto: 自动批准（先执行，后审核）
  - manual: 标记待人工审核
  - reject: 自动拒绝

所有决策记录 operator='ai_agent'，可事后追溯。
"""
from __future__ import annotations

import json
import types
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import (
    get_db, WorkflowHistory, Notification,
    ExpenseClaim, LeaveRequest, StockEntry, JournalEntry,
    PurchaseOrder, ApprovalRule, Budget, User, Contract,
    StockLedger, StockBalance,
)


# ═══════════════════════════════════════════════
# 审批状态机（与 routers/workflow.py 保持一致）
# ═══════════════════════════════════════════════

TABLE_MAP = {
    "ExpenseClaim":  "expense_claims",
    "PurchaseOrder": "purchase_orders",
    "JournalEntry":  "journal_entries",
    "LeaveRequest":  "leave_requests",
    "Contract":      "contracts",
    "StockEntry":    "stock_entries",
    "Project":       "projects",
}

STATUS_COL = {
    "ExpenseClaim":  "approval_status",
    "PurchaseOrder": "status",
    "JournalEntry":  "docstatus",
    "LeaveRequest":  "status",
    "Contract":      "status",
    "StockEntry":    "status",
    "Project":       "status",
}

APPROVAL_ACTIONS = {
    "ExpenseClaim": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted"},
        {"action": "approve", "from": "Submitted", "to": "Approved"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected"},
        {"action": "pay",     "from": "Approved",  "to": "Paid"},
    ],
    "PurchaseOrder": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted"},
        {"action": "approve", "from": "Submitted", "to": "Approved"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected"},
        {"action": "order",   "from": "Approved",  "to": "Ordered"},
        {"action": "receive", "from": "Ordered",   "to": "Received"},
    ],
    "JournalEntry": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted"},
        {"action": "approve", "from": "Submitted", "to": "Approved"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected"},
    ],
    "LeaveRequest": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted"},
        {"action": "approve", "from": "Submitted", "to": "Approved"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected"},
    ],
    "Contract": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted"},
        {"action": "approve", "from": "Submitted", "to": "Approved"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected"},
    ],
    "StockEntry": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted"},
        {"action": "approve", "from": "Submitted", "to": "Approved"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected"},
    ],
    "Project": [
        {"action": "submit",  "from": "Draft",     "to": "Submitted"},
        {"action": "approve", "from": "Submitted", "to": "Approved"},
        {"action": "reject",  "from": "Submitted", "to": "Rejected"},
    ],
}

JE_TO_INT = {"Draft": 0, "Submitted": 1, "Approved": 2, "Rejected": 3}
JE_TO_STR = {v: k for k, v in JE_TO_INT.items()}


# ═══════════════════════════════════════════════
# 可配置审批阈值
# ═══════════════════════════════════════════════

@dataclass
class ApprovalThreshold:
    doctype: str
    auto_approve_amount: float = 0.0
    auto_approve_max_days: int = 0
    require_llm_review: bool = False
    risk_keywords: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_THRESHOLDS: list[dict] = [
    {
        "doctype": "ExpenseClaim",
        "auto_approve_amount": 1000.0,
        "auto_approve_max_days": 0,
        "require_llm_review": True,
        "risk_keywords": '["报销","虚假","个人消费","娱乐","私人"]',
        "notes": "小额报销（≤1000）自动通过；超阈值标记待审",
    },
    {
        "doctype": "LeaveRequest",
        "auto_approve_amount": 0,
        "auto_approve_max_days": 3,
        "require_llm_review": False,
        "risk_keywords": '["产假","病假超过7天"]',
        "notes": "≤3天假期自动通过",
    },
    {
        "doctype": "StockEntry",
        "auto_approve_amount": 5000.0,
        "auto_approve_max_days": 0,
        "require_llm_review": False,
        "risk_keywords": '["退货","报废"]',
        "notes": "小额出入库（≤5000）自动通过",
    },
    {
        "doctype": "PurchaseOrder",
        "auto_approve_amount": 10000.0,
        "auto_approve_max_days": 0,
        "require_llm_review": True,
        "risk_keywords": '["独家","紧急","加急"]',
        "notes": "小额采购（≤10000）自动通过；超阈值标记待审",
    },
    {
        "doctype": "JournalEntry",
        "auto_approve_amount": 5000.0,
        "auto_approve_max_days": 0,
        "require_llm_review": False,
        "risk_keywords": '["调整","冲销","异常"]',
        "notes": "小额日记账（≤5000）自动通过",
    },
]


# ═══════════════════════════════════════════════
# 阈值配置管理（持久化到 ApprovalRule 表）
# ═══════════════════════════════════════════════

def get_threshold(db: Session, doctype: str) -> ApprovalThreshold | None:
    """读取审批阈值；无配置时返回 None（降级全量人工审核）"""
    try:
        row = db.query(ApprovalRule).filter_by(
            doctype=doctype, approver_role="auto_approve"
        ).first()
        if not row:
            return None
        data = json.loads(row.condition_json) if row.condition_json else {}
        return ApprovalThreshold(
            doctype=row.doctype,
            auto_approve_amount=float(data.get("auto_approve_amount", 0)),
            auto_approve_max_days=int(data.get("auto_approve_max_days", 0) or 0),
            require_llm_review=bool(data.get("require_llm_review", False)),
            risk_keywords=data.get("risk_keywords", ""),
            notes=data.get("notes", ""),
        )
    except Exception:
        return None


def save_threshold(db: Session, threshold: ApprovalThreshold) -> None:
    existing = db.query(ApprovalRule).filter_by(
        doctype=threshold.doctype, approver_role="auto_approve"
    ).first()
    condition_data = json.dumps(threshold.to_dict())
    if existing:
        existing.level = threshold.auto_approve_max_days
        existing.condition_json = condition_data
    else:
        db.add(ApprovalRule(
            doctype=threshold.doctype,
            approver_role="auto_approve",
            level=threshold.auto_approve_max_days,
            condition_json=condition_data,
        ))
    db.commit()


def delete_threshold(db: Session, doctype: str) -> None:
    db.query(ApprovalRule).filter_by(
        doctype=doctype, approver_role="auto_approve"
    ).delete()
    db.commit()


def list_thresholds(db: Session) -> list[dict]:
    rows = db.query(ApprovalRule).filter_by(approver_role="auto_approve").all()
    results = []
    for r in rows:
        cjson = json.loads(r.condition_json) if r.condition_json else {}
        results.append({
            "doctype": r.doctype,
            "auto_approve_amount": float(cjson.get("auto_approve_amount", 0)),
            "auto_approve_max_days": int(cjson.get("auto_approve_max_days", 0) or 0),
            "notes": cjson.get("notes", ""),
        })
    # 补充没有数据库配置但属于默认阈值的 doctype
    existing_doctypes = {r["doctype"] for r in results}
    for default in DEFAULT_THRESHOLDS:
        if default["doctype"] not in existing_doctypes:
            results.append(default)
    return results


# ═══════════════════════════════════════════════
# LLM 客户端（可选）
# ═══════════════════════════════════════════════

try:
    from ai.services.llm_client import LLMClient
    _llm_available = True
except Exception:
    _llm_available = False


def _get_llm():
    if not _llm_available:
        return None
    client = LLMClient()
    if not client.openai_key:
        return None
    return client


# ═══════════════════════════════════════════════
# 核心审查函数
# ═══════════════════════════════════════════════

def review_document(db: Session, doctype: str, doc_name: str) -> dict:
    """
    对单个 Submitted 单据进行 AI 审批审查。
    """
    result = {
        "doctype": doctype,
        "doc_name": doc_name,
        "decision": "manual",
        "score": 0,
        "reason": "",
        "threshold": None,
        "llm_reviewed": False,
        "llm_result": None,
        "risk_flags": [],
        "title": "",
    }

    doc_data = _fetch_document(db, doctype, doc_name)
    if doc_data is None:
        result["decision"] = "reject"
        result["reason"] = f"文档不存在: {doctype} {doc_name}"
        return result

    current_status = _get_current_status(doctype, doc_data)
    if current_status != "Submitted":
        result["reason"] = f"当前状态为 {current_status}，不在待审队列"
        return result

    threshold = get_threshold(db, doctype)
    if threshold is None:
        result["reason"] = f"无 {doctype} 审批阈值配置，需人工审核"
        result["score"] = 50
        return result

    result["threshold"] = threshold.to_dict()

    # 设置 title
    if doctype == "ExpenseClaim":
        result["title"] = f"{doc_data.get('employee','')} - {doc_data.get('expense_type','')} - ¥{doc_data.get('claim_amount',0):,.0f}"
    elif doctype == "LeaveRequest":
        result["title"] = f"请假 {doc_data.get('leave_type','')} | {doc_data.get('start_date','')}~{doc_data.get('end_date','')}"
    elif doctype == "StockEntry":
        result["title"] = f"{doc_data.get('stock_entry_type','')} | {doc_name}"
    elif doctype == "PurchaseOrder":
        result["title"] = f"{doc_data.get('supplier','')} | ¥{doc_data.get('total',0):,.0f}"
    elif doctype == "JournalEntry":
        result["title"] = f"{doc_data.get('title','')} ({doc_data.get('posting_date','')})"
    elif doctype == "Contract":
        result["title"] = f"{doc_data.get('contract_name','')} | ¥{doc_data.get('contract_value',0):,.0f}"

    score, reason, risk_flags = _rule_engine_score(doctype, doc_data, threshold)
    result["score"] = score
    result["reason"] = reason
    result["risk_flags"] = risk_flags

    if threshold.require_llm_review:
        llm_result = _llm_review(doctype, doc_data, threshold, score)
        result["llm_reviewed"] = True
        result["llm_result"] = llm_result
        if llm_result:
            if llm_result.get("decision") == "reject":
                result["decision"] = "reject"
                result["reason"] = llm_result.get("reason", result["reason"])
                result["score"] = max(0, score - 30)
            elif llm_result.get("decision") == "approve" and score >= 60:
                result["score"] = min(100, score + 10)

    if result["decision"] != "reject":
        if score >= 80:
            result["decision"] = "auto"
            result["reason"] = f"规则评分 {score}/100，达到自动审批阈值"
        elif score >= 50:
            result["decision"] = "manual"
            result["reason"] = f"规则评分 {score}/100，建议人工审核"
        else:
            result["decision"] = "manual"
            result["reason"] = f"规则评分 {score}/100，风险较高，需人工审核"

    return result


# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════

def _fetch_document(db: Session, doctype: str, doc_name: str) -> dict | None:
    model_map = {
        "ExpenseClaim": ExpenseClaim,
        "LeaveRequest": LeaveRequest,
        "StockEntry": StockEntry,
        "JournalEntry": JournalEntry,
        "Contract": Contract,
        "PurchaseOrder": PurchaseOrder,
    }
    model = model_map.get(doctype)
    if not model:
        return None

    if doctype == "LeaveRequest":
        row = db.query(model).filter_by(id=doc_name).first()
    else:
        row = db.query(model).filter_by(name=doc_name).first()

    if not row:
        return None

    data = {}
    for col in model.__table__.columns:
        val = getattr(row, col.name, None)
        if isinstance(val, (date, datetime)):
            data[col.name] = str(val)
        else:
            data[col.name] = val
    return data


def _get_current_status(doctype: str, doc_data: dict) -> str:
    status_map = {
        "ExpenseClaim": "approval_status",
        "LeaveRequest": "status",
        "StockEntry": "status",
        "Contract": "status",
        "PurchaseOrder": "status",
    }
    col = status_map.get(doctype, "status")
    if doctype == "JournalEntry":
        raw = doc_data.get("docstatus")
        return JE_TO_STR.get(int(raw) if raw is not None else 0, "Draft")
    raw = doc_data.get(col)
    return str(raw) if raw else "Draft"


def _rule_engine_score(doctype: str, doc_data: dict, threshold: ApprovalThreshold) -> tuple[int, str, list[str]]:
    """规则引擎评分 → (score, reason, risk_flags)"""
    score = 50
    reasons = []
    risk_flags = []

    if doctype == "ExpenseClaim":
        amount = float(doc_data.get("claim_amount") or 0)
        purpose = str(doc_data.get("purpose") or "")
        employee = str(doc_data.get("employee") or "")

        if amount <= threshold.auto_approve_amount:
            score += 30
            reasons.append(f"金额 {amount} ≤ 阈值 {threshold.auto_approve_amount}")
        elif amount <= threshold.auto_approve_amount * 2:
            score += 10
            reasons.append(f"金额 {amount} 略超阈值")
        else:
            score -= 20
            reasons.append(f"金额 {amount} 远超阈值 {threshold.auto_approve_amount}")
            risk_flags.append(f"金额过高: {amount}")

        if purpose and len(purpose) > 5:
            score += 10
            reasons.append("用途描述完整")
        else:
            score -= 10
            risk_flags.append("用途描述缺失或过短")

        if employee:
            score += 5
        else:
            score -= 10
            risk_flags.append("缺少员工信息")

        if threshold.risk_keywords:
            try:
                keywords = json.loads(threshold.risk_keywords)
                for kw in keywords:
                    if kw.lower() in purpose.lower():
                        score -= 15
                        risk_flags.append(f"用途含风险关键词: {kw}")
            except Exception:
                pass

    elif doctype == "LeaveRequest":
        leave_type = str(doc_data.get("leave_type") or "")
        start_str = str(doc_data.get("start_date") or "")
        end_str = str(doc_data.get("end_date") or "")

        days = _calc_leave_days(start_str, end_str)
        if days is not None:
            if days <= threshold.auto_approve_max_days:
                score += 30
                reasons.append(f"请假 {days} 天 ≤ 阈值 {threshold.auto_approve_max_days} 天")
            elif days <= threshold.auto_approve_max_days * 3:
                score += 10
                reasons.append(f"请假 {days} 天略超阈值")
            else:
                score -= 20
                reasons.append(f"请假 {days} 天远超阈值")
                risk_flags.append(f"请假天数过长: {days}天")
        else:
            score -= 10
            risk_flags.append("无法计算请假天数")

        safe_types = {"年假", "事假", "调休", "Annual", "Casual", "Sick"}
        if leave_type in safe_types:
            score += 10
            reasons.append(f"假期类型常规: {leave_type}")

    elif doctype == "StockEntry":
        total_amount = 0.0
        items_json = doc_data.get("items_json")
        if items_json:
            try:
                items = json.loads(items_json)
                for item in items:
                    qty = float(item.get("qty") or item.get("quantity") or 0)
                    rate = float(item.get("rate") or item.get("valuation_rate") or 0)
                    total_amount += qty * rate
            except Exception:
                pass

        if total_amount <= threshold.auto_approve_amount:
            score += 30
            reasons.append(f"出入库金额 {total_amount} ≤ 阈值 {threshold.auto_approve_amount}")
        else:
            score -= 15
            risk_flags.append(f"出入库金额 {total_amount} 超阈值")

    elif doctype == "JournalEntry":
        title = str(doc_data.get("title") or "")
        score += 10
        reasons.append("日记账条目通常低风险")
        if "调整" in title or "冲销" in title:
            score -= 15
            risk_flags.append("调整/冲销分录需人工确认")

    elif doctype == "PurchaseOrder":
        total = float(doc_data.get("total") or 0)
        supplier = str(doc_data.get("supplier") or "")

        if total <= threshold.auto_approve_amount:
            score += 30
            reasons.append(f"采购金额 {total} ≤ 阈值 {threshold.auto_approve_amount}")
        else:
            score -= 15
            risk_flags.append(f"采购金额 {total} 超阈值")

        if supplier:
            score += 5
        else:
            score -= 10
            risk_flags.append("缺少供应商信息")

    elif doctype == "Contract":
        value = float(doc_data.get("contract_value") or 0)
        if value <= threshold.auto_approve_amount:
            score += 20
            reasons.append(f"合同金额 {value} ≤ 阈值")
        else:
            score -= 20
            risk_flags.append(f"合同金额 {value} 超阈值")
        score -= 10
        risk_flags.append("合同类单据建议人工审核")

    score = max(0, min(100, score))
    reason = "; ".join(reasons) if reasons else "规则引擎评分完成"
    if risk_flags:
        score = min(score, 49)
    return score, reason, risk_flags


def _calc_leave_days(start_str: str, end_str: str) -> int | None:
    try:
        start = datetime.strptime(start_str[:10], "%Y-%m-%d")
        end = datetime.strptime(end_str[:10], "%Y-%m-%d")
        return max(1, (end - start).days + 1)
    except Exception:
        return None


def _llm_review(doctype: str, doc_data: dict, threshold: ApprovalThreshold, rule_score: int) -> dict | None:
    llm = _get_llm()
    if llm is None:
        return None

    context_lines = [f"单据类型: {doctype}", f"规则引擎评分: {rule_score}/100"]
    for key, val in doc_data.items():
        if val is not None and str(val).strip():
            context_lines.append(f"{key}: {val}")

    context_text = "\n".join(context_lines)

    system_prompt = (
        "你是一个企业审批 AI 助手。审查待审批单据，判断是否应该自动批准。"
        "请严格输出 JSON，不要有其他内容。"
        "JSON: {\"decision\": \"approve\"|\"reject\"|\"manual\", \"reason\": \"原因\", \"confidence\": 0.0-1.0}"
    )

    user_prompt = (
        f"请审查以下单据，判断是否适合自动批准：\n\n"
        f"=== 单据信息 ===\n{context_text}\n\n"
        f"审查要点：信息是否完整合理？是否存在异常模式？是否符合常规业务逻辑？\n"
        f"如果规则引擎分数 >70 且你未发现明显异常，建议 approve。"
    )

    try:
        result = llm.chat_json(system_prompt, user_prompt)
        return {
            "decision": result.get("decision", "manual"),
            "reason": result.get("reason", ""),
            "confidence": result.get("confidence", 0.5),
        }
    except Exception as e:
        return {"decision": "manual", "reason": f"LLM 审查失败: {e}", "confidence": 0}


# ═══════════════════════════════════════════════
# 批量审查 + 自动执行
# ═══════════════════════════════════════════════

def _pending_rows(doctype: str, db: Session) -> list[dict]:
    """获取指定 doctype 所有 Submitted 状态的记录（本地实现，避免循环导入）"""
    tbl = TABLE_MAP.get(doctype)
    if not tbl:
        return []
    col = STATUS_COL.get(doctype, "status")
    if doctype == "JournalEntry":
        rows = db.execute(text(f"SELECT name FROM {tbl} WHERE docstatus = 1")).fetchall()
        return [{"name": r[0]} for r in rows]
    if doctype == "LeaveRequest":
        rows = db.execute(text(f"SELECT id FROM {tbl} WHERE {col} = 'Submitted'")).fetchall()
        return [{"name": str(r[0])} for r in rows]
    rows = db.execute(text(f"SELECT name FROM {tbl} WHERE {col} = 'Submitted'")).fetchall()
    return [{"name": r[0]} for r in rows]


def review_all_pending(db: Session) -> dict:
    all_recs = []
    for doctype in ["ExpenseClaim", "LeaveRequest", "StockEntry",
                    "JournalEntry", "PurchaseOrder", "Contract"]:
        for row in _pending_rows(doctype, db):
            rec = review_document(db, doctype, row["name"])
            all_recs.append(rec)

    summary = {
        "total": len(all_recs),
        "auto": sum(1 for r in all_recs if r["decision"] == "auto"),
        "manual": sum(1 for r in all_recs if r["decision"] == "manual"),
        "reject": sum(1 for r in all_recs if r["decision"] == "reject"),
    }
    return {"summary": summary, "recommendations": all_recs}


def _do_state_transition(db: Session, doctype: str, doc_name: str, action: str, comment: str) -> dict:
    """
    执行状态变更（AI Agent 专用，无需鉴权）。
    复用 workflow.py 的状态机逻辑，确保预算扣减、库存过账等副作用一致。
    """
    current = _get_current_status(doctype, _fetch_document(db, doctype, doc_name) or {})

    actions = APPROVAL_ACTIONS.get(doctype, [])
    matched = next((a for a in actions if a["action"] == action and a["from"] == current), None)
    if not matched:
        return {"ok": False, "error": f"动作 '{action}' 不适用于当前状态 '{current}'"}

    tbl = TABLE_MAP[doctype]
    col = STATUS_COL[doctype]
    new_val = matched["to"]
    if doctype == "JournalEntry":
        new_val = JE_TO_INT[new_val]

    pk = "id" if doctype == "LeaveRequest" else "name"
    db.execute(
        text(f"UPDATE {tbl} SET {col} = :v, modified = :m WHERE {pk} = :pk"),
        {"v": new_val, "m": datetime.utcnow(), "pk": doc_name},
    )

    db.add(WorkflowHistory(
        doc_name=doc_name, doctype=doctype,
        action=action, from_status=current, to_status=matched["to"],
        comment=comment, operator="ai_agent",
        field_changes=json.dumps({"status": {"from": current, "to": matched["to"]}}),
    ))

    # 通知
    _notify_approval(db, doctype, doc_name, action, comment)

    # 副作用：预算扣减（ExpenseClaim）
    if matched["to"] == "Approved" and doctype == "ExpenseClaim":
        _ai_consume_budget(db, doc_name)

    # 副作用：库存过账（StockEntry）
    if matched["to"] == "Approved" and doctype == "StockEntry":
        _ai_post_stock_ledger(db, doc_name)

    db.commit()
    return {
        "ok": True, "name": doc_name, "doctype": doctype,
        "action": action, "from": current, "to": matched["to"],
        "operator": "ai_agent",
    }


def _notify_approval(db: Session, doctype: str, doc_name: str, action: str, comment: str) -> None:
    labels = {"approve": "AI自动批准", "reject": "AI自动拒绝"}
    label = labels.get(action, action)
    db.add(Notification(
        recipient="admin",
        title=f"【AI审批】{doctype} {doc_name} 已{label}",
        body=f"AI Agent 自动执行「{label}」，原因：{comment}",
        ntype="approval_result",
        doctype=doctype, doc_name=doc_name, action=action,
        priority="normal",
    ))


def _ai_consume_budget(db: Session, name: str) -> None:
    """审批通过后扣减预算（复用 workflow.py 的 budget_for）"""
    from routers._org import budget_for

    exp = db.query(ExpenseClaim).filter_by(name=name).first()
    if not exp or not exp.claim_amount:
        return
    period = datetime.utcnow().strftime("%Y-%m")
    emp = db.query(User).filter_by(username=exp.employee).first()
    dept_id = getattr(emp, "department_id", None) if emp else None
    budget = budget_for(db, "ExpenseClaim", period, dept_id)
    if budget:
        budget.used_amount = (budget.used_amount or 0) + exp.claim_amount


def _ai_post_stock_ledger(db: Session, stock_entry_name: str) -> None:
    """StockEntry 审批通过后写入库存台账"""
    from datetime import date as _date

    entry = db.query(StockEntry).filter_by(name=stock_entry_name).first()
    if not entry:
        return
    try:
        items = json.loads(entry.items_json or "[]")
    except Exception:
        return
    if not items:
        return

    posting_date = entry.modified.date() if entry.modified else _date.today()
    warehouse = entry.to_warehouse or entry.from_warehouse or "Default"

    for item_row in items:
        item_code = item_row.get("item_code") or item_row.get("item")
        qty = float(item_row.get("qty") or item_row.get("quantity") or 0)
        rate = float(item_row.get("rate") or item_row.get("valuation_rate") or 0)
        if not item_code or qty == 0:
            continue

        if entry.stock_entry_type == "Material Issue":
            incoming, outgoing = 0.0, qty
        else:
            incoming, outgoing = qty, 0.0

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

        db.add(StockLedger(
            item_code=item_code, warehouse=warehouse,
            stock_entry_type=entry.stock_entry_type,
            stock_entry_name=entry.name,
            posting_date=posting_date,
            incoming_qty=incoming, outgoing_qty=outgoing,
            balance_qty=bal.actual_qty,
            valuation_rate=rate,
            stock_value=bal.actual_qty * rate,
            description=f"AI:{entry.stock_entry_type}: {entry.name}",
        ))


def execute_recommendation(db: Session, doctype: str, doc_name: str,
                           action: str, comment: str = "AI自动审批") -> dict:
    """执行单条 AI 审批决策"""
    if action not in ("approve", "reject", "flag"):
        return {"ok": False, "error": f"不支持的动作: {action}"}

    if action == "flag":
        db.add(WorkflowHistory(
            doc_name=doc_name, doctype=doctype,
            action="ai_flag", from_status="Submitted", to_status="Submitted",
            comment=comment, operator="ai_agent", field_changes="{}",
        ))
        db.commit()
        return {"ok": True, "action": "flag", "comment": comment}

    return _do_state_transition(db, doctype, doc_name, action, comment)


def batch_execute(db: Session, recommendations: list[dict]) -> dict:
    """批量执行审查建议"""
    executed, failed, skipped = [], [], []

    for rec in recommendations:
        decision = rec.get("decision")
        if decision == "auto":
            result = execute_recommendation(db, rec["doctype"], rec["doc_name"],
                                            "approve", rec.get("reason", "AI自动审批"))
            (executed if result.get("ok") else failed).append(result)
        elif decision == "reject":
            result = execute_recommendation(db, rec["doctype"], rec["doc_name"],
                                            "reject", rec.get("reason", "AI自动拒绝"))
            (executed if result.get("ok") else failed).append(result)
        else:
            skipped.append({"doc_name": rec["doc_name"], "doctype": rec["doctype"],
                            "reason": "需人工审核"})

    return {
        "summary": {"executed": len(executed), "failed": len(failed), "skipped": len(skipped)},
        "details": {"executed": executed, "failed": failed, "skipped": skipped},
    }
