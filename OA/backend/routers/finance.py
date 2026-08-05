"""routers/finance.py — 财务（SQLAlchemy）"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db, Account, JournalEntry, PaymentEntry, ExpenseClaim
from pydantic import BaseModel
from typing import Annotated, Optional
import json, re
from routers.auth import require_auth, CurrentUser
from routers._db import model_to_dict, seq_for, register as _reg

router = APIRouter(prefix="/api/resource", tags=["Finance"])

_reg("Account", Account, "ACC")
_reg("Journal Entry", JournalEntry, "JE")
_reg("Payment Entry", PaymentEntry, "PE")
_reg("Expense Claim", ExpenseClaim, "EXP")


def md(m) -> dict: return model_to_dict(m)
class R(BaseModel):
    data: Optional[dict | list] = None
    message: Optional[str] = None

def _upsert(cls, name, data, db, update=True):
    m = db.query(cls).filter(cls.name == name).first() if update else None
    if not m: m = cls(name=name); db.add(m)
    for k, v in data.items():
        if k not in ("name",) and hasattr(m, k): setattr(m, k, v)
    return m

# ── Account ───────────────────────────────────────────────────
@router.get("/Account", response_model=R)
def list_accounts(db: Session = Depends(get_db), limit=100, current_user: CurrentUser = Depends(require_auth)):
    return R(data={"data": [md(r) for r in db.query(Account).limit(limit).all()], "length": db.query(Account).count()})

@router.post("/Account", response_model=R)
def create_account(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    name = data.get("name") or seq_for("Account", db)
    m = _upsert(Account, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Account created")

@router.get("/Account/{name}", response_model=R)
def get_account(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Account).filter(Account.name == name).first()
    if not m: raise HTTPException(404, "Account not found")
    return R(data=md(m))

@router.put("/Account/{name}", response_model=R)
def update_account(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = _upsert(Account, name, data, db); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Account updated")

@router.delete("/Account/{name}", response_model=R)
def delete_account(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(Account).filter(Account.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Account deleted")

# ── Journal Entry（借贷平衡校验）───────────────────────────────
@router.get("/Journal Entry", response_model=R)
def list_journals(db: Session = Depends(get_db), limit=50, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(JournalEntry).order_by(JournalEntry.creation.desc()).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Journal Entry", response_model=R)
def create_journal(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    accounts = data.get("accounts", [])
    if not accounts: raise HTTPException(400, "日记账至少需要一条分录")
    debit = sum(float(a.get("debit", 0) or 0) for a in accounts)
    credit = sum(float(a.get("credit", 0) or 0) for a in accounts)
    if abs(debit - credit) > 0.01:
        raise HTTPException(400, f"借贷不平衡：借方 {debit:.2f} / 贷方 {credit:.2f}")
    name = data.get("name") or seq_for("Journal Entry", db)
    m = JournalEntry(name=name, title=data.get("title",""), posting_date=data.get("posting_date"),
                     remark=data.get("remark"), accounts_json=json.dumps(accounts))
    db.add(m); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Journal Entry created")

@router.get("/Journal Entry/{name}", response_model=R)
def get_journal(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(JournalEntry).filter(JournalEntry.name == name).first()
    if not m: raise HTTPException(404, "Journal Entry not found")
    return R(data=md(m))

@router.put("/Journal Entry/{name}", response_model=R)
def update_journal(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(JournalEntry).filter(JournalEntry.name == name).first()
    if not m: raise HTTPException(404, "Journal Entry not found")
    for k, v in data.items():
        if k == "accounts": setattr(m, "accounts_json", json.dumps(v))
        elif k not in ("name",) and hasattr(m, k): setattr(m, k, v)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Journal Entry updated")

@router.delete("/Journal Entry/{name}", response_model=R)
def delete_journal(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(JournalEntry).filter(JournalEntry.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Journal Entry deleted")

# ── Payment Entry ─────────────────────────────────────────────
@router.get("/Payment Entry", response_model=R)
def list_payments(db: Session = Depends(get_db), limit=50, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(PaymentEntry).order_by(PaymentEntry.creation.desc()).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Payment Entry", response_model=R)
def create_payment(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    name = data.get("name") or seq_for("Payment Entry", db)
    m = _upsert(PaymentEntry, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Payment Entry created")

@router.get("/Payment Entry/{name}", response_model=R)
def get_payment(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(PaymentEntry).filter(PaymentEntry.name == name).first()
    if not m: raise HTTPException(404, "Payment Entry not found")
    return R(data=md(m))

@router.put("/Payment Entry/{name}", response_model=R)
def update_payment(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = _upsert(PaymentEntry, name, data, db); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Payment Entry updated")

@router.delete("/Payment Entry/{name}", response_model=R)
def delete_payment(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(PaymentEntry).filter(PaymentEntry.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Payment Entry deleted")

# ── Expense Claim ─────────────────────────────────────────────
@router.get("/Expense Claim", response_model=R)
def list_claims(db: Session = Depends(get_db), limit=50, current_user: CurrentUser = Depends(require_auth)):
    rows = db.query(ExpenseClaim).order_by(ExpenseClaim.creation.desc()).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Expense Claim", response_model=R)
def create_claim(data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    amount = float(data.get("claim_amount", 0) or 0)
    if amount <= 0: raise HTTPException(400, "报销金额必须大于 0")
    name = data.get("name") or seq_for("Expense Claim", db)
    m = _upsert(ExpenseClaim, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Expense Claim created")

@router.get("/Expense Claim/{name}", response_model=R)
def get_claim(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(ExpenseClaim).filter(ExpenseClaim.name == name).first()
    if not m: raise HTTPException(404, "Expense Claim not found")
    return R(data=md(m))

@router.put("/Expense Claim/{name}", response_model=R)
def update_claim(name: str, data: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = _upsert(ExpenseClaim, name, data, db); db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Expense Claim updated")

@router.delete("/Expense Claim/{name}", response_model=R)
def delete_claim(name: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    m = db.query(ExpenseClaim).filter(ExpenseClaim.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Expense Claim deleted")

# ── 发票分类 / 财务汇总 ────────────────────────────────────────
class InvoiceClassifyRequest(BaseModel):
    supplier: str = ""; amount: float = 0; description: str = ""

@router.post("/ai/classify_invoice")
def ai_classify_invoice(req: InvoiceClassifyRequest, db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    desc = req.description.lower(); supplier = req.supplier.lower()
    rules = [
        (r"云计算|服务器|域名|带宽|oss|cdn|云", "IT基础设施"),
        (r"招聘|猎头|社保|公积金|薪资|工资", "人力成本"),
        (r"差旅|机票|酒店|打车|高铁|餐饮|住宿", "差旅费用"),
        (r"广告|推广|投放|seo|sem|营销|媒体", "市场营销"),
        (r"律师|法律|专利|商标|著作权", "法务费用"),
        (r"采购|硬件|设备|物料|耗材|电脑", "采购成本"),
        (r"房租|物业|水电|办公用品|快递|文具", "行政运营"),
    ]
    for pattern, category in rules:
        if re.search(pattern, desc): return {"category": category, "confidence": "auto", "method": "keyword"}
    supplier_map = {"腾讯云":"IT基础设施","阿里云":"IT基础设施","华为云":"IT基础设施","aws":"IT基础设施"}
    for key, cat in supplier_map.items():
        if key.lower() in supplier: return {"category": cat, "confidence": "auto", "method": "supplier_map"}
    return {"category": "待分类", "confidence": "low", "method": "unmatched"}

@router.get("/finance_summary")
def finance_summary(db: Session = Depends(get_db), current_user: CurrentUser = Depends(require_auth)):
    accounts = db.query(Account).all()
    total_debit = total_credit = 0.0
    for je in db.query(JournalEntry).all():
        for a in json.loads(je.accounts_json or "[]"):
            total_debit += float(a.get("debit", 0) or 0)
            total_credit += float(a.get("credit", 0) or 0)
    pending = db.query(ExpenseClaim).filter(ExpenseClaim.approval_status.in_(["Draft","Submitted"])).all()
    paid = db.query(ExpenseClaim).filter(ExpenseClaim.approval_status == "Paid").all()
    return {
        "accounts": [md(a) for a in accounts],
        "account_count": len(accounts),
        "journal_count": db.query(JournalEntry).count(),
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "balanced": abs(total_debit - total_credit) < 0.01,
        "pending_claims": len(pending),
        "pending_claim_amount": round(sum(c.claim_amount for c in pending), 2),
        "paid_claim_amount": round(sum(c.claim_amount for c in paid), 2),
    }
