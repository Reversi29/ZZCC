"""database.py — SQLAlchemy ORM（所有配置从 config.py 读取 .env）"""
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, Date, DateTime, Time, Enum, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, date
from pathlib import Path
import hashlib

from config import get_settings

_DB_URL = get_settings().DATABASE_URL
engine = create_engine(
    _DB_URL,
    connect_args={"check_same_thread": False} if _DB_URL.startswith("sqlite") else {},
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


def _hash_pw(password: str) -> str:
    """Hash password with salt from settings (lazy eval to avoid conftest import order issues)."""
    from config import get_settings
    salt_hex = get_settings().PASSWORD_SALT_HEX
    # Pad hex string to even length and decode
    salt_bytes = bytes.fromhex(salt_hex.ljust(len(salt_hex) + (8 - len(salt_hex) % 8) % 8, '0'))
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 310_000).hex()


def init_db():
    """启动时创建所有表"""
    # SQLite: 建 data 目录
    if _DB_URL.startswith("sqlite"):
        Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _seed_default_users()


def _seed_default_users():
    """启动时写入默认用户（仅当表中无数据时）"""
    try:
        db = SessionLocal()
        try:
            if db.query(User).count() > 0:
                return
            defaults = [
                ("admin", "admin123", "管理员", "admin"),
                ("user01", "pass01", "张三", "user"),
            ]
            for username, password, display_name, role in defaults:
                db.add(User(
                    username=username,
                    hashed_password=_hash_pw(password),
                    display_name=display_name,
                    role=role,
                ))
            db.commit()
            print("[init] Default users seeded: admin/admin123, user01/pass01")
        finally:
            db.close()
    except Exception as e:
        print(f"[init] User seed skipped: {e}")


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
    status = Column(String(50), default="Draft")
    company = Column(String(255), default="ZZCC")
    hire_date = Column(Date, nullable=True)
    leave_annual = Column(Float, default=15.0)
    leave_sick = Column(Float, default=10.0)
    leave_annual_used = Column(Float, default=0.0)
    leave_sick_used = Column(Float, default=0.0)
    department_id = Column(Integer, nullable=True)
    bank_account = Column(String(100), nullable=True)
    tax_id = Column(String(100), nullable=True)


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
    owner = Column(String(255), nullable=True)  # 数据隔离：销售只看自己客户


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
    owner = Column(String(255), nullable=True)


class Opportunity(Base, Timestamped):
    __tablename__ = "opportunities"
    name = Column(String(255), primary_key=True)
    opportunity_name = Column(String(255), nullable=False)
    party_name = Column(String(255), nullable=True)
    sales_stage = Column(String(100), default="Prospecting")
    probability = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    expected_closing_date = Column(Date, nullable=True)
    owner = Column(String(255), nullable=True)


class Project(Base, Timestamped):
    __tablename__ = "projects"
    name = Column(String(255), primary_key=True)
    project_name = Column(String(255), nullable=False)
    status = Column(String(50), default="Draft")  # Draft/Submitted/Approved/Rejected/Cancelled
    priority = Column(String(50), default="Medium")
    percent_complete = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    project_manager = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    company = Column(String(255), default="ZZCC")
    notes = Column(Text, nullable=True)


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
    reorder_level = Column(Float, default=0.0)   # 全局库存预警阈值
    warehouse = Column(String(255), nullable=True)


class StockEntry(Base, Timestamped):
    __tablename__ = "stock_entries"
    name = Column(String(255), primary_key=True)
    stock_entry_type = Column(String(100), default="Material Receipt")
    from_warehouse = Column(String(255), nullable=True)
    to_warehouse = Column(String(255), nullable=True)
    items_json = Column(Text, default="[]")
    status = Column(String(50), default="Draft")
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(String(255), nullable=True)
    department_id = Column(Integer, nullable=True)


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



class Warehouse(Base, Timestamped):
    """仓库"""
    __tablename__ = "warehouses"
    name = Column(String(255), primary_key=True)
    warehouse_name = Column(String(255), nullable=False)
    warehouse_type = Column(String(50), default="Physical")   # Physical / Virtual
    address = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    status = Column(String(50), default="Active")
    department_id = Column(Integer, nullable=True)


class StockLedger(Base, Timestamped):
    """库存台账 — 每笔库存变动记录"""
    __tablename__ = "stock_ledger"
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_code = Column(String(255), nullable=False)
    warehouse = Column(String(255), nullable=False)
    stock_entry_type = Column(String(100), nullable=False)   # Material Receipt / Material Issue / Material Transfer
    stock_entry_name = Column(String(255), nullable=True)
    voucher_type = Column(String(100), default="Stock Entry")
    voucher_no = Column(String(255), nullable=True)
    posting_date = Column(Date, nullable=False)
    posting_time = Column(Time, nullable=True)
    incoming_qty = Column(Float, default=0.0)
    outgoing_qty = Column(Float, default=0.0)
    balance_qty = Column(Float, default=0.0)
    valuation_rate = Column(Float, default=0.0)
    stock_value = Column(Float, default=0.0)
    party_type = Column(String(50), nullable=True)
    party = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)


class StockBalance(Base, Timestamped):
    """库存余额 — 当前各仓库各物料的库存快照"""
    __tablename__ = "stock_balances"
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_code = Column(String(255), nullable=False)
    warehouse = Column(String(255), nullable=False)
    actual_qty = Column(Float, default=0.0)
    reserved_qty = Column(Float, default=0.0)
    ordered_qty = Column(Float, default=0.0)
    valuation_rate = Column(Float, default=0.0)
    stock_value = Column(Float, default=0.0)
    last_updated = Column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint('item_code', 'warehouse', name='uq_item_warehouse'),
    )


class LeaveRequest(Base, Timestamped):
    __tablename__ = "leave_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    employee = Column(String(255), nullable=False)
    leave_type = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Float, default=1.0)
    reason = Column(Text, nullable=True)
    status = Column(String(50), default="Draft")
    approver = Column(String(255), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    department_id = Column(Integer, nullable=True)

class AttendanceRecord(Base, Timestamped):
    __tablename__ = "attendance_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee = Column(String(255), nullable=False)
    date = Column(Date, nullable=False)
    check_in = Column(Time, nullable=True)
    check_out = Column(Time, nullable=True)
    status = Column(String(50), default="Normal")
    remark = Column(String(255), nullable=True)
    department_id = Column(Integer, nullable=True)

class SalaryRecord(Base, Timestamped):
    __tablename__ = "salary_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee = Column(String(255), nullable=False)
    year_month = Column(String(7), nullable=False)
    base_salary = Column(Float, default=0.0)
    bonus = Column(Float, default=0.0)
    deductions = Column(Float, default=0.0)
    net_salary = Column(Float, default=0.0)
    pay_date = Column(Date, nullable=True)
    remark = Column(Text, nullable=True)
    department_id = Column(Integer, nullable=True)

class WorkflowHistory(Base, Timestamped):
    __tablename__ = "workflow_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_name = Column(String(255), nullable=False, index=True)
    doctype = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    comment = Column(Text, nullable=True)
    operator = Column(String(255), default="system")
    field_changes = Column(Text, nullable=True)  # JSON 字符串：字段变更明细（如 {"status": {"from":"Draft","to":"Submitted"}}）


class Notification(Base, Timestamped):
    """审批通知"""
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    recipient = Column(String(255), nullable=False, index=True)  # 接收人/角色
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    ntype = Column(String(50), default="info")  # approval_request | approval_result | info | reminder
    doctype = Column(String(50), nullable=True)
    doc_name = Column(String(255), nullable=True)
    action = Column(String(50), nullable=True)   # submit/approve/reject/pay...
    is_read = Column(Boolean, default=False)
    priority = Column(String(20), default="normal")  # low | normal | urgent


class User(Base):
    """认证用户（DB-backed，替代内存 dict）"""
    __tablename__ = "users"
    username = Column(String(80), primary_key=True)
    hashed_password = Column(String(255), nullable=False)
    display_name = Column(String(120), nullable=False)
    role = Column(String(50), default="user")  # admin | user
    department_id = Column(String(80), ForeignKey("departments.name"), nullable=True)  # nullable: 小团队不强制绑定
    is_active = Column(Boolean, default=True)
    status = Column(String(50), default="active")  # active | pending | rejected（注册审批流）
    ext = Column(Text, nullable=True)  # JSON，预留给 title/phone/manager 等未来字段
    creation = Column(DateTime, default=datetime.utcnow)
    modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Department(Base, Timestamped):
    """
    组织部门（Nested Set Model）。
    - lft/rgt 形成树的包含区间：子部门的 lft > 父.lft 且 rgt < 父.rgt
    - 查询某部门所有下属：WHERE lft > :parent_lft AND rgt < :parent_rgt
    - 查询完整路径（根→当前）：WHERE lft <= :self_lft AND rgt >= :self_rgt ORDER BY lft
    - ext JSON 预留给 cost_center / approval_limit / manager_title 等未来字段
    """
    __tablename__ = "departments"
    name = Column(String(80), primary_key=True)
    department_name = Column(String(120), nullable=False)
    parent = Column(String(80), ForeignKey("departments.name"), nullable=True)  # None=根部门
    lft = Column(Integer, nullable=False, index=True)   # 左值
    rgt = Column(Integer, nullable=False, index=True)   # 右值
    company = Column(String(80), nullable=True)          # 所属公司（多租户场景预留）
    is_group = Column(Boolean, default=False)            # True=仅作分组/汇总节点
    ext = Column(Text, nullable=True)                   # JSON，预留给 cost_center / manager_title 等


class Budget(Base, Timestamped):
    """月度预算控制（三维：doctype + period + department）"""
    __tablename__ = "budgets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    doctype = Column(String(50), nullable=False, index=True)
    period = Column(String(20), nullable=False)
    department_id = Column(String(80), nullable=True)          # None=全局预算（全公司）
    limit_amount = Column(Float, default=0.0)
    used_amount = Column(Float, default=0.0)
    note = Column(String(255), nullable=True)


class ApprovalRule(Base, Timestamped):
    """
    多级审批规则。
    - 无 department_id 时为全局规则（所有部门适用）
    - 有 department_id 时为该部门专用规则，覆盖同名全局规则
    - 有 level 时按 level 升序执行多级审批
    """
    __tablename__ = "approval_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    doctype = Column(String(50), nullable=False, index=True)
    department_id = Column(String(80), nullable=True)          # None=全局规则
    level = Column(Integer, nullable=False)
    approver_role = Column(String(50), default="admin")
    condition_json = Column(Text, nullable=True)               # 金额阈值等条件（JSON 字符串）


class Delegation(Base, Timestamped):
    """审批代理人：grantor 委托 delegate 代其审批（可限定 doctype + department）"""
    __tablename__ = "delegations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    grantor = Column(String(80), nullable=False)    # 委托人 username
    delegate = Column(String(80), nullable=False)   # 代理人 username
    doctype = Column(String(50), nullable=True)     # 限定单据类型，None=全部
    department_id = Column(String(80), nullable=True)  # 限定部门，None=全部部门
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)


class Announcement(Base, Timestamped):
    """企业公告"""
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    published_by = Column(String(255), nullable=False)  # 发布人 username
    status = Column(String(20), nullable=False, default="draft")  # draft / published
    is_pinned = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=True)         # 自动过期时间
    view_count = Column(Integer, default=0, nullable=False)


class DailyReport(Base, Timestamped):
    """日报/周报"""
    __tablename__ = "daily_reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)  # 报告标题(如"日报 2026-08-22")
    report_type = Column(String(10), nullable=False, default="daily")  # daily / weekly
    report_date = Column(Date, nullable=False)  # 报告对应日期
    content = Column(Text, nullable=False)  # 报告正文
    author = Column(String(255), nullable=False)  # 作者 username
    status = Column(String(20), nullable=False, default="draft")  # draft / submitted
