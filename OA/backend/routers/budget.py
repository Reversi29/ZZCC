"""routers/budget.py — 预算 CRUD"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, Budget, User
from pydantic import BaseModel
from typing import Optional
from routers.auth import require_auth, CurrentUser
from routers._db import model_to_dict

router = APIRouter(prefix="/api/resource", tags=["Budget"])

def md(m): return model_to_dict(m)
class R(BaseModel):
    data: Optional[dict | list] = None; message: Optional[str] = None

@router.get("/Budget", response_model=R)
def list_budgets(db: Session = Depends(get_db), doctype: Optional[str] = None, period: Optional[str] = None, department_id: Optional[str] = None, limit: int = 200, current_user: CurrentUser = Depends(require_auth)):
    q = db.query(Budget)
    if doctype: q = q.filter_by(doctype=doctype)
    if period: q = q.filter_by(period=period)
    if department_id: q = q.filter_by(department_id=department_id)
    rows = q.order_by(Budget.id.desc()).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Budget", response_model=R)
def create_budget(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    # admin only
    if current_user.role not in ('admin','api'):
        raise HTTPException(403, '只有管理员可创建预算')
    m = Budget(**{k: v for k, v in data.items() if k in ('doctype','period','department_id','limit_amount','used_amount','note')})
    db.add(m); db.commit(); db.refresh(m)
    return R(data=md(m), message='Budget created')

@router.put("/Budget/{budget_id}", response_model=R)
def update_budget(budget_id: int, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    if current_user.role not in ('admin','api'):
        raise HTTPException(403, '只有管理员可修改预算')
    m = db.query(Budget).filter_by(id=budget_id).first()
    if not m: raise HTTPException(404, 'Budget not found')
    for k, v in data.items():
        if hasattr(m, k): setattr(m, k, v)
    db.commit(); db.refresh(m)
    return R(data=md(m), message='Budget updated')

@router.delete("/Budget/{budget_id}", response_model=R)
def delete_budget(budget_id: int, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    if current_user.role not in ('admin','api'):
        raise HTTPException(403, '只有管理员可删除预算')
    m = db.query(Budget).filter_by(id=budget_id).first()
    if not m: raise HTTPException(404, 'Budget not found')
    db.delete(m); db.commit()
    return R(message='Budget deleted')

@router.get("/Budget/summary", response_model=R)
def budget_summary(db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(Budget).all()
    # 按 doctype 汇总
    groups = {}
    for r in rows:
        key = r.doctype or 'ALL'
        if key not in groups:
            groups[key] = {'limit': 0, 'used': 0, 'count': 0, 'periods': set()}
        groups[key]['limit'] += (r.limit_amount or 0)
        groups[key]['used'] += (r.used_amount or 0)
        groups[key]['count'] += 1
        groups[key]['periods'].add(r.period or '')
    result = []
    for k, v in groups.items():
        pct = round(v['used']/v['limit']*100, 1) if v['limit'] else 0
        result.append({'doctype': k, 'limit': v['limit'], 'used': v['used'], 'remaining': v['limit']-v['used'],
                       'pct': pct, 'count': v['count'], 'periods': sorted(v['periods'])})
    return R(data=result)
