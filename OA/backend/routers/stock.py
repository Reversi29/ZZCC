"""routers/stock.py — 库存/资产行政（SQLAlchemy）"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db, Item, StockEntry, Asset, Warehouse, StockLedger, StockBalance
from pydantic import BaseModel
from typing import Annotated, Optional
import json
from routers.auth import require_auth, CurrentUser
from routers._db import model_to_dict, seq_for, register as _reg

router = APIRouter(prefix="/api/resource", tags=["Stock / Asset"])

_reg("Item", Item, "ITEM")
_reg("Stock Entry", StockEntry, "SE")
_reg("Asset", Asset, "AST")
_reg("Warehouse", Warehouse, "WH")


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
    if "asset_name" not in data or not data.get("asset_name"):
        data["asset_name"] = data.get("name") or ""
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

# ── Warehouse ───────────────────────────────────────────────
@router.get("/Warehouse", response_model=R)
def list_warehouses(db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(Warehouse).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Warehouse", response_model=R)
def create_warehouse(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    name = data.get("name") or data.get("warehouse_name") or seq_for("Warehouse", db)
    m = Warehouse(name=name, warehouse_name=data.get("warehouse_name", name),
                  warehouse_type=data.get("warehouse_type", "Physical"),
                  address=data.get("address"), is_default=data.get("is_default", False),
                  status=data.get("status", "Active"),
                  department_id=data.get("department_id"))
    db.add(m); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Warehouse created")

@router.get("/Warehouse/{name}", response_model=R)
def get_warehouse(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Warehouse).filter(Warehouse.name == name).first()
    if not m: raise HTTPException(404, "Warehouse not found")
    return R(data=md(m))

@router.put("/Warehouse/{name}", response_model=R)
def update_warehouse(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Warehouse).filter(Warehouse.name == name).first()
    if not m: raise HTTPException(404, "Warehouse not found")
    for k, v in data.items():
        if k not in ("name",) and hasattr(m, k): setattr(m, k, v)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Warehouse updated")

@router.delete("/Warehouse/{name}", response_model=R)
def delete_warehouse(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Warehouse).filter(Warehouse.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Warehouse deleted")

# ── 库存汇总 / 低库存预警 ─────────────────────────────────────
@router.get("/stock_summary")
def stock_summary(db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    """实时库存余额（来自 StockBalance 台账汇总）"""
    rows, total = [], 0.0
    for bal in db.query(StockBalance).all():
        val = round(float(bal.actual_qty or 0) * float(bal.valuation_rate or 0), 2)
        total += val
        rows.append({
            "item_code": bal.item_code, "warehouse": bal.warehouse,
            "actual_qty": float(bal.actual_qty or 0),
            "reserved_qty": float(bal.reserved_qty or 0),
            "available_qty": float(bal.actual_qty or 0) - float(bal.reserved_qty or 0),
            "valuation_rate": float(bal.valuation_rate or 0),
            "stock_value": val,
            "last_updated": str(bal.last_updated) if bal.last_updated else None,
        })
    return {
        "items": rows, "item_count": len(rows),
        "total_stock_value": round(total, 2),
        "stock_entry_count": db.query(StockEntry).count(),
        "asset_count": db.query(Asset).count(),
        "warehouse_count": db.query(Warehouse).count(),
    }

@router.get("/low_stock")
def low_stock(db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    """基于 StockBalance 实时库存 + Item.reorder_level 的库存预警"""
    warnings = []
    items_map = {it.name: it for it in db.query(Item).all()}
    for bal in db.query(StockBalance).all():
        it = items_map.get(bal.item_code)
        threshold = float(it.reorder_level or 0) if it else 0
        actual = float(bal.actual_qty or 0)
        if actual <= threshold:
            warnings.append({
                "item_code": bal.item_code,
                "item_name": it.item_name if it else bal.item_code,
                "warehouse": bal.warehouse,
                "actual_qty": actual,
                "reorder_level": threshold,
                "severity": "critical" if actual == 0 else "warning",
            })
    return {"warnings": warnings, "count": len(warnings)}

# ── 库存台账 / 明细 ─────────────────────────────────────────
@router.get("/stock_ledger")
def stock_ledger(
    db: Session = Depends(get_db),
    item_code: str = None,
    warehouse: str = None,
    current_user: CurrentUser = Depends(require_auth),
):
    q = db.query(StockLedger)
    if item_code: q = q.filter(StockLedger.item_code == item_code)
    if warehouse: q = q.filter(StockLedger.warehouse == warehouse)
    rows = q.order_by(StockLedger.posting_date.desc(), StockLedger.id.desc()).limit(200).all()
    return {
        "entries": [{
            "id": r.id, "item_code": r.item_code, "warehouse": r.warehouse,
            "stock_entry_type": r.stock_entry_type,
            "posting_date": str(r.posting_date) if r.posting_date else None,
            "incoming_qty": float(r.incoming_qty or 0),
            "outgoing_qty": float(r.outgoing_qty or 0),
            "balance_qty": float(r.balance_qty or 0),
            "valuation_rate": float(r.valuation_rate or 0),
            "stock_value": float(r.stock_value or 0),
            "description": r.description,
        } for r in rows],
        "count": len(rows),
    }
