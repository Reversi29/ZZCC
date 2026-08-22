"""routers/approval_rules.py — 多级审批规则 CRUD"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db, ApprovalRule
from pydantic import BaseModel
from typing import Optional
from routers.auth import require_auth, CurrentUser
from routers._db import model_to_dict

router = APIRouter(prefix="/api/resource", tags=["ApprovalRule"])

def md(m): return model_to_dict(m)
class R(BaseModel):
    data: Optional[dict | list] = None; message: Optional[str] = None

@router.get("/ApprovalRule", response_model=R)
def list_rules(db: Session = Depends(get_db), doctype: Optional[str] = None, department_id: Optional[str] = None, limit: int = 200, current_user: CurrentUser = Depends(require_auth)):
    q = db.query(ApprovalRule)
    if doctype: q = q.filter_by(doctype=doctype)
    if department_id: q = q.filter_by(department_id=department_id)
    else: q = q.filter(or_(ApprovalRule.department_id == None, ApprovalRule.department_id.is_(None)))
    rows = q.order_by(ApprovalRule.doctype, ApprovalRule.level).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/ApprovalRule", response_model=R)
def create_rule(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    if current_user.role not in ('admin','api'):
        raise HTTPException(403, '只有管理员可配置审批规则')
    m = ApprovalRule(**{k: v for k, v in data.items() if k in ('doctype','department_id','level','approver_role','condition_json')})
    db.add(m); db.commit(); db.refresh(m)
    return R(data=md(m), message='ApprovalRule created')

@router.put("/ApprovalRule/{rule_id}", response_model=R)
def update_rule(rule_id: int, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    if current_user.role not in ('admin','api'):
        raise HTTPException(403, '只有管理员可修改审批规则')
    m = db.query(ApprovalRule).filter_by(id=rule_id).first()
    if not m: raise HTTPException(404, 'ApprovalRule not found')
    for k, v in data.items():
        if hasattr(m, k): setattr(m, k, v)
    db.commit(); db.refresh(m)
    return R(data=md(m), message='ApprovalRule updated')

@router.delete("/ApprovalRule/{rule_id}", response_model=R)
def delete_rule(rule_id: int, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    if current_user.role not in ('admin','api'):
        raise HTTPException(403, '只有管理员可删除审批规则')
    m = db.query(ApprovalRule).filter_by(id=rule_id).first()
    if not m: raise HTTPException(404, 'ApprovalRule not found')
    db.delete(m); db.commit()
    return R(message='ApprovalRule deleted')

@router.get("/ApprovalRule/by-doc", response_model=R)
def rules_by_doc(db: Session = Depends(get_db), doctype: str = None, department_id: Optional[str] = None, current_user: CurrentUser = Depends(require_auth)):
    if not doctype: raise HTTPException(400, 'doctype 必填')
    q = db.query(ApprovalRule).filter_by(doctype=doctype)
    if department_id:
        q = q.filter(or_(ApprovalRule.department_id == department_id, ApprovalRule.department_id.is_(None)))
    rows = q.order_by(ApprovalRule.level).all()
    return R(data=[md(r) for r in rows])
