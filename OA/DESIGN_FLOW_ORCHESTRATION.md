# 业务流编排系统（Flow Orchestration）设计文档

## 目录

1. [系统架构](#1-系统架构)
2. [核心概念模型](#2-核心概念模型)
3. [后端执行引擎](#3-后端执行引擎)
4. [API 接口](#4-api-接口)
5. [前端画布编辑器](#5-前端画布编辑器)
6. [AI 自主编排](#6-ai-自主编排)
7. [节点类型规范](#7-节点类型规范)
8. [数据流与状态机](#8-数据流与状态机)
9. [部署与运维](#9-部署与运维)
10. [扩展路线图](#10-扩展路线图)

---

## 1. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     前端 (app.js)                            │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐     │
│  │ 节点面板   │  │  SVG 画布编辑器 │  │ 属性配置面板     │     │
│  └──────────┘  └──────────────┘  └──────────────────┘     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 执行进度面板 (flow-modal + flow-exec-steps)          │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP + X-API-Key
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    后端 (FastAPI)                            │
│                                                            │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ routers/    │  │ services/        │  │ models/      │  │
│  │ flow.py     │→ │ flow_engine.py   │→ │ flow.py      │  │
│  │ (14 端点)   │  │ (执行引擎)        │  │ (5 ORM 表)   │  │
│  └─────────────┘  └──────────────────┘  └──────────────┘  │
│         │                  │                                  │
│         │                  ├── call_internal_api()            │
│         │                  │    → /api/resource/*             │
│         │                  │    → /api/audit-log             │
│         │                  │    → /api/notifications/...      │
│         │                  │    → /api/wecom/webhook          │
│         │                  │                                  │
│         │                  ├── agent → /api/ai/consult       │
│         │                  ├── webhook → urllib (外部)       │
│         │                  ├── http → urllib (外部)          │
│         │                  └── delay → time.sleep            │
│         │                                                     │
│         ▼                                                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              AI Build 引擎                            │    │
│  │  ┌──────────────┐  ┌────────────────────────────┐  │    │
│  │  │ 规则引擎      │  │ LLM 引擎 (可选)             │  │    │
│  │  │ 关键词匹配    │  │ 自然语言 → 节点序列          │  │    │
│  │  │ → 节点+边     │  │ (接入 LLM 后)               │  │    │
│  │  └──────────────┘  └────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    MariaDB (MariaDB 10.8)                   │
│                                                            │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ flow_templates │  │ flow_instances │  │ flow_nodes   │  │
│  │ (12 cols)      │  │ (15 cols)      │  │ (13 cols)    │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
│  ┌────────────────┐  ┌────────────────┐                   │
│  │ flow_edges     │  │ flow_agent_logs│                   │
│  │ (9 cols)       │  │ (11 cols)      │                   │
│  └────────────────┘  └────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### 1.1 设计原则

- **模板 / 实例分离**：模板是静态设计时的定义，实例是运行时的一次执行记录
- **图数据结构**：节点（Node）+ 有向边（Edge）构成流程 DAG，支持分叉但不支持环
- **上下文传递**：跨节点 `context` 字典持久化到 `FlowInstance.context_json`，每个节点的 output 写入后下一节点可读
- **分支决策**：decision 节点计算 condition 后将结果写入 `context["_branch"]`，后续边匹配该值
- **内联子图**：loop 节点的 `body_nodes` 是逻辑子节点定义（非 DB 引用），在迭代时创建临时 `_LoopNode` 执行

---

## 2. 核心概念模型

### 2.1 FlowTemplate — 流程模板

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str (PK) | 模板名称（主键） |
| `title` | str | 展示标题 |
| `description` | str | 描述 |
| `category` | str | 分类标签 |
| `nodes` | JSON | 节点定义列表（画布坐标 + 配置） |
| `edges` | JSON | 边定义列表（source/target/condition/label） |
| `version` | int | 版本号 |
| `is_published` | bool | 是否已发布（只有已发布的可执行） |
| `is_default` | bool | 是否默认模板 |
| `metadata_json` | JSON | 扩展元数据 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

**设计决策**：
- 节点/边在模板中以 JSON 形式整体存储（而非外键关系），模板版本演进时历史 JSON 不变
- `is_published` 作为发布门控：开发中的模板不能执行实例

### 2.2 FlowInstance — 流程实例

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str (PK) | 实例编号（如 `FLW-20260826-0001`） |
| `template_name` | str (FK) | 关联模板 |
| `trigger_type` | str | `manual` / `cron` / `event` / `callback` |
| `trigger_context` | JSON | 触发时的业务数据 |
| `status` | str | 状态机：`pending` / `running` / `completed` / `failed` / `suspended` |
| `execution_log_json` | JSON | 逐步执行日志（含 body_steps 子步骤） |
| `context_json` | JSON | 跨节点共享上下文 |
| `started_at` | datetime | 开始执行时间 |
| `completed_at` | datetime | 完成时间 |
| `elapsed_ms` | int | 执行耗时（毫秒） |
| `created_at` / `updated_at` | datetime | 审计时间戳 |

**状态机**：

```
     ┌─────────────────────────────────┐
     │            pending              │
     └────────────┬────────────────────┘
                  │ execute()
                  ▼
     ┌─────────────────────────────────┐
     │            running              │
     └──┬──────────┬──────────┬───────┘
        │          │          │
   (全部完成)  (遇异常)   (需审批)
        │          │          │
        ▼          ▼          ▼
   ┌──────┐  ┌──────┐  ┌───────────┐
   │completed│ │failed│ │ suspended │
   └──────┘  └──────┘  └────┬──────┘
                            │ approve/reject
                            ▼
                    ┌──────────────┐
                    │   running    │ (重新进入)
                    └──────────────┘
```

### 2.3 FlowNode — 实例节点

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID (PK) | 节点唯一 ID |
| `instance_name` | str (FK) | 关联实例 |
| `template_node_id` | str | 模板中节点的 ID |
| `type` | str | 节点类型（12 种，见 §7） |
| `label` | str | 展示标签 |
| `config` | JSON | 节点配置（URL、body、field 等） |
| `status` | str | `pending` / `running` / `done` / `failed` / `skipped` / `suspended` |
| `output` | JSON | 节点输出结果 |
| `error` | str | 失败原因 |
| `duration_ms` | int | 执行耗时 |
| `started_at` / `completed_at` | datetime | 执行时间 |
| `created_at` | datetime | 创建时间 |

**设计决策**：
- 执行时实例节点是模板节点的运行时投影（`template_node_id` 关联）
- `output` 和 `error` 在执行过程中持续刷新，支持调试

### 2.4 FlowEdge — 边

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID (PK) | |
| `instance_name` | str (FK) | |
| `source_node_id` | str | 源节点 |
| `target_node_id` | str | 目标节点 |
| `condition` | str | 分支条件（`default` / `true` / `false` / 任意字符串） |
| `label` | str | 边标签 |
| `created_at` | datetime | |

### 2.5 FlowAgentLog — 节点执行审计

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID (PK) | |
| `instance_name` | str | |
| `node_id` | str | |
| `action` | str | 执行动作 |
| `input_snapshot` | JSON | 输入快照 |
| `output_snapshot` | JSON | 输出快照 |
| `duration_ms` | int | |
| `status` | str | |
| `error` | str | |
| `created_at` | datetime | |

---

## 3. 后端执行引擎

### 3.1 执行流程

```
POST /api/flow/template/{name}/instance
        │
        ▼
create_instance()
  1. 创建 FlowInstance (status=pending)
  2. 遍历模板 nodes JSON，创建 FlowNode 记录 (status=pending)
  3. 遍历模板 edges JSON，创建 FlowEdge 记录
  4. 返回实例编号

POST /api/flow/instance/{name}/execute?dry_run=true|false
        │
        ▼
execute_instance()
  1. 找到 start 节点 → next_id = start_node_id
  2. 主循环 (while next_id, 最大 200 步):
       a. 更新节点 status=running, started_at
       b. 调用 _execute_node(node, context, dry_run)
       c. 写入节点 output / duration_ms
       d. 如果 result 含 "branch" → context["_branch"] = result["branch"]
       e. 如果节点返回 "next" → next_id = result["next"]（硬编码跳转）
       f. 否则 next_id = _next_node(current_node_id, edges)
       g. 更新节点 status=done
       h. 如果 status=failed → 实例失败，退出循环
       i. 如果 status=suspended → 实例暂停，等待外部审批
  3. 更新实例 status=completed/failed/suspended, completed_at, elapsed_ms
```

### 3.2 核心函数

#### `execute_instance(instance, dry_run=False)`

- **循环上限**：200 步，防止无限循环
- **context 持久化**：每次迭代将最新 context 写入 `instance.context_json`
- **异常隔离**：单个节点异常不中断全局流程（dry_run 模式下静默吞异常）

#### `_execute_node(node, context, dry_run=False) → dict`

按节点类型分发到对应的内部 `_execute_*` 函数。

| 节点类型 | 函数 | dry_run 行为 |
|----------|------|-------------|
| `start` | `_execute_start` | 直接返回 `{"status":"done","output":{}}` |
| `decision` | `_execute_decision` | 仍计算条件（用于 preview） |
| `action` | `_execute_action` | 跳过 `call_internal_api`，返回预览数据 |
| `agent` | `_execute_agent` | 跳过 LLM 调用 |
| `http` | `_execute_http` | 跳过 urllib 请求 |
| `webhook` | `_execute_webhook` | 跳过 urllib POST |
| `notify` | `_execute_notify` | 跳过 `push_external` 真实推送 |
| `delay` | `_execute_delay` | 跳过 `time.sleep`，立即返回 |
| `approve` | `_execute_approve` | 返回 `{"status":"suspended"}` |
| `output` | `_execute_output` | 直接返回 |
| `loop` | `_execute_loop` | **不跳过迭代**，在内部节点用 dry_run |
| `manual` | `_execute_manual` | 返回 `{"status":"suspended"}` |

#### `_next_node(current_id, edges) → str|None`

三级优先级：

1. **显式匹配**：遍历 edges，若 `edge.condition == context.get("_branch")` 则返回 `edge.target_node_id`
2. **默认边**：condition 为 `"default"` 或 `"true"` 的边
3. **兜底**：返回第一条边的目标

#### `_execute_loop(node, context, dry_run) → dict`

```python
def _execute_loop(node, context, dry_run):
    cfg = node.config
    iterations = cfg.get("iterations", 1)
    variable = cfg.get("variable", "i")
    ctx_key = cfg.get("ctx_key", "loop_result")
    body_nodes = cfg.get("body_nodes", [])

    result = {"status": "done", "output": {}}

    if not body_nodes:
        result["output"]["loops"] = 0
        result["output"]["body_steps"] = []
        return result

    body_steps = []

    for i in range(iterations):
        context[variable] = i  # 设置循环变量
        for bdef in body_nodes:
            # 创建临时节点对象
            ln = _LoopNode(
                id=str(uuid.uuid4()),
                type=bdef["type"],
                label=bdef.get("label", bdef["type"]),
                config=bdef.get("config", {}),
                status="pending",
                output=None,
                error=None,
                duration_ms=0,
            )
            r = _execute_node(ln, context, dry_run)
            body_steps.append({
                "iteration": i,
                "node_type": ln.type,
                "node_label": ln.label,
                "status": r.get("status", "done"),
                "output": r.get("output"),
            })
            if r.get("status") == "failed":
                break

    result["output"] = {
        "iterations": iterations,
        "variable": variable,
        "body_steps": body_steps,
    }
    return result
```

### 3.3 内部 API 调用 (`call_internal_api`)

```python
def call_internal_api(method, path, json_body=None):
    # 拼接 http://localhost:8003 + path
    # 携带 X-API-Key 头
    # urllib 执行 GET/POST/PUT/DELETE/PATCH
    # 返回 {"status": 200, "data": {...}}
```

路由规则：
- 相对路径 `/api/...` → 直接拼接
- 其他路径 → 加 `/api` 前缀

### 3.4 分支决策机制

```
decision 节点:
  config.condition_type = "expression" | "field_compare" | "fixed"
  config.condition     = "amount > 10000" 等
  config.field         = "amount"
  config.values        = {"true": "...", "false": "..."}

执行时:
  _execute_decision(node, context):
    result = eval_condition(node.config, context)  # True/False
    return {
      "status": "done",
      "output": {"decision": result},
      "branch": "true" if result else "false",
    }

execute_instance 主循环捕获 branch:
  if "branch" in result:
      context["_branch"] = result["branch"]
```

---

## 4. API 接口

### 4.1 节点类型元数据

`GET /api/flow/node-types`

返回 12 种节点类型及其分类和 schema：

```json
[
  {
    "id": "start",
    "name": "开始",
    "category": "terminal",
    "icon": "🏁",
    "config_schema": {},
    "description": "流程入口"
  }
]
```

### 4.2 模板 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/flow/templates` | 列表 |
| GET | `/api/flow/template/{name}` | 获取 |
| POST | `/api/flow/template` | 创建（可指定 category/description） |
| PUT | `/api/flow/template/{name}` | 更新 |
| DELETE | `/api/flow/template/{name}` | 删除 |
| POST | `/api/flow/template/{name}/publish` | 发布（is_published=true） |

### 4.3 实例执行

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/flow/instances` | 列表 |
| GET | `/api/flow/instance/{name}` | 获取（含节点+边） |
| POST | `/api/flow/template/{name}/instance` | 创建实例 |
| POST | `/api/flow/instance/{name}/execute?dry_run={0\|1}` | 执行 |
| POST | `/api/flow/instance/{name}/approve` | 审批通过 |
| POST | `/api/flow/instance/{name}/cancel` | 取消（标记 failed） |

### 4.4 AI 构建

`POST /api/flow/build`

```json
{
  "goal": "招聘新员工时自动审批",
  "mode": "rule" | "llm",
  "context": {}
}
```

返回完整模板定义，可直接 POST 到 `/api/flow/template` 创建。

### 4.5 错误码规范

| 场景 | HTTP 状态码 | 错误信息 |
|------|------------|---------|
| 模板不存在 | 404 | `Template not found` |
| 模板未发布 | 400 | `Template is not published` |
| 实例不存在 | 404 | `Instance not found` |
| 实例状态冲突 | 400 | `Instance is already running` |
| 实例已完成/失败 | 400 | `Instance is already completed/failed` |
| 审批状态不匹配 | 400 | `Instance is not suspended` |
| 节点类型未知 | 400 | `Unknown node type` |
| 执行异常 | 500 | 异常详情 |

---

## 5. 前端画布编辑器

### 5.1 文件结构

```
OA/frontend/
├── index.html        # 109 行，HTML 结构 + link/style 引用
├── style.css         # 401 行，全局样式
└── app.js            # 4888 行，全部前端逻辑（含 Flow Designer）
```

### 5.2 画布编辑器架构

```
┌─────────────────────────────────────────────────────────────┐
│  工具栏 (renderToolbar)                                      │
│  [新建模板] [保存] [发布] [新建实例] [执行] [导入JSON] [导出JSON] │
├──────────────────┬──────────────────────┬──────────────────┤
│                  │                      │                  │
│  节点面板        │      SVG 画布          │  属性面板        │
│  (renderPalette) │  (renderCanvas)       │  (renderProperties)│
│                  │                      │                  │
│  ● 终端节点      │  - 网格背景           │                  │
│    🏁 开始       │  - 节点（矩形）       │  选中节点后       │
│    📤 输出       │  - 连线（SVG path）    │  显示配置表单     │
│    ⏸️ 暂停       │  - 拖拽移动           │                  │
│                  │  - 缩放/平移          │  label/config    │
│  ● I/O 节点     │  - 双击节点弹出属性    │  实时更新到       │
│    👤 人工确认    │    编辑对话框          │  nodes JSON      │
│    🤖 Agent      │                      │                  │
│                  │                      │                  │
│  ● 动作节点     │                      │                  │
│    ⚡ 执行操作    │                      │                  │
│    🌐 HTTP 请求   │                      │                  │
│    🔔 通知       │                      │                  │
│    ⏱️ 延时       │                      │                  │
│    🔗 Webhook     │                      │                  │
│                  │                      │                  │
│  ● 控制节点     │                      │                  │
│    🔀 条件判断    │                      │                  │
│    🔄 循环       │                      │                  │
├──────────────────┴──────────────────────┴──────────────────┤
│  节点列表 (renderNodeList) — 显示/编辑模板节点+边            │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 核心交互

| 操作 | 事件 | 行为 |
|------|------|------|
| 拖拽节点到画布 | dragstart → drop | 从节点面板复制节点定义到 nodes[] |
| 移动节点 | mousedown → mousemove → mouseup | 更新 nodes[].x/y |
| 连线 | 从节点右连口 mousemove → 目标节点 mousedown | 创建 edge {source, target} |
| 双击节点 | dblclick | 弹出属性编辑对话框 |
| 点击节点 | click | 选中 → 属性面板显示当前配置 |
| 点击画布空白 | click | 取消选中 |

### 5.4 缩放和平移

- **缩放**：`canvas_scale` (0.3–2.0)，滚轮 ±0.1
- **平移**：`canvas_pan_x/y`，中键拖拽或 shift+左键拖拽
- **坐标变换**：
  - SVG 世界坐标 → 屏幕坐标：`(x - pan_x) * scale + canvas_offset_x`
  - 屏幕坐标 → SVG 世界坐标：`(screen_x - canvas_offset_x) / scale + pan_x`

### 5.5 函数清单（34 个）

| 函数 | 职责 |
|------|------|
| `renderFlowDesigner(main)` | 画布编辑器主入口 |
| `renderCanvas(svg, node, data)` | 绘制单个 SVG 节点 |
| `_drawGrid(svg, canvas)` | 绘制背景网格 |
| `_drawEdges(svg, node, data)` | 绘制所有连线 |
| `_drawNodes(svg, node, data)` | 绘制所有节点 |
| `_drawLabel(svg, x, y, text)` | 绘制文字标签 |
| `renderPalette(panel, data)` | 节点面板 |
| `renderProperties(panel, node, data)` | 属性配置面板 |
| `renderNodeList(panel, data)` | 节点/边列表编辑器 |
| `renderToolbar(toolbar, data)` | 工具栏按钮 |
| `renderInstancePanel()` | 实例执行面板 |
| `FLOW_saveTemplate(data)` | 保存到模板 |
| `FLOW_doSave()` | 触发保存对话框 |
| `FLOW_createInstance()` | 创建实例 |
| `FLOW_executeInstance()` | 执行实例（进度模态面板） |
| `FLOW_approveInstance()` | 审批通过 |
| `FLOW_buildAI()` | AI 构建 |
| `FLOW_exportJson()` | 导出 JSON |
| `FLOW_importJson()` | 导入 JSON |
| `flowCloseModal(el)` | 关闭模态框 |
| `FLOW_viewInstance()` | 查看实例详情 |
| ... | 14 个辅助函数（编辑对话框、连线交互等） |

---

## 6. AI 自主编排

### 6.1 规则引擎（已实现）

关键词匹配逻辑：

```python
def _rule_based_build(goal: str, ctx: dict) -> dict:
    goal_lower = goal.lower()

    # 审批流程模式
    if any(k in goal_lower for k in ["审批", "审批流", "approval", "报销"]):
        return _build_approval_template(ctx)

    # 招聘流程模式
    if any(k in goal_lower for k in ["招聘", "招聘流程", "hire", "入职"]):
        return _build_recruitment_template(ctx)

    # 工单处理模式
    if any(k in goal_lower for k in ["工单", "issue", "ticket", "故障", "问题"]):
        return _build_ticket_template(ctx)
```

三种预置模板模式各生成不同的节点+边序列：

**审批模式**：
```
start → decision(amount>10000) → [approve分支] → output
                         → [agent分支] → output
```

**招聘模式**：
```
start → agent(简历筛选) → decision → action(创建联系人)
                          → agent(面试安排) → notify
```

**工单模式**：
```
start → decision(优先级) → agent(自动诊断)
                     → notify(通知负责人)
```

### 6.2 LLM 引擎（预留）

```python
def _llm_build_goal(goal: str, ctx: dict, available_nodes: list) -> dict:
    """
    预留 LLM 接口：
    - 输入: 用户目标 + 可用节点类型列表
    - 输出: 结构化节点定义 + 边定义
    - 调用方式: POST 到配置的 LLM API
    - 当前返回: HTTP 501 Not Implemented
    """
    raise HTTPException(501, "LLM build not implemented")
```

接入后 prompt 模板：

```
你是一个流程编排助手。用户描述了一个业务流程：

"{goal}"

以下是可用的节点类型：
{available_nodes}

请根据用户描述，设计一个包含 {min_nodes}~{max_nodes} 个节点的流程。
输出 JSON 格式，包含 nodes 和 edges 数组。
```

---

## 7. 节点类型规范

### 7.1 完整类型定义

| ID | 名称 | 类别 | 图标 | 必填配置 |
|----|------|------|------|----------|
| `start` | 开始 | terminal | 🏁 | — |
| `output` | 输出 | terminal | 📤 | `type` (text), `content` |
| `delay` | 延时 | terminal | ⏱️ | `duration_seconds` |
| `manual` | 人工确认 | io | 👤 | `message` |
| `approve` | 审批 | io | ✅ | `approver` (可选), `message` |
| `agent` | Agent | io | 🤖 | `module`, `prompt` |
| `action` | 执行操作 | action | ⚡ | `resource`, `method`, `body` |
| `http` | HTTP 请求 | action | 🌐 | `url`, `method` |
| `webhook` | Webhook | action | 🔗 | `url`, `method` |
| `notify` | 通知 | action | 🔔 | `message`, `channels` |
| `decision` | 条件判断 | control | 🔀 | `field`, `operator`, `value` |
| `loop` | 循环 | control | 🔄 | `iterations`, `variable`, `body_nodes` |

### 7.2 各类型执行细节

#### start
- 初始化 `context` 字典
- 可携带初始变量 `init_vars` 注入 context

#### decision
```json
{
  "condition_type": "expression",
  "condition": "amount > 10000",
  "context_key": "amount"
}
```
- `expression` 类型：直接 `eval(condition, context)`，需要 context 中有对应变量
- `field_compare` 类型：`context[config.field] operator config.value`

#### action（内部 API）
```json
{
  "resource": "Purchase Order",
  "method": "PUT",
  "body": {"total": 15000, "status": "Approved"},
  "ctx_key": "po_result"
}
```
- 调用 `call_internal_api(method, f"/api/resource/{resource}", body)`
- 结果写入 `context[ctx_key]`

#### http / webhook
```json
{
  "url": "https://api.example.com/data",
  "method": "GET",
  "headers": {"Authorization": "Bearer xxx"}
}
```
- http：GET 请求，结果注入 context
- webhook：POST 请求，只返回 status

#### agent
```json
{
  "module": "procurement",
  "prompt": "分析以下采购单..."
}
```
- 调用 `POST /api/ai/consult`
- 返回含 `advice` / `risk_flags` / `suggestions`

#### loop
```json
{
  "iterations": 3,
  "variable": "i",
  "ctx_key": "loop_result",
  "body_nodes": [
    {"type": "decision", "label": "判断 i", "config": {"field": "i", "operator": ">", "value": 1}},
    {"type": "action", "label": "处理", "config": {"resource": "User", "method": "GET", "body": {}}}
  ]
}
```
- body_nodes 是内联子节点定义（非 DB 引用）
- 每次迭代设置 `context[variable] = idx`
- 创建临时 `_LoopNode` 执行

#### notify
```json
{
  "message": "审批通过通知",
  "channels": ["inapp", "wecom"],
  "title": "OA 通知",
  "recipient": ""
}
```
- 遍历 channels，调用 `push_external(title, message, channel, recipient)`

---

## 8. 数据流与状态机

### 8.1 节点执行状态机

```
              ┌────────┐
              │ pending │
              └───┬────┘
                  │
              running
                  │
          ┌───────┼───────┐
          │       │       │
      ┌───▼───┐ ┌▼────┐ ┌▼────────┐
      │  done │ │fail │ │ suspended │
      └───────┘ └─────┘ └──────────┘
                         │
                    (外部 approve)
                         │
                    ┌────▼────┐
                    │ running │ (重新进入)
                    └─────────┘
```

### 8.2 实例生命周期

```
                  ┌──────────┐
                  │  pending │
                  └────┬─────┘
                       │ execute()
                  ┌────▼─────┐
                  │  running │
                  ├──────────┤
                  │ 每步更新   │
                  │ context  │
                  └────┬─────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
     ┌────▼────┐  ┌────▼────┐  ┌───▼───────┐
     │ completed│  │  failed │  │ suspended │
     └─────────┘  └─────────┘  └─────┬─────┘
                                     │
                              ┌──────▼───────┐
                              │  approve    │
                              │  /cancel    │
                              └──────┬───────┘
                                     │
                              ┌──────▼───────┐
                              │  running    │ (继续执行)
                              └─────────────┘
```

### 8.3 模板发布门控

```
开发中 (is_published=false)
        │
  ┌─────▼────┐
  │  publish  │
  └─────┬────┘
        │
已发布 (is_published=true)
        │
  ┌─────▼────┐
  │ 可执行    │
  └──────────┘
```

---

## 9. 部署与运维

### 9.1 Docker 容器栈

| 容器 | 端口 | 用途 |
|------|------|------|
| `zzcc-oa-mariadb` | 3307:3306 | MariaDB 10.8，flow 5 表 |
| `zzcc-oa-backend` | 8003 | FastAPI，14 flow 端点 |
| `zzcc-oa-nginx` | 8080:80 | nginx 反代，SPA 路由 |
| `zzcc-oa-frontend` | — | 备用 |
| `zzcc-oa-redis` | 6379 | 缓存/队列 |

### 9.2 nginx 配置要点

```nginx
location /api/ {
    proxy_pass http://backend:8003;
    proxy_set_header X-API-Key $http_x_api_key;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
location / {
    try_files $uri $uri/ /index.html;
}
```

### 9.3 已知运维痛点

| 问题 | 根因 | 绕过方案 |
|------|------|----------|
| `docker cp` 报 "device or resource busy" | bind mount 句柄被 nginx 持有 | `docker cp` → `nginx -s reload`（reload 触发重载，内容已替换） |
| 文件已修改但 `docker cp` 失败 | 同上 | 用 rename trick：`cp` 到 `.tmp` 再 `mv` |
| 后端启动慢导致 nginx DNS 失败 | 容器启动时序 | backend healthy 后再重启 nginx |

### 9.4 健康检查

```bash
# 39 端点全量检查（40 模块）
curl -H "X-API-Key: zzcc_oadev_key_2024" \
  http://localhost:8080/api/flow/node-types

# 确认 5 张 flow 表存在
docker exec -i zzcc-oa-mariadb mysql -uroot -pzzcc_oa_2024 \
  -e "USE zzcc_oa; SHOW TABLES LIKE 'flow_%';"

# pytest 全量
python -m pytest backend/test/ --tb=line -q
# 期望: 306 passed, 9 warnings
```

---

## 10. 扩展路线图

### 10.1 近期

| 优先级 | 项目 | 说明 |
|--------|------|------|
| P0 | ✅ | 基础执行引擎（start/decision/action/agent/http/webhook/notify/delay/approve/output/loop） |
| P0 | ✅ | 前端画布编辑器（拖拽、连线、缩放、属性编辑、模板管理） |
| P0 | ✅ | AI 规则引擎（3 种模式） |
| P0 | ✅ | 测试覆盖率（flow 30 用例，全量 306 passed） |
| P1 | ⬜ | LLM 引擎接入（自然语言 → 节点序列） |
| P1 | ⬜ | cron 触发器（定时自动创建实例） |
| P1 | ⬜ | webhook 事件触发器（外部事件自动启动） |

### 10.2 中期

| 项目 | 说明 |
|------|------|
| 流程模板市场 | 预置模板 + 用户分享 |
| 流程版本管理 | 模板 diff + 回滚 |
| 执行看板 | 实例列表 + 甘特图 + 执行耗时 |
| 变量表达式引擎 | 支持模板变量 `${var}` 在 context 中解析 |
| 节点插件机制 | 自定义节点类型（Python 注册表） |

### 10.3 远期

| 项目 | 说明 |
|------|------|
| 多租户隔离 | 每个部门独立流程空间 |
| 流程分析 | 执行频率 / 瓶颈分析 / 自动化率 |
| 与钉钉/企微深度集成 | 消息卡片 / 审批单推送 |
| BPMN 2.0 导入导出 | 标准格式互通 |

---

## 附录 A：关键源码文件

| 文件 | 行数 | 内容 |
|------|------|------|
| `backend/models/flow.py` | 138 | FlowTemplate/Instance/Node/Edge/AgentLog 5 模型 |
| `backend/services/flow_engine.py` | 475 | 模板 CRUD + 实例执行 + 12 节点类型执行 + AI build |
| `backend/routers/flow.py` | 539 | 14 个 API 端点 |
| `frontend/app.js` | 4888 | 全部前端逻辑（含 34 个 Flow Designer 函数） |
| `backend/test/test_flow.py` | — | 30 用例，覆盖执行引擎所有节点类型 |

## 附录 B：FlowTemplate JSON 结构示例

```json
{
  "name": "template-hr-recruit-001",
  "title": "招聘新员工审批流程",
  "description": "从简历筛选到入职的自动化流程",
  "category": "hr",
  "nodes": [
    {"id": "n1", "type": "start", "label": "开始", "x": 100, "y": 200, "config": {}},
    {"id": "n2", "type": "agent", "label": "简历筛选", "x": 300, "y": 200,
     "config": {"module": "hr", "prompt": "分析简历..."}},
    {"id": "n3", "type": "decision", "label": "是否通过", "x": 500, "y": 200,
     "config": {"field": "pass_score", "operator": ">=", "value": 70}},
    {"id": "n4", "type": "action", "label": "创建联系人", "x": 700, "y": 100,
     "config": {"resource": "Contact", "method": "POST", "body": {}}},
    {"id": "n5", "type": "notify", "label": "通知负责人", "x": 700, "y": 300,
     "config": {"message": "简历已通过筛选", "channels": ["inapp"]}},
    {"id": "n6", "type": "output", "label": "结束", "x": 900, "y": 200,
     "config": {"type": "text", "content": "招聘流程完成"}}
  ],
  "edges": [
    {"source": "n1", "target": "n2", "condition": "default", "label": ""},
    {"source": "n2", "target": "n3", "condition": "default", "label": ""},
    {"source": "n3", "target": "n4", "condition": "true", "label": "通过"},
    {"source": "n3", "target": "n5", "condition": "false", "label": "不通过"},
    {"source": "n4", "target": "n6", "condition": "default", "label": ""},
    {"source": "n5", "target": "n6", "condition": "default", "label": ""}
  ],
  "version": 1,
  "is_published": true
}
```

## 附录 C：API 端点完整清单

```
GET    /api/flow/node-types             — 节点类型元数据
GET    /api/flow/templates              — 模板列表
GET    /api/flow/template/{name}        — 获取模板
POST   /api/flow/template               — 创建模板
PUT    /api/flow/template/{name}        — 更新模板
DELETE /api/flow/template/{name}        — 删除模板
POST   /api/flow/template/{name}/publish — 发布模板

GET    /api/flow/instances              — 实例列表
GET    /api/flow/instance/{name}        — 获取实例
POST   /api/flow/template/{name}/instance — 创建实例
POST   /api/flow/instance/{name}/execute  — 执行实例（?dry_run=0|1）
POST   /api/flow/instance/{name}/approve — 审批通过
POST   /api/flow/instance/{name}/cancel  — 取消实例

POST   /api/flow/build                  — AI 自主编排
```

---

*文档版本：v1.0 | 最后更新：2026-08-26*
*对应代码：commit `4ae4a2e`（+ 之前的 `7301ef8`/`02f0a86`/`5845e2d`）*