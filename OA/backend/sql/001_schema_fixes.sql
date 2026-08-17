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
