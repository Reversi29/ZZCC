-- ZZCC OA schema 迁移（幂等，可重复执行）
-- 背景：P2.9 / P2.10 开发时修改了 ORM model，但从未对生产库 ALTER；
--       SQLAlchemy create_all 只建新表、不改已有表结构，导致列漂移 → 运行时 500。
-- 以下用 IF NOT EXISTS 补齐缺失列：
--   - 全新库会被 create_all 建好完整结构，此处语句自动跳过；
--   - 已有生产库补齐缺失列，恢复服务。

-- CRM 数据隔离字段（P2.10）
ALTER TABLE leads ADD COLUMN IF NOT EXISTS owner VARCHAR(255) NULL;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS owner VARCHAR(255) NULL;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS owner VARCHAR(255) NULL;

-- 请假单 name 列（P2.9 workflow 引擎依赖 name 查询）
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS name VARCHAR(255) NOT NULL DEFAULT '';

-- 员工扩展字段（P2.9 HR 模块）
ALTER TABLE employees ADD COLUMN IF NOT EXISTS hire_date DATE NULL;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS leave_annual FLOAT NULL DEFAULT 15.0;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS leave_sick FLOAT NULL DEFAULT 10.0;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS leave_annual_used FLOAT NULL DEFAULT 0.0;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS leave_sick_used FLOAT NULL DEFAULT 0.0;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS department_id INTEGER NULL;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS bank_account VARCHAR(100) NULL;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS tax_id VARCHAR(100) NULL;

-- 库存扩展字段
ALTER TABLE items ADD COLUMN IF NOT EXISTS reorder_level REAL NULL;
ALTER TABLE items ADD COLUMN IF NOT EXISTS warehouse VARCHAR(255) NULL;

-- 入库/出库单据扩展字段
ALTER TABLE stock_entries ADD COLUMN IF NOT EXISTS submitted_at TEXT NULL;
ALTER TABLE stock_entries ADD COLUMN IF NOT EXISTS department_id TEXT NULL;
ALTER TABLE stock_entries ADD COLUMN IF NOT EXISTS submitted_by TEXT NULL;

-- 审批历史扩展字段
ALTER TABLE workflow_history ADD COLUMN IF NOT EXISTS field_changes TEXT NULL;

-- 企业公告表（P4.20）
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    published_by VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    is_pinned INTEGER DEFAULT 0,
    expires_at TEXT NULL,
    view_count INTEGER DEFAULT 0,
    creation TEXT NULL,
    modified TEXT NULL,
    modified_by VARCHAR(255) DEFAULT 'Administrator'
);

-- 日报/周报表（P4.23）
CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    report_type TEXT NOT NULL DEFAULT 'daily',
    report_date TEXT NOT NULL,
    content TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    creation TEXT NULL,
    modified TEXT NULL,
    modified_by TEXT DEFAULT 'Administrator'
);
