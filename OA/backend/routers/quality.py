"""routers/quality.py — 质量测试（SQLAlchemy）"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db, QualityInspection
from pydantic import BaseModel
from typing import Annotated, Optional
from routers.auth import require_auth, CurrentUser
from routers._db import model_to_dict, seq_for, register as _reg

router = APIRouter(prefix="/api/resource", tags=["Quality"])
_reg("Quality Inspection", QualityInspection, "QI")


def md(m) -> dict: return model_to_dict(m)
class R(BaseModel):
    data: Optional[dict | list] = None; message: Optional[str] = None

def _parse_val(k, v):
    from datetime import date as _date
    import json as _json
    if isinstance(v, str) and k.endswith('_date') and v:
        try: return _date.fromisoformat(v)
        except: pass
    elif isinstance(v, (dict, list)):
        return _json.dumps(v, ensure_ascii=False)
    return v

def _upsert(cls, name, data, db, update=True):
    m = db.query(cls).filter(cls.name == name).first() if update else None
    if not m: m = cls(name=name); db.add(m)
    for k, v in data.items():
        if k not in ("name",) and hasattr(m, k): setattr(m, k, _parse_val(k, v))
    return m

@router.get("/Quality Inspection", response_model=R)
def list_inspections(db: Session = Depends(get_db), limit=100, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(QualityInspection).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Quality Inspection", response_model=R)
def create_inspection(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    name = data.get("name") or seq_for("Quality Inspection", db)
    m = _upsert(QualityInspection, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Quality Inspection created")

@router.get("/Quality Inspection/{name}", response_model=R)
def get_inspection(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(QualityInspection).filter(QualityInspection.name == name).first()
    if not m: raise HTTPException(404, "Quality Inspection not found")
    return R(data=md(m))

@router.put("/Quality Inspection/{name}", response_model=R)
def update_inspection(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = _upsert(QualityInspection, name, data, db); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Quality Inspection updated")

@router.delete("/Quality Inspection/{name}", response_model=R)
def delete_inspection(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(QualityInspection).filter(QualityInspection.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Quality Inspection deleted")
