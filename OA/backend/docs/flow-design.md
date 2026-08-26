# ZZCC OA 业务流编排系统 — 设计文档

## 1. 概述

低代码可视化业务流编排引擎。支持：
1. **手动编排**：画布拖拽定义节点/边，保存为模板
2. **AI 自动编排**：自然语言目标 → 规则/LLM 生成流程模板
3. **执行引擎**：同步执行实例，支持人工审批挂起、AI Agent、内联循环

---

## 2. 数据模型

5 张表（`backend/models/flow.py`），均继承 `Timestamped` mixin（含 `creation`/`modification` 列）。

| 表 | 主键 | 说明 |
|----|------|------|
| `flow_templates` | id | 可复用的流程模板。`config` 存 JSON（nodes + edges）。`name` UNIQUE，`published` 布尔标记 |
| `flow_instances` | id | 一次执行实例。`status`（pending/running/suspended/complete/failed）、`current_step`（suspended 时记录卡住的节点 ID）、`trigger_type`（manual/ai/webhook/cron） |
| `flow_nodes` | id | 实例中的执行节点。`node_type`、`status`、`config`/`input_data`/`output_data`（均 JSON TEXT）、`parent_node_id`（自引用） |
| `flow_edges` | id | 节点间连接。`source_id`/`target_id` 外键到 flow_nodes，`condition` 分支标签（true/false/default） |
| `flow_agent_logs` | id | Agent 节点执行日志（prompt/response/tool_calls） |

**关系**：
- `FlowTemplate.instances` cascade `delete-orphan`
- `FlowInstance.nodes` cascade `delete-orphan`，`order_by="FlowNode.creation"`
- `FlowNode.parent` self-referencing（loop 场景下记录逻辑父子关系）

---

## 3. 节点类型（12 种 × 5 类）

`models/flow.py` 中 `FLOW_NODE_TYPES` / `FLOW_NODE_CATEGORIES` 常量，前后端共享单数据源。

| 类别 | 节点 | config 关键字段 |
|------|------|----------------|
| terminal | start / output | — |
| io | input / webhook | fields[], url, method, payload |
| action | action / http / notify | method/path/body, url, channels/message |
| control | decision / loop / approve / delay | condition, iterations/body_nodes, approver_role, duration |
| ai | agent | prompt, module |

**Loop 节点 `body_nodes` 是内联定义**：

```json
{
  "type": "loop",
  "config": {
    "iterations": 3,
    "variable": "i",
    "body_nodes": [
      {"type": "decision", "label": "检查", "config": {"condition": "i > 0"}},
      {"type": "action", "label": "查询", "config": {"method": "GET", "path": "/api/resource/X"}}
    ]
  }
}
```

引擎创建临时 `_LoopNode` 对象（非 DB 记录）逐次执行，不查 `flow_nodes` 表。

---

## 4. 执行引擎

### 4.1 主流程

```
execute_instance():
  1. 设置 instance.status = "running"
  2. 构建邻接表 adj[node_id] = [edges]
  3. 找到 start 节点（或首个节点）作为 current_id
  4. while current_id 有效:
       a. result = _execute_node(db, node, context, dry_run)
       b. if result.branch → context["_branch"] = result.branch
       c. if decision + decision_result → context["decision_result"] = result.output.decision
       d. 更新 node.status / input_data / output_data / error → commit
       e. 记录 step
       f. 终止判断:
          - output 节点或 status=complete → instance.complete, 返回
          - status=suspended → instance.suspended, 返回（等待外部 approve）
          - status=failed → instance.failed, 返回
       g. current_id = _next_node(db, current_id, adj, nodes, context)
       h. loop_count 上限 200，超出 → failed
```

### 4.2 `_next_node` 三级优先级

1. **显式匹配**：`context["_branch"] == edge.condition`（字符串精确匹配）
2. **默认边**：`condition` 为 `None` / `"default"` / `"true"`
3. **兜底**：按 `weight` 排序的第一条出边

### 4.3 `_execute_node` 各类型行为

| 节点 | 行为 |
|------|------|
| start/output | 返回 `{status:done, output:{complete:true}}` |
| input | 返回 suspended，等待外部数据 |
| decision | `eval(condition, {}, context)` 求值，返回 `{branch:"true"/"false"}` |
| loop | 解析 iterations/variable/body_nodes → 逐次迭代创建临时节点 → 收集 body_steps |
| approve | 返回 suspended，等待审批 |
| agent | dry_run → 模拟返回；否则调 `call_internal_api("POST", "/api/ai/consult", ...)` |
| action | dry_run → 参数回显；否则调 `call_internal_api(method, path, body)`，结果注入 `context[ctx_key]` |
| http | dry_run → 参数回显；否则 `urllib.request.urlopen` 发请求，结果注入 context |
| notify | 调 `push_external(message, context)` 发送通知 |
| delay | dry_run → 跳过；否则 `time.sleep(min(duration/1000, 60))` |
| webhook | dry_run → 参数回显；否则 POST payload 到外部 URL |

**dry_run 模式**：跳过所有真实外部调用（AI/HTTP/webhook/通知/延迟），仅验证节点链路逻辑。

### 4.4 `call_internal_api`

```
OA_API_BASE_URL (env, 默认 http://localhost:8003) + path
POST/GET, Content-Type: application/json
X-API-Key 头从 OA_API_KEY (env, 默认 zzcc_oadev_key_2024)
urllib.request.urlopen, timeout=30s
返回 {status, body} 或 {status, error} 或 {error}
```

---

## 5. 状态机

### 实例状态

```
pending → running → complete
                → suspended → running → complete
                → failed
```

- `suspended`：`approve`/`input` 触发，`current_step` 记录卡住的 node.id
- 恢复：`POST /instances/{id}/approve` → running
- 取消：`POST /instances/{id}/cancel` → failed

### 节点状态

`pending` → `done` / `skipped` / `failed`

---

## 6. AI 编排

`POST /api/flow/build` 端点，两阶段：

1. **规则引擎**：`goal` 关键词匹配预定义模板
   - 审批类（"审批"/"报销"/"采购"）→ 金额判断 + 分级审批
   - 招聘类（"招聘"/"hire"/"面试"）→ 需求→AI 生成 JD→创建记录→HR 审批
   - 工单类（"工单"/"ticket"/"客服"）→ 创建→优先级判断→主管审批→分派
2. **LLM 引擎**（规则未命中时）：`auto_approval._get_llm()` + system prompt 约束 JSON 输出

---

## 7. API 端点（14 个，prefix `/api/flow`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/node-types` | 12 种节点类型 + schema（前端画布） |
| GET | `/templates` | 模板列表（支持 category/published/search 过滤） |
| GET | `/templates/{id}` | 单个模板 |
| POST | `/templates` | 创建模板 |
| PUT | `/templates/{id}` | 更新模板 config |
| DELETE | `/templates/{id}` | 删除模板 |
| POST | `/templates/{id}/publish` | 发布模板 |
| GET | `/instances` | 实例列表 |
| GET | `/instances/{id}` | 实例详情（含 nodes/edges） |
| POST | `/instances` | 从模板创建实例 |
| POST | `/instances/{id}/execute` | 执行实例 |
| POST | `/instances/{id}/approve` | 审批通过 |
| POST | `/instances/{id}/cancel` | 取消实例 |
| POST | `/build` | AI 自动生成流程模板 |

---

## 8. 前端画布

`/flow-designer` 路由，SVG 网格画布。

### 关键函数（`app.js`）

| 函数 | 说明 |
|------|------|
| `renderFlowDesigner` | 初始化画布（左节点面板 + 中网格 + 右属性面板） |
| `FLOW_saveTemplate` | 保存/更新模板 |
| `FLOW_createInstance` | 从画布创建实例 |
| `FLOW_executeInstance` | 执行 + 实时进度模态框 |
| `FLOW_viewInstance` | 查看结果（loop body_steps 展开） |
| `FLOW_exportJson` / `FLOW_importJson` | JSON 导入导出 |
| `FLOW_buildAI` | 调用 AI 编排 |

---

## 9. 部署 & 运维

### Docker 容器（6 个）

`zzcc-oa-mariadb`(3307) / `zzcc-oa-backend`(8003) / `zzcc-oa-nginx`(8080) / `zzcc-oa-redis`(6379) / `zzcc-casdoor`(8004) / `zzcc-casdoor-postgres`(5432)

### 代码部署（已知痛点）

`docker cp` 对 bind mount 文件返回 "device or resource busy"，但文件内容实际已更新。用 `docker cp file.container:/path/.tmp && mv .tmp file` 重命名绕过句柄锁定。

### Nginx 关键配置

```nginx
location /api/ {
    proxy_pass http://backend:8003;
    proxy_set_header X-API-Key $http_x_api_key;  # 必须！否则 require_auth 401
}
```

### 测试

全量 `pytest`：208 passed, 0 failed。`conftest.py` 需注入 `API_KEY`/`JWT_SECRET_KEY`/`OAUTH_CLIENT_ID` 等环境变量，否则 `get_settings()` 默认值 `CHANGE_ME_API_KEY` 导致 X-API-Key 认证 401。