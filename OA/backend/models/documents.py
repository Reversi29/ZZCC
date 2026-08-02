"""ZZCC OA — ERPNext v15 兼容数据模型"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any
from datetime import datetime, date
from enum import Enum


# ── ERPNext 标准枚举 ──────────────────────────────────────────
class DocStatus(str, Enum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    CANCELLED = "Cancelled"


class LeadStatus(str, Enum):
    NEW = "New"
    CONTACTED = "Contacted"
    QUALIFIED = "Qualified"
    CONVERTED = "Converted"
    LOST = "Lost"


class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"


# ── 基础文档 ──────────────────────────────────────────────────
class ZZDocBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None           # ERPNext 主键字段
    owner: Optional[str] = "Administrator"
    creation: Optional[datetime] = None
    modified: Optional[datetime] = None
    modified_by: Optional[str] = None
    docstatus: int = 0                   # 0=Draft, 1=Submitted, 2=Cancelled
    idx: int = 0


# ── User / Employee ────────────────────────────────────────────
class User(ZZDocBase):
    email: str
    first_name: str = ""
    last_name: str = ""
    enabled: bool = True
    user_type: str = "System User"
    role_profile_name: Optional[str] = None
    department: Optional[str] = None


class Employee(ZZDocBase):
    employee_name: str
    first_name: str = ""
    last_name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None          # 职位
    department: Optional[str] = None
    branch: Optional[str] = None
    employment_type: str = "Full-time"
    date_of_joining: Optional[date] = None
    status: str = "Active"
    company: Optional[str] = "ZZCC"


# ── CRM: Lead / Contact / Opportunity ─────────────────────────
class Lead(ZZDocBase):
    leads: str = ""
    salutation: Optional[str] = None
    lead_name: str
    company_name: Optional[str] = None
    email_id: Optional[str] = None
    phone: Optional[str] = None
    mobile_no: Optional[str] = None
    lead_owner: Optional[str] = None
    source: Optional[str] = None
    lead_status: str = "New"
    territory: Optional[str] = None
    industry: Optional[str] = None
    annual_revenue: Optional[float] = None
    no_of_employees: Optional[int] = None
    notes: Optional[str] = None


class Contact(ZZDocBase):
    first_name: str = ""
    last_name: str = ""
    salutation: Optional[str] = None
    email_id: Optional[str] = None
    phone: Optional[str] = None
    mobile_no: Optional[str] = None
    company_name: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    is_primary_contact: bool = True


class Opportunity(ZZDocBase):
    opportunity_name: str
    party_name: Optional[str] = None
    op_type: str = "Sales"
    sales_stage: str = "Prospecting"
    probability: float = 0.0
    amount: float = 0.0
    currency: str = "CNY"
    expected_closing_date: Optional[date] = None
    source: Optional[str] = None
    contact_person: Optional[str] = None
    notes: Optional[str] = None


# ── Project & Task ─────────────────────────────────────────────
class Project(ZZDocBase):
    project_name: str
    project_code: Optional[str] = None
    status: str = "Open"
    project_type: Optional[str] = None
    is_active: bool = True
    percent_complete: float = 0.0
    project_template: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    expected_start_date: Optional[date] = None
    expected_end_date: Optional[date] = None
    priority: str = "Medium"
    project_manager: Optional[str] = None
    department: Optional[str] = None
    company: str = "ZZCC"
    estimated_hours: float = 0.0
    actual_hours: float = 0.0
    notes: Optional[str] = None


class Task(ZZDocBase):
    subject: str
    project: Optional[str] = None
    status: str = "Open"
    priority: str = "Medium"
    task_weight: float = 0.0
    parent_task: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    expected_time: float = 0.0
    progress: float = 0.0
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    department: Optional[str] = None
    company: str = "ZZCC"


# ── Purchase ────────────────────────────────────────────────────
class PurchaseOrder(ZZDocBase):
    po_no: Optional[str] = None
    supplier: str
    schedule_date: Optional[date] = None
    status: str = "Draft"
    currency: str = "CNY"
    conversion_rate: float = 1.0
    buying_price_list: Optional[str] = None
    prices_include_tax: str = "No"
    tax_withholding_category: Optional[str] = None
    payment_terms_template: Optional[str] = None
    tc_name: Optional[str] = None
    terms: Optional[str] = None
    total: float = 0.0                     # 订单总额（自动计算）
    # 子表（简化）
    items: List[dict] = Field(default_factory=list)
    taxes: List[dict] = Field(default_factory=list)


class Supplier(ZZDocBase):
    supplier_name: str
    supplier_group: Optional[str] = None
    supplier_type: str = "Company"
    country: Optional[str] = None
    default_currency: Optional[str] = None
    default_price_list: Optional[str] = None
    payment_terms: Optional[str] = None
    tax_id: Optional[str] = None
    website: Optional[str] = None
    primary_address: Optional[str] = None
    primary_contact: Optional[str] = None
    notes: Optional[str] = None


# ── Stock ──────────────────────────────────────────────────────
class StockEntry(ZZDocBase):
    stock_entry_type: str = "Material Receipt"
    purpose: Optional[str] = None
    add_to_transit: bool = False
    from_warehouse: Optional[str] = None
    to_warehouse: Optional[str] = None
    items: List[dict] = Field(default_factory=list)


class Asset(ZZDocBase):
    asset_name: str
    asset_category: Optional[str] = None       # 电子设备 / 办公家具 / 车辆 / 生产设备 / 其他
    asset_type: str = "Fixed Asset"
    purchase_date: Optional[date] = None
    purchase_value: float = 0.0
    location: Optional[str] = None
    custodian: Optional[str] = None            # 保管人
    status: str = "Active"                     # Active / In Maintenance / Scrapped
    depreciation_method: Optional[str] = None  # Straight Line / Written Down Value
    expected_life_years: Optional[float] = None


class Item(ZZDocBase):
    item_code: str
    item_name: str
    item_group: Optional[str] = None
    stock_uom: str = "Nos"
    disabled: bool = False
    allow_alternative_item: bool = False
    is_fixed_asset: bool = False
    asset_category: Optional[str] = None
    is_purchase_item: bool = True
    is_sales_item: bool = True
    val_rate: float = 0.0
    standard_rate: float = 0.0
    opening_stock: float = 0.0
    reorder_levels: List[dict] = Field(default_factory=list)


# ── Quality ────────────────────────────────────────────────────
class QualityInspection(ZZDocBase):
    inspection_type: str = "Incoming"
    reference_type: Optional[str] = None
    reference_name: Optional[str] = None
    item_code: Optional[str] = None
    item_serial_no: Optional[str] = None
    batch_no: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    remarks: Optional[str] = None
    inspection_parameters: List[dict] = Field(default_factory=list)
    readings: List[dict] = Field(default_factory=list)


# ── Finance: Account / Journal Entry / Payment Entry / Expense Claim ─
class Account(ZZDocBase):
    account_name: str
    account_type: str = "Expense"        # Asset / Liability / Equity / Income / Expense
    root_type: str = "Expense"           # Asset / Liability / Equity / Income / Expense
    is_group: bool = False
    parent_account: Optional[str] = None
    balance: float = 0.0


class ExpenseClaim(ZZDocBase):
    employee: str
    expense_type: str = "Travel"          # Travel / Meals / Office / Supplies / Entertainment / Other
    claim_amount: float = 0.0
    expense_date: Optional[date] = None
    approval_status: str = "Draft"        # Draft / Submitted / Approved / Rejected / Paid
    purpose: Optional[str] = None
    remark: Optional[str] = None


class JournalEntry(ZZDocBase):
    title: str
    voucher_type: str = "Journal Entry"
    accounts: List[dict] = Field(default_factory=list)
    remark: Optional[str] = None
    bexpect_invoice_date: Optional[date] = None
    posting_date: Optional[date] = None
    company: str = "ZZCC"
    currency: str = "CNY"
    exchange_rate: float = 1.0


class PaymentEntry(ZZDocBase):
    payment_type: str = "Receive"
    party_type: str = "Customer"
    party: str
    paid_from: Optional[str] = None
    paid_to: Optional[str] = None
    paid_amount: float = 0.0
    received_amount: float = 0.0
    currency: str = "CNY"
    exchange_rate: float = 1.0
    reference_no: Optional[str] = None
    reference_date: Optional[date] = None
    mode_of_payment: Optional[str] = None
    bank_account: Optional[str] = None


# ── Support ─────────────────────────────────────────────────────
class SupportTicket(ZZDocBase):
    subject: str
    ticket_type: Optional[str] = None
    status: str = "Open"
    priority: str = "Medium"
    raised_by: Optional[str] = None
    description: Optional[str] = None
    ticket_split_from: Optional[str] = None
    company: str = "ZZCC"


# ── Compliance ─────────────────────────────────────────────────
class Contract(ZZDocBase):
    contract_name: str
    party_a: Optional[str] = None
    party_b: Optional[str] = None
    contract_type: Optional[str] = None
    contract_template: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    signing_date: Optional[date] = None
    status: str = "Active"
    contract_value: float = 0.0
    currency: str = "CNY"
    terms: Optional[str] = None
    renewal_terms: Optional[str] = None
    notes: Optional[str] = None


# ── AI Result ──────────────────────────────────────────────────
class AITaskResult(BaseModel):
    task_id: str
    doctype: str
    action: str
    result: dict
    advice: Optional[str] = None
    risk_flags: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
