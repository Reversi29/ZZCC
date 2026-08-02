# ZZCC OA — 技术构建文档
> 记录从 ERPNext Docker 到 FastAPI 原生 ARM 方案的全过程

**最后更新：2026-07-30**

## 背景

用户要求基于 ERPNext/Odoo（开源 ERP）搭建 ZZCC OA 系统，覆盖 10 条业务线。

## ❌ 方案一：ERPNext Docker（失败）

### 问题列表

| 问题 | 根因 | 影响 |
|------|------|------|
| `frappe/erpnext-nginx:v15` 不存在 | 镜像名错误 | nginx 启动失败 |
| `redis:7-alpine` ARM QEMU 崩溃 | ARM + QEMU + Redis 7 不兼容 | Redis 容器无法运行 |
| `bench new-site` SIGSEGV @ 34% | QEMU DocType 同步层崩溃 | 站点创建失败 |
| `pip install frappe/bench` macOS 挂起 | frappe setup.py 依赖解析死锁 | 无法安装 frappe |
| `frappe/erpnext:v15` 纯 x86 镜像 | 官方未提供 ARM 变体 | QEMU 转译性能差且不稳定 |

### 关键日志

```
# bench new-site 崩溃
Signal: SIGSEGV
Address: 0x7f8000000000
# DocType sync 阶段 34%
```

### 为什么 Odoo 也有风险

用户最初担忧 Odoo 企业版锁功能（License Check），要求 ERP 选型评估：
- Odoo 企业版有技术锁（License Check）
- ERPNext 100% 开源（GPL v3），无后顾之忧
- 最终 ERPNext Docker 在 Apple Silicon 不可行，改用 FastAPI

## ✅ 方案二：FastAPI 原生 ARM

### 技术决策

1. **完全对齐 ERPNext v15 REST API 协议**，字段名、端点路径、响应格式一一对应
2. **Pydantic 模型**完全匹配 ERPNext 标准字段结构
3. **保留 Docker MariaDB**，后续可直接对接 SQL 数据持久化
4. **FastAPI 替换 Frappe 后端**，无 QEMU 依赖，ARM 原生性能

### 目录结构

```
/Users/mac/ZZCC/OA/
├── backend/
│   ├── main.py              FastAPI 应用入口
│   ├── config.py            环境变量配置（API Key / Redis / MariaDB）
│   ├── models/
│   │   └── documents.py     15 个 Pydantic 模型
│   └── routers/
│       ├── crm.py           线索 / 联系 / 商机
│       ├── project.py       项目 / 任务
│       ├── procurement.py   采购订单 / 供应商
│       ├── finance.py       日记账 / 付款单 / AI 发票分类
│       ├── compliance.py    合同 / AI 条款扫描
│       ├── customer_service.py  工单
│       ├── quality.py       质检
│       ├── hr.py           员工
│       ├── stock.py         物料 / 库存
│       └── ai.py            10 模块 AI 咨询引擎
├── ai/
│   ├── prompts/             10 个业务模块提示词模板
│   ├── main.py              AI 咨询入口
│   └── llm_client.py        OpenAI / 本地 LLM 客户端
├── frontend/
│   ├── index.html           SPA（Vue-free 纯 JS）
│   └── nginx.conf           nginx 代理配置
├── scripts/modules/
│   ├── crm_automation.py    线索评分 / 自动化规则
│   ├── finance_rules.py     财务合规规则
│   ├── compliance_rules.py  合规检查
│   ├── procurement_rules.py 采购比价规则
│   └── quality_rules.py     质检判定
├── docker-compose-arm.yml   ARM 原生部署（nginx 前端 + MariaDB）
└── README.md
```

### API 端点对照（ERPNext v15 兼容）

| 模块 | 端点 | 方法 |
|------|------|------|
| Lead | `/api/resource/Lead` | GET/POST |
| Contact | `/api/resource/Contact` | GET/POST |
| Opportunity | `/api/resource/Opportunity` | GET/POST |
| Project | `/api/resource/Project` | GET/POST/DELETE |
| Task | `/api/resource/Task` | GET/POST/DELETE |
| Purchase Order | `/api/resource/Purchase Order` | GET/POST |
| Supplier | `/api/resource/Supplier` | GET/POST |
| Journal Entry | `/api/resource/Journal Entry` | GET/POST |
| Payment Entry | `/api/resource/Payment Entry` | GET/POST |
| Contract | `/api/resource/Contract` | GET/POST/DELETE |
| Support Ticket | `/api/resource/Support Ticket` | GET/POST |
| Quality Inspection | `/api/resource/Quality Inspection` | GET/POST |
| Employee | `/api/resource/Employee` | GET/POST/DELETE |
| Item | `/api/resource/Item` | GET/POST/DELETE |
| Stock Entry | `/api/resource/Stock Entry` | GET/POST |
| AI 咨询 | `/api/ai/consult` | POST |
| AI 发票分类 | `/api/resource/ai/classify_invoice` | POST |
| AI 合同扫描 | `/api/resource/ai/contract_scan` | POST |

## 第三轮：数据持久化（SQLAlchemy + SQLite）

### 技术决策
- **MariaDB 放弃原因**：pip 无法从 PyPI 下载 `pymysql`/`sqlalchemy`（网络超时），换源仍超时
- **改用 SQLite**：Python 内置 `sqlite3`，零依赖，突破网络限制；MariaDB 容器保留备用
- **切换 MariaDB 只需改一行**：`DB_URL = "mysql+pymysql://root:zzcc_oa_2024@127.0.0.1:3307/zzcc_oa"`

### 架构变化
```
内存 dict  →  SQLAlchemy ORM  →  SQLite (data/zzcc_oa.db)
                              →  MariaDB（未来，一行配置切换）
```

### 新增文件
- `database.py`（10703 字节）：所有模型（Account/Employee/Lead/Contact/Opportunity/Project/Task/Supplier/PurchaseOrder/JournalEntry/PaymentEntry/ExpenseClaim/Contract/QualityInspection/SupportTicket/Item/StockEntry/Asset），`init_db()` 建表，`get_db()` 依赖注入
- `routers/_db.py`：序列号生成（`seq_for`）、模型↔字典序列化（`model_to_dict`）、doctype 注册表

### 持久化验证
```bash
✅ 重启后端后数据不丢（直接读 SQLite 文件确认）
✅ 报销单 EXP-0001（赵六 ¥4800）重启后仍在
✅ 账户 ACC-0001 余额 500000 重启后正确
✅ 全链路：前端(8080) → nginx → 后端(8000) → SQLite
```

### 审批工作流（2026-07-31）

覆盖三种单据的全生命周期状态流转。

**状态机**：
```
ExpenseClaim:   Draft → Submitted → Approved → Paid
PurchaseOrder:  Draft → Submitted → Approved → Ordered → Received
JournalEntry:   Draft → Submitted → Approved / Rejected
```

**后端端点**（`backend/routers/workflow.py`）：
| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/workflow/pending` | GET | 所有 Submitted 单据，含可用动作 |
| `/api/workflow/action` | POST | 执行状态流转（submit/approve/reject/pay/order/receive） |
| `/api/workflow/doc/{doctype}/{name}` | GET | 单据详情 + 当前可用动作 |
| `/api/workflow/stats` | GET | 各模块状态统计 |

**前端**：`index.html` 新增「审批」导航模块，三 Tab：
1. **待审批** — 按单据类型分组，金额 + 审批按钮
2. **统计** — 各状态数量彩色展示
3. **我的单据** — 个人单据列表 + 详情页

**已知约束**：
- JournalEntry `docstatus` 是整数（0/1/2/3），其他单据是字符串状态
- 前端 doctype camelCase（如 `ExpenseClaim`）→ API 空格路径（如 `Expense%20Claim`）通过 `DOCTYPE_API` 映射表转换
- 表名使用 snake_case（`expense_claims` / `purchase_orders`）

### 后续切换 MariaDB 步骤
```python
# database.py 改一行即可
DB_URL = "mysql+pymysql://root:zzcc_oa_2024@127.0.0.1:3307/zzcc_oa"
# 需先装 pymysql：pip install pymysql
```

---

## 第二轮完善（财务/采购/行政/UI）

### 新增模型
- `Account`（账户：Asset/Liability/Equity/Income/Expense + 余额）
- `ExpenseClaim`（报销单：类型/金额/审批状态/用途）
- `Asset`（固定资产：类别/原值/保管人/位置/状态）
- `PurchaseOrder` 增加 `total` 字段（行项目金额自动汇总）

### 新增/增强端点
| 端点 | 说明 |
|------|------|
| `POST/GET/PUT/DELETE /api/resource/Account` | 账户 CRUD |
| `POST/GET/PUT/DELETE /api/resource/Expense Claim` | 报销单 CRUD |
| `POST/GET/PUT/DELETE /api/resource/Asset` | 资产 CRUD |
| `POST /api/resource/Journal Entry` | 借贷平衡校验（借方≠贷方拒绝） |
| `POST /api/resource/Purchase Order` | 行项目金额自动计算 total |
| `GET /api/resource/finance_summary` | 账户数/借贷合计/待审批报销汇总 |
| `GET /api/resource/stock_summary` | 库存种类/总值/流水/资产汇总 |
| `GET /api/resource/low_stock` | 低于安全库存预警 |
| `POST /api/resource/ai/po_consult` | 采购 AI 咨询（价格/供应商/交期风险） |

### 前端重构（API 驱动）
- **统一数据层**：所有列表由 API 实时加载，不再用前端内存 store（刷新不丢、可跨客户端）
- **财务中心**（多 Tab）：汇总 / 账户 / 日记账（含分录子表） / 收付款 / 报销 / 发票分类
- **采购中心**（多 Tab）：采购订单（含明细子表） / 供应商 / AI 咨询
- **资产行政中心**（多 Tab）：物料 / 库存流水 / 固定资产 / 库存汇总 / 低库存预警
- **子表编辑器**：items / accounts 支持动态添加/删除行
- **统计卡片**：财务/库存汇总可视化

### 业务校验示例
```
✅ PO 行项目金额自动汇总: 10×5000 + 20×200 = 54000
✅ JE 借贷不平衡拒绝: 借100 / 贷50 → 400 错误
✅ 低库存预警: A4打印纸 5盒 < 安全10盒 → warning
```

## 部署结果

### 服务状态（最终）

```
zzcc-oa-frontend    Up  healthy  0.0.0.0:8080->80/tcp
zzcc-oa-mariadb     Up  healthy  0.0.0.0:3307->3306/tcp
FastAPI backend     Up  -       0.0.0.0:8000->8000/tcp (host native)
```

### 测试结果

```
✅ GET  /                             → {"name":"ZZCC OA System","status":"running"}
✅ GET  /api/status                    → {"status":"ok","modules":[...10个模块]}
✅ POST /api/resource/Lead            → {"data":{"name":"Lead-0001"},"message":"created"}
✅ POST /api/resource/ai/contract_scan → {"risk_level":"high","findings":[...],"risk_count":3}
✅ POST /api/resource/ai/classify_invoice → {"category":"IT基础设施","confidence":"auto"}
✅ POST /api/ai/consult               → {"advice":"...","risk_flags":[],"suggestions":[...]}
✅ GET  http://localhost:8080/         → 200 (nginx → index.html)
✅ GET  http://localhost:8080/api/status → 200 (nginx → FastAPI :8000)
```

## 数据模型（部分）

### Lead
```python
class Lead(BaseModel):
    name: Optional[str] = None
    lead_name: str
    company_name: Optional[str] = None
    email_id: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None  # 官网/展会/推荐/广告/其他
    lead_status: LeadStatus = LeadStatus.NEW
    docstatus: DocStatus = DocStatus.DRAFT
```

### Project
```python
class Project(BaseModel):
    name: Optional[str] = None
    project_name: str
    status: ProjectStatus = ProjectStatus.OPEN
    priority: Priority = Priority.MEDIUM
    percent_complete: Optional[float] = 0
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    docstatus: DocStatus = DocStatus.DRAFT
```

## AI 咨询引擎原理

无需外部 API 的本地规则引擎：

1. **规则库**：每个模块独立的 `rules.py`，定义业务规则
2. **评分函数**：输入上下文 → 输出评分 + 建议 + 风险标记
3. **提示词模板**：结构化 prompt 模板，支持外部 LLM 增强
4. **结果归一化**：统一返回 `{advice, score, risk_flags, suggestions}`

示例（采购咨询）：
```python
# 输入
{"module": "procurement", "context": {"amount": 200000, "supplier": "华X供应商"}}
# 输出
{"advice": "采购金额 200000 元，供应商：华X供应商",
 "risk_flags": [], "suggestions": ["建议要求3家供应商比价"], "score": 60}
```

合同风险扫描（正则规则）：
```python
# 高风险模式
r"违约金\s*[=:]\s*\d{2,}%.*"
r"永久.*保密"
r"自动续期"
r"深圳仲裁委"
# 结果
{"risk_level": "high", "risk_count": 3, "findings": [...]}
```

---

## 最终交付状态（2026-07-30）

### 系统架构

```
浏览器 → nginx:8080 → FastAPI:8000 → SQLite:data/zzcc_oa.db (156KB+)
                          ↓
                      Redis / MariaDB（可选）
```

### 已实现功能

| 模块 | 端点 | 功能 |
|------|------|------|
| 财务 | `/Account` `/Journal Entry` `/Payment Entry` `/Expense Claim` | CRUD + 借贷平衡校验 + 汇总 |
| 发票分类 | `/ai/classify_invoice` | 关键词/供应商智能分类 |
| CRM | `/Lead` `/Contact` `/Opportunity` | 线索/商机全生命周期 |
| 项目 | `/Project` `/Task` | 项目 + 任务管理 |
| 采购 | `/Purchase Order` `/Supplier` | PO 自动汇总 + AI 咨询 |
| 合同 | `/Contract` | 合同全生命周期 |
| 客服 | `/Support Ticket` | 工单管理 |
| 质检 | `/Quality Inspection` | 来料/出货质检 |
| 人事 | `/Employee` | 员工管理 |
| 库存 | `/Item` `/Stock Entry` `/Asset` | 物料/资产 CRUD |
| 库存预警 | `/low_stock` | 低库存报警 |
| 财务汇总 | `/finance_summary` | 全模块汇总 |

### 演示数据（seed_data.py 填充）

- 8 账户 / 3 日记账 / 4 报销单
- 4 线索 / 3 商机（总金额 ¥780,000）
- 3 项目 / 4 任务
- 3 供应商 / 3 采购订单（总金额 ¥342,750）
- 3 合同 / 3 工单 / 3 质检报告
- 5 物料（库存总值 ¥387,060）/ 4 固定资产
- 5 员工

### 待完成（Docker Compose）

- `docker compose up --build` 需 Docker Hub 畅通（当前 Docker Hub 访问不稳定）
- `mariadb:10.8` 镜像需从 `arm64v8/mariadb:10.8` 切换
- 切换 MariaDB 后端：改 `database.py` 一行 `DB_URL`，`pip install pymysql`

### 启动方式

```bash
cd /Users/mac/ZZCC/OA
./start.sh dev     # dev 模式：后端 host 模式直启
python3 seed_data.py  # 填充演示数据（一次性）

# prod 模式（需 Docker Hub 畅通）
./start.sh prod
```

