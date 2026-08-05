"""routers/customer_service.py — 客服工单（SQLAlchemy）"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db, SupportTicket
from pydantic import BaseModel
from typing import Annotated, Optional
from routers.auth import require_auth, CurrentUser
from routers._db import model_to_dict, seq_for, register as _reg

router = APIRouter(prefix="/api/resource", tags=["Customer Service"])
_reg("Support Ticket", SupportTicket, "TKT")


def md(m) -> dict: return model_to_dict(m)
class R(BaseModel):
    data: Optional[dict | list] = None; message: Optional[str] = None

def _upsert(cls, name, data, db, update=True):
    m = db.query(cls).filter(cls.name == name).first() if update else None
    if not m: m = cls(name=name); db.add(m)
    for k, v in data.items():
        if k not in ("name",) and hasattr(m, k): setattr(m, k, v)
    return m

@router.get("/Support Ticket", response_model=R)
def list_tickets(db: Session = Depends(get_db), limit=100, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(SupportTicket).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Support Ticket", response_model=R)
def create_ticket(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    name = data.get("name") or seq_for("Support Ticket", db)
    m = _upsert(SupportTicket, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Support Ticket created")

@router.get("/Support Ticket/{name}", response_model=R)
def get_ticket(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(SupportTicket).filter(SupportTicket.name == name).first()
    if not m: raise HTTPException(404, "Support Ticket not found")
    return R(data=md(m))

@router.put("/Support Ticket/{name}", response_model=R)
def update_ticket(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = _upsert(SupportTicket, name, data, db); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Support Ticket updated")

@router.delete("/Support Ticket/{name}", response_model=R)
def delete_ticket(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(SupportTicket).filter(SupportTicket.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Support Ticket deleted")
