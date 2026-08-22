"""routers/compliance.py — 法务合规（SQLAlchemy）"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db, Contract
from pydantic import BaseModel
from typing import Annotated, Optional
from routers.auth import require_auth, CurrentUser
from routers._db import model_to_dict, seq_for, register as _reg

router = APIRouter(prefix="/api/resource", tags=["Compliance"])
_reg("Contract", Contract, "CONTRACT")


def md(m) -> dict: return model_to_dict(m)
class R(BaseModel):
    data: Optional[dict | list] = None; message: Optional[str] = None

def _upsert(cls, name, data, db, update=True):
    from datetime import date as _date
    import json as _json
    m = db.query(cls).filter(cls.name == name).first() if update else None
    if not m: m = cls(name=name); db.add(m)
    for k, v in data.items():
        if k not in ("name",) and hasattr(m, k):
            if isinstance(v, str) and k.endswith("_date") and v:
                try: v = _date.fromisoformat(v)
                except: pass
            elif isinstance(v, (dict, list)):
                v = _json.dumps(v, ensure_ascii=False)
            setattr(m, k, v)
    return m

@router.get("/Contract", response_model=R)
def list_contracts(db: Session = Depends(get_db), limit=100, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(Contract).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Contract", response_model=R)
def create_contract(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    name = data.get("name") or seq_for("Contract", db)
    data = dict(data); data["status"] = "Draft"  # 新合同默认草稿，走审批流
    m = _upsert(Contract, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Contract created")

@router.get("/Contract/{name}", response_model=R)
def get_contract(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Contract).filter(Contract.name == name).first()
    if not m: raise HTTPException(404, "Contract not found")
    return R(data=md(m))

@router.put("/Contract/{name}", response_model=R)
def update_contract(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = _upsert(Contract, name, data, db); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Contract updated")

@router.delete("/Contract/{name}", response_model=R)
def delete_contract(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Contract).filter(Contract.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Contract deleted")
