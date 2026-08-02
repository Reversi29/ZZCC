# ZZCC OA 系统

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                   Apple Silicon Mac                   │
│                                                      │
│   ┌─────────────┐     ┌──────────────────────────┐ │
│   │  前端 SPA   │────▶│  FastAPI 后端（ARM原生）  │ │
│   │  nginx:8080 │     │  uvicorn :8000 (host)    │ │
│   └─────────────┘     └────────────┬─────────────┘ │
│                                    │                │
│                         ┌──────────┴──────────┐    │
│                         │                     │    │
│                    ┌────▼────┐     ┌────────▼───┐ │
│                    │ MariaDB │     │ Redis      │ │
│                    │ :3307   │     │ (QEMU)     │ │
│                    └─────────┘     └────────────┘ │
└─────────────────────────────────────────────────────┘
```

## 快速启动

### 1. 启动后端（FastAPI，ARM 原生）
```bash
cd backend
API_KEY=zzcc_oadev_key_2024 python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. 启动前端（nginx）
```bash
docker compose -f docker-compose-arm.yml up -d
# 访问 http://localhost:8080
```

### 3. API 文档
- FastAPI 文档：http://localhost:8000/docs
- Redoc：http://localhost:8000/redoc

## 业务模块

| 模块 | 说明 |
|------|------|
| CRM | 线索 / 联系 / 商机 |
| 项目运营 | 项目 / 任务管理 |
| 采购 | 采购订单 / 供应商 |
| 财务 | 日记账 / 付款单 / AI 发票分类 |
| 法务合规 | 合同管理 / AI 条款风险扫描 |
| 客服 | 工单管理 |
| 质量测试 | 来料 / 过程 / 成品检验 |
| 人力资源 | 员工管理 |
| 资产行政 | 物料 / 库存 |
| AI 咨询 | 10 个模块业务规则引擎 |

## API 认证
所有 API 请求需携带：
```
X-Api-Key: zzcc_oadev_key_2024
```

## 关键文件

```
backend/
  main.py              FastAPI 入口
  config.py            配置加载
  models/documents.py 15 个 Pydantic 模型（对齐 ERPNext v15 字段）
  routers/             10 个业务模块路由

ai/
  prompts/             10 个模块的提示词模板
  main.py              AI 咨询引擎
  llm_client.py        LLM 调用客户端

scripts/modules/
  crm_automation.py    CRM 自动规则
  finance_rules.py     财务规则引擎
  compliance_rules.py  合规规则引擎
  procurement_rules.py 采购规则引擎
  quality_rules.py     质检规则引擎
```

## 为什么放弃 ERPNext Docker？

ERPNext 官方 `frappe/erpnext:v15` 镜像为**纯 x86_64**，在 Apple Silicon M4 Mac 上通过 QEMU 用户态模拟运行存在以下问题：

- `bench new-site`：34% 处 SIGSEGV 稳定崩溃
- `pip install frappe`：在 macOS Python 环境下永久挂起
- `frappe/erpnext-nginx:v15`：镜像不存在
- `redis:7-alpine`（ARM）：在 QEMU 下崩溃

**解决方案**：用 FastAPI 编写完全对齐 ERPNext v15 REST API 协议的后端，ARM 原生运行，无 QEMU 依赖，性能更好。
