"""routers/stock.py — 库存/资产行政（SQLAlchemy）"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db, Item, StockEntry, Asset
from pydantic import BaseModel
from typing import Annotated, Optional
import json
from routers.auth import require_auth, CurrentUser
from routers._db import model_to_dict, seq_for, register as _reg

router = APIRouter(prefix="/api/resource", tags=["Stock / Asset"])

_reg("Item", Item, "ITEM")
_reg("Stock Entry", StockEntry, "SE")
_reg("Asset", Asset, "AST")


def md(m) -> dict: return model_to_dict(m)
class R(BaseModel):
    data: Optional[dict | list] = None; message: Optional[str] = None

def _upsert(cls, name, data, db, update=True):
    m = db.query(cls).filter(cls.name == name).first() if update else None
    if not m: m = cls(name=name); db.add(m)
    for k, v in data.items():
        if k not in ("name",) and hasattr(m, k): setattr(m, k, v)
    return m

# ── Item ──────────────────────────────────────────────────────
@router.get("/Item", response_model=R)
def list_items(db: Session = Depends(get_db), limit=100, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(Item).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Item", response_model=R)
def create_item(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    name = data.get("name") or data.get("item_code") or seq_for("Item", db)
    m = _upsert(Item, name, data, db, update=False)
    if "reorder_levels" in data:
        setattr(m, "reorder_levels_json", json.dumps(data["reorder_levels"]))
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Item created")

@router.get("/Item/{name}", response_model=R)
def get_item(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Item).filter(Item.name == name).first()
    if not m: raise HTTPException(404, "Item not found")
    return R(data=md(m))

@router.put("/Item/{name}", response_model=R)
def update_item(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Item).filter(Item.name == name).first()
    if not m: raise HTTPException(404, "Item not found")
    for k, v in data.items():
        if k == "reorder_levels": setattr(m, "reorder_levels_json", json.dumps(v))
        elif k not in ("name",) and hasattr(m, k): setattr(m, k, v)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Item updated")

@router.delete("/Item/{name}", response_model=R)
def delete_item(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Item).filter(Item.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Item deleted")

# ── Stock Entry ───────────────────────────────────────────────
@router.get("/Stock Entry", response_model=R)
def list_stock_entries(db: Session = Depends(get_db), limit=100, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(StockEntry).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Stock Entry", response_model=R)
def create_stock_entry(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    name = data.get("name") or seq_for("Stock Entry", db)
    m = StockEntry(name=name, stock_entry_type=data.get("stock_entry_type","Material Receipt"),
                   from_warehouse=data.get("from_warehouse"), to_warehouse=data.get("to_warehouse"),
                   items_json=json.dumps(data.get("items",[])))
    db.add(m); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Stock Entry created")

@router.get("/Stock Entry/{name}", response_model=R)
def get_stock_entry(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(StockEntry).filter(StockEntry.name == name).first()
    if not m: raise HTTPException(404, "Stock Entry not found")
    return R(data=md(m))

@router.put("/Stock Entry/{name}", response_model=R)
def update_stock_entry(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(StockEntry).filter(StockEntry.name == name).first()
    if not m: raise HTTPException(404, "Stock Entry not found")
    for k, v in data.items():
        if k == "items": setattr(m, "items_json", json.dumps(v))
        elif k not in ("name",) and hasattr(m, k): setattr(m, k, v)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Stock Entry updated")

@router.delete("/Stock Entry/{name}", response_model=R)
def delete_stock_entry(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(StockEntry).filter(StockEntry.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Stock Entry deleted")

# ── Asset ─────────────────────────────────────────────────────
@router.get("/Asset", response_model=R)
def list_assets(db: Session = Depends(get_db), limit=100, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(Asset).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Asset", response_model=R)
def create_asset(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    if (data.get("purchase_value") or 0) < 0: raise HTTPException(400, "资产原值不能为负")
    name = data.get("name") or data.get("asset_name") or seq_for("Asset", db)
    m = _upsert(Asset, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Asset created")

@router.get("/Asset/{name}", response_model=R)
def get_asset(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Asset).filter(Asset.name == name).first()
    if not m: raise HTTPException(404, "Asset not found")
    return R(data=md(m))

@router.put("/Asset/{name}", response_model=R)
def update_asset(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = _upsert(Asset, name, data, db); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Asset updated")

@router.delete("/Asset/{name}", response_model=R)
def delete_asset(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Asset).filter(Asset.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Asset deleted")

# ── 库存汇总 / 低库存预警 ─────────────────────────────────────
@router.get("/stock_summary")
def stock_summary(db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    rows, total = [], 0.0
    for it in db.query(Item).all():
        qty = float(it.opening_stock or 0); rate = float(it.val_rate or 0)
        val = round(qty * rate, 2); total += val
        rows.append({"item_code": it.item_code or it.name, "item_name": it.item_name or it.name,
                     "qty": qty, "val_rate": rate, "value": val})
    return {
        "items": rows, "item_count": len(rows),
        "total_stock_value": round(total, 2),
        "stock_entry_count": db.query(StockEntry).count(),
        "asset_count": db.query(Asset).count(),
    }

@router.get("/low_stock")
def low_stock(db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    warnings = []
    for it in db.query(Item).all():
        qty = float(it.opening_stock or 0)
        levels = json.loads(it.reorder_levels_json or "[]")
        threshold = float(levels[0].get("warehouse_reorder_level", 0)) if levels else 0
        if qty <= threshold:
            warnings.append({
                "item_code": it.item_code or it.name,
                "item_name": it.item_name or it.name,
                "qty": qty, "reorder_level": threshold,
                "severity": "critical" if qty == 0 else "warning",
            })
    return {"warnings": warnings, "count": len(warnings)}
