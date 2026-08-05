"""routers/procurement.py — 采购（SQLAlchemy）"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db, Supplier, PurchaseOrder
from pydantic import BaseModel
from typing import Annotated, Optional
import json, re
from routers.auth import require_auth, CurrentUser
from routers._db import model_to_dict, seq_for, register as _reg

router = APIRouter(prefix="/api/resource", tags=["Procurement"])

_reg("Supplier", Supplier, "SUP")
_reg("Purchase Order", PurchaseOrder, "PO")


def md(m) -> dict: return model_to_dict(m)

class R(BaseModel):
    data: Optional[dict | list] = None
    message: Optional[str] = None

def _upsert(cls, name, data, db, update=True):
    m = db.query(cls).filter(cls.name == name).first() if update else None
    if not m:
        m = cls(name=name); db.add(m)
    for k, v in data.items():
        if k not in ("name",) and hasattr(m, k): setattr(m, k, v)
    return m

# ── Supplier ──────────────────────────────────────────────────
@router.get("/Supplier", response_model=R)
def list_suppliers(db: Session = Depends(get_db), limit=100, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(Supplier).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Supplier", response_model=R)
def create_supplier(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    name = data.get("name") or seq_for("Supplier", db)
    m = _upsert(Supplier, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Supplier created")

@router.get("/Supplier/{name}", response_model=R)
def get_supplier(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Supplier).filter(Supplier.name == name).first()
    if not m: raise HTTPException(404, "Supplier not found")
    return R(data=md(m))

@router.put("/Supplier/{name}", response_model=R)
def update_supplier(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = _upsert(Supplier, name, data, db); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Supplier updated")

@router.delete("/Supplier/{name}", response_model=R)
def delete_supplier(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Supplier).filter(Supplier.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Supplier deleted")

# ── Purchase Order ────────────────────────────────────────────
@router.get("/Purchase Order", response_model=R)
def list_pos(db: Session = Depends(get_db), limit=100, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(PurchaseOrder).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Purchase Order", response_model=R)
def create_po(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    raw = data.get("items", [])
    # 支持字符串（单行描述）或数组（明细列表）
    if isinstance(raw, str):
        items = []
        total = round(float(data.get("total") or 0), 2)
    else:
        items = raw
        total = round(sum(float(it.get("qty", 0)) * float(it.get("rate", 0)) for it in items), 2)
    name = data.get("name") or seq_for("Purchase Order", db)
    m = PurchaseOrder(name=name, supplier=data.get("supplier",""), total=total,
                      items_json=json.dumps(items), status=data.get("status","Draft"),
                      terms=data.get("terms"))
    db.add(m); db.commit(); db.refresh(m)
    return R(data={"name": m.name, "total": m.total}, message="Purchase Order created")

@router.get("/Purchase Order/{name}", response_model=R)
def get_po(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(PurchaseOrder).filter(PurchaseOrder.name == name).first()
    if not m: raise HTTPException(404, "Purchase Order not found")
    return R(data=md(m))

@router.put("/Purchase Order/{name}", response_model=R)
def update_po(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(PurchaseOrder).filter(PurchaseOrder.name == name).first()
    if not m: raise HTTPException(404, "Purchase Order not found")
    for k, v in data.items():
        if k == "items": setattr(m, "items_json", json.dumps(v))
        elif k not in ("name",) and hasattr(m, k): setattr(m, k, v)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Purchase Order updated")

@router.delete("/Purchase Order/{name}", response_model=R)
def delete_po(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(PurchaseOrder).filter(PurchaseOrder.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Purchase Order deleted")

# ── AI: 采购咨询 ──────────────────────────────────────────────
class POConsultRequest(BaseModel):
    supplier: str = ""
    amount: float = 0
    items: str = ""
    description: str = ""

@router.post("/ai/po_consult")
def ai_po_consult(req: POConsultRequest, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    risk_flags, suggestions = [], []
    score = 80
    if req.amount > 500000:
        risk_flags.append("单笔金额超过50万，需审批流升级"); score = 55
    elif req.amount > 100000:
        suggestions.append("建议要求3家供应商比价"); score = min(score, 65)
    elif req.amount < 10000:
        suggestions.append("建议走快速采购通道（单据直批）"); score = 90
    if not req.supplier: risk_flags.append("缺少供应商信息")
    text = (req.items + req.description).lower()
    if re.search(r"独家|唯一|指定", text):
        risk_flags.append("存在指定/独家供货，需说明合理性")
    if re.search(r"预付|全款|订金", text) and req.amount > 50000:
        risk_flags.append("大额预付款，建议分期支付并约定违约条款")
    return {
        "advice": f"采购金额 {req.amount:.2f} 元，供应商：{req.supplier or '未指定'}",
        "risk_flags": risk_flags,
        "suggestions": suggestions or ["采购要素完整，可正常推进"],
        "score": score,
    }
