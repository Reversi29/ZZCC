"""database.py — SQLAlchemy ORM（SQLite for dev，切换 MariaDB 只需改 URL）"""
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, Date, DateTime, Enum, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, date
from pathlib import Path
import os

# ── 切换数据库只需改这一行 ────────────────────────────────────
# SQLite（当前，开发/演示）
DB_URL = os.getenv("DATABASE_URL", "sqlite:///data/zzcc_oa.db")

# MariaDB（未来）示例：
# DB_URL = "mysql+pymysql://root:zzcc_oa_2024@127.0.0.1:3307/zzcc_oa"

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Session:
    """FastAPI 依赖注入：每请求一个 session，用完自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """启动时创建所有表"""
    # SQLite: 建 data 目录
    if DB_URL.startswith("sqlite"):
        Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)


# ── 基础字段混入 ──────────────────────────────────────────────
class Timestamped:
    creation = Column(DateTime, default=datetime.utcnow)
    modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    modified_by = Column(String(255), default="Administrator")


# ═══════════════════════════════════════════════════════════════
# 所有模型（对齐 ERPNext v15 字段结构）
# ═══════════════════════════════════════════════════════════════

class Account(Base, Timestamped):
    __tablename__ = "accounts"
    name = Column(String(255), primary_key=True)
    account_name = Column(String(255), nullable=False)
    account_type = Column(String(50), default="Expense")   # Asset/Liability/Equity/Income/Expense
    root_type = Column(String(50), default="Expense")
    is_group = Column(Boolean, default=False)
    parent_account = Column(String(255), nullable=True)
    balance = Column(Float, default=0.0)


class Employee(Base, Timestamped):
    __tablename__ = "employees"
    name = Column(String(255), primary_key=True)
    employee_name = Column(String(255), nullable=False)
    first_name = Column(String(100), default="")
    last_name = Column(String(100), default="")
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    designation = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    employment_type = Column(String(50), default="Full-time")
    status = Column(String(50), default="Active")
    company = Column(String(255), default="ZZCC")


class Lead(Base, Timestamped):
    __tablename__ = "leads"
    name = Column(String(255), primary_key=True)
    lead_name = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    email_id = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    source = Column(String(100), nullable=True)
    lead_status = Column(String(50), default="New")
    annual_revenue = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    docstatus = Column(Integer, default=0)


class Contact(Base, Timestamped):
    __tablename__ = "contacts"
    name = Column(String(255), primary_key=True)
    first_name = Column(String(100), default="")
    last_name = Column(String(100), default="")
    email_id = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    company_name = Column(String(255), nullable=True)
    designation = Column(String(255), nullable=True)
    is_primary_contact = Column(Boolean, default=True)


class Opportunity(Base, Timestamped):
    __tablename__ = "opportunities"
    name = Column(String(255), primary_key=True)
    opportunity_name = Column(String(255), nullable=False)
    party_name = Column(String(255), nullable=True)
    sales_stage = Column(String(100), default="Prospecting")
    probability = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    expected_closing_date = Column(Date, nullable=True)


class Project(Base, Timestamped):
    __tablename__ = "projects"
    name = Column(String(255), primary_key=True)
    project_name = Column(String(255), nullable=False)
    status = Column(String(50), default="Open")
    priority = Column(String(50), default="Medium")
    percent_complete = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    project_manager = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    company = Column(String(255), default="ZZCC")
    notes = Column(Text, nullable=True)
    docstatus = Column(Integer, default=0)


class Task(Base, Timestamped):
    __tablename__ = "tasks"
    name = Column(String(255), primary_key=True)
    subject = Column(String(255), nullable=False)
    project = Column(String(255), nullable=True)
    status = Column(String(50), default="Open")
    priority = Column(String(50), default="Medium")
    progress = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    assigned_to = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)


class Supplier(Base, Timestamped):
    __tablename__ = "suppliers"
    name = Column(String(255), primary_key=True)
    supplier_name = Column(String(255), nullable=False)
    supplier_group = Column(String(100), nullable=True)
    supplier_type = Column(String(50), default="Company")
    country = Column(String(100), nullable=True)
    tax_id = Column(String(100), nullable=True)
    website = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)


class PurchaseOrder(Base, Timestamped):
    __tablename__ = "purchase_orders"
    name = Column(String(255), primary_key=True)
    supplier = Column(String(255), nullable=False)
    schedule_date = Column(Date, nullable=True)
    status = Column(String(50), default="Draft")
    total = Column(Float, default=0.0)
    items_json = Column(Text, default="[]")   # JSON 序列化子表
    terms = Column(Text, nullable=True)
    docstatus = Column(Integer, default=0)


class JournalEntry(Base, Timestamped):
    __tablename__ = "journal_entries"
    name = Column(String(255), primary_key=True)
    title = Column(String(500), nullable=False)
    posting_date = Column(Date, nullable=True)
    voucher_type = Column(String(100), default="Journal Entry")
    remark = Column(Text, nullable=True)
    company = Column(String(255), default="ZZCC")
    accounts_json = Column(Text, default="[]")  # JSON 序列化分录
    docstatus = Column(Integer, default=0)


class PaymentEntry(Base, Timestamped):
    __tablename__ = "payment_entries"
    name = Column(String(255), primary_key=True)
    payment_type = Column(String(50), default="Receive")
    party_type = Column(String(50), default="Customer")
    party = Column(String(255), nullable=False)
    paid_amount = Column(Float, default=0.0)
    mode_of_payment = Column(String(100), nullable=True)
    reference_no = Column(String(255), nullable=True)
    reference_date = Column(Date, nullable=True)
    status = Column(String(50), default="Draft")
    docstatus = Column(Integer, default=0)


class ExpenseClaim(Base, Timestamped):
    __tablename__ = "expense_claims"
    name = Column(String(255), primary_key=True)
    employee = Column(String(255), nullable=False)
    expense_type = Column(String(100), default="Travel")
    claim_amount = Column(Float, default=0.0)
    expense_date = Column(Date, nullable=True)
    approval_status = Column(String(50), default="Draft")
    purpose = Column(Text, nullable=True)


class Contract(Base, Timestamped):
    __tablename__ = "contracts"
    name = Column(String(255), primary_key=True)
    contract_name = Column(String(500), nullable=False)
    party_a = Column(String(255), nullable=True)
    party_b = Column(String(255), nullable=True)
    contract_type = Column(String(100), nullable=True)
    contract_value = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(String(50), default="Active")
    terms = Column(Text, nullable=True)


class QualityInspection(Base, Timestamped):
    __tablename__ = "quality_inspections"
    name = Column(String(255), primary_key=True)
    inspection_type = Column(String(100), default="Incoming")
    item_code = Column(String(255), nullable=True)
    batch_no = Column(String(100), nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    readings_json = Column(Text, default="[]")
    status = Column(String(50), default="Draft")


class SupportTicket(Base, Timestamped):
    __tablename__ = "support_tickets"
    name = Column(String(255), primary_key=True)
    subject = Column(String(500), nullable=False)
    ticket_type = Column(String(100), nullable=True)
    status = Column(String(50), default="Open")
    priority = Column(String(50), default="Medium")
    raised_by = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)


class Item(Base, Timestamped):
    __tablename__ = "items"
    name = Column(String(255), primary_key=True)
    item_code = Column(String(255), nullable=False)
    item_name = Column(String(255), nullable=False)
    item_group = Column(String(100), nullable=True)
    stock_uom = Column(String(50), default="Nos")
    val_rate = Column(Float, default=0.0)
    opening_stock = Column(Float, default=0.0)
    reorder_levels_json = Column(Text, default="[]")
    is_purchase_item = Column(Boolean, default=True)
    is_sales_item = Column(Boolean, default=True)


class StockEntry(Base, Timestamped):
    __tablename__ = "stock_entries"
    name = Column(String(255), primary_key=True)
    stock_entry_type = Column(String(100), default="Material Receipt")
    from_warehouse = Column(String(255), nullable=True)
    to_warehouse = Column(String(255), nullable=True)
    items_json = Column(Text, default="[]")
    status = Column(String(50), default="Draft")


class Asset(Base, Timestamped):
    __tablename__ = "assets"
    name = Column(String(255), primary_key=True)
    asset_name = Column(String(255), nullable=False)
    asset_category = Column(String(100), nullable=True)
    asset_type = Column(String(50), default="Fixed Asset")
    purchase_date = Column(Date, nullable=True)
    purchase_value = Column(Float, default=0.0)
    custodian = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    status = Column(String(50), default="Active")
