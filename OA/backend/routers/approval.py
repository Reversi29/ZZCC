"""approval.py — 审批规则配置（多级审批链的 CRUD，仅管理员）"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, ApprovalRule
from routers.auth import require_admin, CurrentUser

router = APIRouter(prefix="/api/approval-rules", tags=["审批规则"])


class RuleIn(BaseModel):
    doctype: str
    level: int
    approver_role: str = "admin"
    condition_json: str | None = None


@router.post("", status_code=201)
def create_rule(
    body: RuleIn,
    current_user: Annotated[CurrentUser, Depends(require_admin)] = None,
    db: Session = Depends(get_db),
):
    """新增一条审批规则（某 doctype 的第 N 级审批人角色）"""
    if body.level < 1:
        raise HTTPException(400, "level 必须 >= 1")
    db.add(ApprovalRule(
        doctype=body.doctype,
        level=body.level,
        approver_role=body.approver_role,
        condition_json=body.condition_json,
    ))
    db.commit()
    return {"ok": True, "doctype": body.doctype, "level": body.level}


@router.get("")
def list_rules(
    doctype: str | None = Query(None),
    current_user: Annotated[CurrentUser, Depends(require_admin)] = None,
    db: Session = Depends(get_db),
):
    """列出审批规则（可按 doctype 过滤）"""
    q = db.query(ApprovalRule)
    if doctype:
        q = q.filter_by(doctype=doctype)
    rows = q.order_by(ApprovalRule.doctype, ApprovalRule.level).all()
    return [{
        "id": r.id,
        "doctype": r.doctype,
        "level": r.level,
        "approver_role": r.approver_role,
        "condition_json": r.condition_json,
    } for r in rows]


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    current_user: Annotated[CurrentUser, Depends(require_admin)] = None,
    db: Session = Depends(get_db),
):
    """删除一条审批规则"""
    r = db.query(ApprovalRule).filter_by(id=rule_id).first()
    if not r:
        raise HTTPException(404, "规则不存在")
    db.delete(r)
    db.commit()
    return {"ok": True}
