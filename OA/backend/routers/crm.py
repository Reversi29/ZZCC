"""routers/crm.py — CRM 模块（SQLAlchemy）"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db, Lead, Contact, Opportunity
from routers.auth import require_auth, CurrentUser
from routers._db import register as _reg
from pydantic import BaseModel
from typing import Annotated, Optional
import json

router = APIRouter(prefix="/api/resource", tags=["CRM"])




def md(m) -> dict:
    """model_to_dict 简写"""
    from routers._db import model_to_dict
    return model_to_dict(m)


class R(BaseModel):
    data: Optional[dict | list] = None
    message: Optional[str] = None


# ── Lead ──────────────────────────────────────────────────────

_reg("Lead", Lead, "LEAD")
_reg("Contact", Contact, "CON")
_reg("Opportunity", Opportunity, "OPP")


@router.get("/Lead", response_model=R)
def list_leads(db: Session = Depends(get_db), limit: int = 100, current_user: CurrentUser = Depends(require_auth)):
    q = db.query(Lead)
    if current_user.role not in ("admin", "api"):
        q = q.filter(or_(Lead.owner == current_user.username, Lead.owner.is_(None)))
    rows = q.limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})


@router.post("/Lead", response_model=R)
def create_lead(lead: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    from routers._db import seq_for
    name = lead.get("name") or seq_for("Lead", db)
    m = Lead(name=name, owner=current_user.username)
    for k, v in lead.items():
        if k != "name" and hasattr(m, k):
            setattr(m, k, v)
    db.add(m); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Lead created")


@router.get("/Lead/{name}", response_model=R)
def get_lead(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Lead).filter(Lead.name == name).first()
    if not m:
        raise HTTPException(404, "Lead not found")
    return R(data=md(m))


@router.put("/Lead/{name}", response_model=R)
def update_lead(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Lead).filter(Lead.name == name).first()
    if not m:
        raise HTTPException(404, "Lead not found")
    for k, v in data.items():
        if k not in ("name",) and hasattr(m, k):
            setattr(m, k, v)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Lead updated")


@router.delete("/Lead/{name}", response_model=R)
def delete_lead(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Lead).filter(Lead.name == name).first()
    if m:
        db.delete(m); db.commit()
    return R(message="Lead deleted")


# ── Contact ───────────────────────────────────────────────────
@router.get("/Contact", response_model=R)
def list_contacts(db: Session = Depends(get_db), limit: int = 100, current_user: CurrentUser = Depends(require_auth)):
    q = db.query(Contact)
    if current_user.role not in ("admin", "api"):
        q = q.filter(or_(Contact.owner == current_user.username, Contact.owner.is_(None)))
    rows = q.limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})


@router.post("/Contact", response_model=R)
def create_contact(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    from routers._db import seq_for
    name = data.get("name") or seq_for("Contact", db)
    m = Contact(name=name, owner=current_user.username)
    for k, v in data.items():
        if k != "name" and hasattr(m, k):
            setattr(m, k, v)
    db.add(m); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Contact created")


@router.get("/Contact/{name}", response_model=R)
def get_contact(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Contact).filter(Contact.name == name).first()
    if not m:
        raise HTTPException(404, "Contact not found")
    return R(data=md(m))


@router.delete("/Contact/{name}", response_model=R)
def delete_contact(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Contact).filter(Contact.name == name).first()
    if m:
        db.delete(m); db.commit()
    return R(message="Contact deleted")


# ── Opportunity ───────────────────────────────────────────────
@router.get("/Opportunity", response_model=R)
def list_opportunities(db: Session = Depends(get_db), limit: int = 100, current_user: CurrentUser = Depends(require_auth)):
    q = db.query(Opportunity)
    if current_user.role not in ("admin", "api"):
        q = q.filter(or_(Opportunity.owner == current_user.username, Opportunity.owner.is_(None)))
    rows = q.limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})


@router.post("/Opportunity", response_model=R)
def create_opportunity(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    from routers._db import seq_for
    name = data.get("name") or seq_for("Opportunity", db)
    m = Opportunity(name=name, owner=current_user.username)
    for k, v in data.items():
        if k != "name" and hasattr(m, k):
            setattr(m, k, v)
    db.add(m); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Opportunity created")


@router.get("/Opportunity/{name}", response_model=R)
def get_opportunity(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Opportunity).filter(Opportunity.name == name).first()
    if not m:
        raise HTTPException(404, "Opportunity not found")
    return R(data=md(m))


@router.delete("/Opportunity/{name}", response_model=R)
def delete_opportunity(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Opportunity).filter(Opportunity.name == name).first()
    if m:
        db.delete(m); db.commit()
    return R(message="Opportunity deleted")
