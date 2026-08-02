#!/usr/bin/env python3
"""
seed_data.py — ZZCC OA 演示数据填充
基于 SQLite 真实表结构（从 database.py 的 SQLAlchemy 模型映射）
"""
import sqlite3, json, os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "backend", "data", "zzcc_oa.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
NOW = datetime.now().isoformat()

def upsert(table, cols, row):
    cols_str = ", ".join(cols)
    ph = ", ".join(["?"] * len(cols))
    cur.execute(f"INSERT OR REPLACE INTO {table} ({cols_str}) VALUES ({ph})", row)

# ════════════════════════════════════════════════════════════════
# 财务（8 账户 + 3 日记账 + 4 报销单）
# ════════════════════════════════════════════════════════════════
accounts = [
    ("ACC-0001","银行存款-工行","Asset","Asset",0,None,500000.0),
    ("ACC-0002","应收账款","Asset","Asset",0,None,120000.0),
    ("ACC-0003","固定资产","Asset","Asset",0,None,300000.0),
    ("ACC-0004","应付账款","Liability","Liability",0,None,80000.0),
    ("ACC-0005","实收资本","Equity","Equity",0,None,900000.0),
    ("ACC-0006","主营业务收入","Revenue","Income",0,None,450000.0),
    ("ACC-0007","销售费用","Expense","Expense",0,None,60000.0),
    ("ACC-0008","管理费用","Expense","Expense",0,None,80000.0),
]
for r in accounts:
    upsert("accounts",
           ["name","account_name","account_type","root_type","is_group","parent_account","balance","creation","modified","modified_by"],
           r + (NOW, NOW, "Administrator"))

# 日记账（借贷必平衡）
for i, (title, amt, remark) in enumerate([
    ("收到华兴科技货款", 50000, "华兴科技货款核销"),
    ("购买办公设备",    30000, "购入服务器一台"),
    ("支付本月工资",    85000, "2024年7月工资发放"),
], 1):
    d_name = "ACC-0001"  # 银行存款
    c_name = "ACC-0002" if i == 1 else ("ACC-0008" if i == 3 else "ACC-0002")
    accts = [
        {"account": d_name, "debit": amt, "credit": 0, "cost_center": None},
        {"account": c_name, "debit": 0, "credit": amt, "cost_center": None},
    ]
    name = f"JE-{i:04d}"
    upsert("journal_entries",
           ["name","title","posting_date","remark","accounts_json","creation","modified","modified_by"],
           (name, title, NOW[:10], remark, json.dumps(accts), NOW, NOW, "Administrator"))

# 报销单
for name, emp, etype, amt, status, purpose in [
    ("EXP-0001","赵六","Travel",4800,"Draft","广州出差"),
    ("EXP-0002","李四","Food",1200,"Submitted","客户招待"),
    ("EXP-0003","王五","Office",3500,"Approved","采购办公用品"),
    ("EXP-0004","张三","Communication",800,"Paid","手机话费报销"),
]:
    upsert("expense_claims",
           ["name","employee","expense_type","claim_amount","approval_status","purpose","creation","modified","modified_by"],
           (name, emp, etype, amt, status, purpose, NOW, NOW, "Administrator"))

# ════════════════════════════════════════════════════════════════
# 人事（5 员工）
# ════════════════════════════════════════════════════════════════
for name, ename, dept, desig, email in [
    ("EMP-0001","张三","研发部","高级工程师","zhangsan@zzcc.com"),
    ("EMP-0002","李四","商务部","客户经理","lisi@zzcc.com"),
    ("EMP-0003","王五","财务部","会计","wangwu@zzcc.com"),
    ("EMP-0004","赵六","综合部","行政主管","zhaoliu@zzcc.com"),
    ("EMP-0005","孙七","质量部","质检工程师","sunqi@zzcc.com"),
]:
    upsert("employees",
           ["name","employee_name","department","designation","email","creation","modified","modified_by"],
           (name, ename, dept, desig, email, NOW, NOW, "Administrator"))

# ════════════════════════════════════════════════════════════════
# CRM（4 线索 + 3 商机）
# ════════════════════════════════════════════════════════════════
for name, lname, company, status, source, email, phone in [
    ("LEAD-0001","华兴科技","华兴科技","Lead","Website","hx@huaxing.com","13800138001"),
    ("LEAD-0002","深圳腾云","深圳腾云","New","Referral","ty@tengyun.com","13800138002"),
    ("LEAD-0003","北京智联","北京智联","Working","Campaign","zl@zhilian.com","13800138003"),
    ("LEAD-0004","上海云帆","上海云帆","New","Social","yf@yunfan.com","13800138004"),
]:
    upsert("leads",
           ["name","lead_name","company_name","lead_status","source","email_id","phone","creation","modified","modified_by"],
           (name, lname, company, status, source, email, phone, NOW, NOW, "Administrator"))

for name, oname, party, stage, prob, amt in [
    ("OPP-0001","企业ERP系统采购","华兴科技","Proposal",70,280000.0),
    ("OPP-0002","OA系统升级","深圳腾云","Negotiation",80,150000.0),
    ("OPP-0003","数据分析平台","北京智联","Qualification",30,350000.0),
]:
    upsert("opportunities",
           ["name","opportunity_name","party_name","sales_stage","probability","amount","creation","modified","modified_by"],
           (name, oname, party, stage, prob, amt, NOW, NOW, "Administrator"))

# ════════════════════════════════════════════════════════════════
# 项目（3 项目 + 4 任务）
# ════════════════════════════════════════════════════════════════
for name, pname, status, dept, manager in [
    ("PRJ-0001","ZZCC数据平台V2","Open","研发部","张三"),
    ("PRJ-0002","办公自动化升级","On Hold","综合部","赵六"),
    ("PRJ-0003","客户CRM系统","Completed","商务部","李四"),
]:
    upsert("projects",
           ["name","project_name","status","department","project_manager","creation","modified","modified_by"],
           (name, pname, status, dept, manager, NOW, NOW, "Administrator"))

for name, tname, project, status, priority in [
    ("TSK-0001","需求调研","PRJ-0001","Open","High"),
    ("TSK-0002","数据库设计","PRJ-0001","Open","Medium"),
    ("TSK-0003","前端开发","PRJ-0001","Working","High"),
    ("TSK-0004","系统测试","PRJ-0002","Open","Low"),
]:
    upsert("tasks",
           ["name","subject","project","status","priority","creation","modified","modified_by"],
           (name, tname, project, status, priority, NOW, NOW, "Administrator"))

# ════════════════════════════════════════════════════════════════
# 采购（3 供应商 + 3 采购订单）
# ════════════════════════════════════════════════════════════════
for name, sname, sgroup, country in [
    ("SUP-0001","深圳市华联电子","IT设备","中国"),
    ("SUP-0002","广州华南办公用品","办公用品","中国"),
    ("SUP-0003","北京中关村电脑城","IT设备","中国"),
]:
    upsert("suppliers",
           ["name","supplier_name","supplier_group","country","creation","modified","modified_by"],
           (name, sname, sgroup, country, NOW, NOW, "Administrator"))

for name, supplier, total, status, items in [
    ("PO-0001","SUP-0001",54000.0,"Submitted",[
        {"item_code":"SRV-001","item_name":"服务器","qty":10,"rate":5000.0},
        {"item_code":"NET-001","item_name":"网络交换机","qty":20,"rate":200.0},
    ]),
    ("PO-0002","SUP-0002",8750.0,"Draft",[
        {"item_code":"OFF-001","item_name":"A4打印纸","qty":50,"rate":150.0},
        {"item_code":"OFF-002","item_name":"激光墨盒","qty":25,"rate":50.0},
    ]),
    ("PO-0003","SUP-0003",280000.0,"Approved",[
        {"item_code":"PC-001","item_name":"台式电脑","qty":20,"rate":14000.0},
    ]),
]:
    upsert("purchase_orders",
           ["name","supplier","total","status","items_json","creation","modified","modified_by"],
           (name, supplier, total, status, json.dumps(items), NOW, NOW, "Administrator"))

# ════════════════════════════════════════════════════════════════
# 合同/合规（3 合同）
# ════════════════════════════════════════════════════════════════
for name, cname, party_a, party_b, ctype, value, sdate, edate, status in [
    ("CONTRACT-0001","华兴科技-ERP合同","ZZCC公司","华兴科技","销售合同",280000.0,"2024-03-01","2025-03-01","Active"),
    ("CONTRACT-0002","腾云科技-OA合同","ZZCC公司","深圳腾云","服务合同",150000.0,"2024-05-15","2025-05-15","Active"),
    ("CONTRACT-0003","智联招聘-软件合同","ZZCC公司","北京智联","软件许可",35000.0,"2024-01-01","2024-12-31","Expired"),
]:
    upsert("contracts",
           ["name","contract_name","party_a","party_b","contract_type","contract_value","start_date","end_date","status","creation","modified","modified_by"],
           (name, cname, party_a, party_b, ctype, value, sdate, edate, status, NOW, NOW, "Administrator"))

# ════════════════════════════════════════════════════════════════
# 客服（3 工单）
# ════════════════════════════════════════════════════════════════
for name, subject, status, priority, raised_by, desc in [
    ("TKT-0001","系统无法登录","Open","High","华兴科技-张总","登录时提示密码错误，重置后仍无法登录"),
    ("TKT-0002","报表数据错误","Working","Medium","深圳腾云-李经理","7月销售报表数字与实际不符"),
    ("TKT-0003","功能咨询","Closed","Low","北京智联-王主任","咨询批量导入功能使用方法"),
]:
    upsert("support_tickets",
           ["name","subject","status","priority","raised_by","description","creation","modified","modified_by"],
           (name, subject, status, priority, raised_by, desc, NOW, NOW, "Administrator"))

# ════════════════════════════════════════════════════════════════
# 质检（3 报告）
# ════════════════════════════════════════════════════════════════
for name, itype, item_code, batch, status in [
    ("QI-0001","Incoming","SRV-001","批次A-2024","Accepted"),
    ("QI-0002","Incoming","NET-001","批次B-2024","Accepted"),
    ("QI-0003","Outgoing","PC-001","批次C-2024","Accepted"),
]:
    readings = {"total_inspected":100,"accepted":95,"rejected":5,"notes":"外观检测正常"}
    upsert("quality_inspections",
           ["name","inspection_type","item_code","batch_no","status","readings_json","creation","modified","modified_by"],
           (name, itype, item_code, batch, status, json.dumps(readings), NOW, NOW, "Administrator"))

# ════════════════════════════════════════════════════════════════
# 库存/资产（5 物料 + 3 流水 + 4 固定资产）
# ════════════════════════════════════════════════════════════════
for name, icode, iname, igroup, uom, qty, rate, reorder in [
    ("ITEM-0001","SRV-001","服务器 R730","IT设备","Unit",25,8500.0,5),
    ("ITEM-0002","NET-001","网络交换机","IT设备","Unit",50,600.0,10),
    ("ITEM-0003","OFF-001","A4打印纸 500张/包","办公用品","Box",8,150.0,10),
    ("ITEM-0004","OFF-002","激光打印机墨盒","办公用品","Pcs",12,280.0,5),
    ("ITEM-0005","PC-001","台式电脑 DELL","IT设备","Unit",20,7000.0,3),
]:
    reorder_levels = json.dumps([{"warehouse":"主仓库","warehouse_reorder_level":reorder}])
    upsert("items",
           ["name","item_code","item_name","item_group","stock_uom","opening_stock","val_rate","reorder_levels_json","creation","modified","modified_by"],
           (name, icode, iname, igroup, uom, qty, rate, reorder_levels, NOW, NOW, "Administrator"))

for name, stype, from_w, to_w, items in [
    ("SE-0001","Material Receipt","","主仓库",[{"item_code":"SRV-001","qty":10}]),
    ("SE-0002","Material Issue","主仓库","",[{"item_code":"OFF-001","qty":5}]),
    ("SE-0003","Material Transfer","主仓库","备件库",[{"item_code":"NET-001","qty":3}]),
]:
    upsert("stock_entries",
           ["name","stock_entry_type","from_warehouse","to_warehouse","items_json","creation","modified","modified_by"],
           (name, stype, from_w, to_w, json.dumps(items), NOW, NOW, "Administrator"))

for name, aname, acat, atype, value, custodian, status in [
    ("AST-0001","DELL服务器 R730","IT设备","Fixed","85000.0","研发部","Active"),
    ("AST-0002","办公桌椅套装","办公家具","Fixed","12000.0","综合部","Active"),
    ("AST-0003","公司汽车-粤B12345","运输工具","Fixed","280000.0","综合部","Active"),
    ("AST-0004","会议室投影仪","电子设备","Fixed","18000.0","综合部","Active"),
]:
    upsert("assets",
           ["name","asset_name","asset_category","asset_type","purchase_value","custodian","status","creation","modified","modified_by"],
           (name, aname, acat, atype, value, custodian, status, NOW, NOW, "Administrator"))

conn.commit()

def cnt(t): return cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
def sum_col(t, col): return cur.execute(f"SELECT COALESCE(SUM({col}),0) FROM {t}").fetchone()[0]

print("=" * 55)
print("  ZZCC OA — 演示数据填充完成")
print("=" * 55)
print(f"  财务：{cnt('accounts')} 账户 | {cnt('journal_entries')} 日记账 | {cnt('expense_claims')} 报销单")
print(f"  人事：{cnt('employees')} 员工")
print(f"  CRM： {cnt('leads')} 线索 | {cnt('opportunities')} 商机")
print(f"  项目：{cnt('projects')} 项目 | {cnt('tasks')} 任务")
print(f"  采购：{cnt('suppliers')} 供应商 | {cnt('purchase_orders')} 采购订单")
print(f"  合同：{cnt('contracts')} 合同")
print(f"  客服：{cnt('support_tickets')} 工单")
print(f"  质检：{cnt('quality_inspections')} 质检报告")
print(f"  库存：{cnt('items')} 物料 | {cnt('stock_entries')} 库存流水")
print(f"  资产：{cnt('assets')} 固定资产")
total_stock = sum_col("items", "opening_stock * val_rate")
print(f"\n  库存总值：¥{total_stock:,.2f}")
print(f"  DB: {DB_PATH}")
print("=" * 55)
conn.close()
