# ZZCC OA 类脑 AI 架构设计

> 版本 1.0 · 2026-09-05
> 基于现有 OA 后端（43 routers / 50 tables / 插件系统 / 流程编排引擎）

---

## 1. 设计目标

将当前碎片化的 AI 能力（规则咨询 / 自动审批 / 流程编排）统一为**一个类脑认知系统**，具备：

| 能力 | 现有状态 | 目标状态 |
|------|---------|---------|
| 感知 | 被动接收请求 | 主动监听事件 + 轮询数据变更 |
| 注意 | 无 | 动态过滤无关信息，聚焦关键信号 |
| 工作记忆 | 无（每次请求独立） | 跨请求上下文保持（会话 / 任务级） |
| 长期记忆 | 审批阈值表 | 知识图谱 + 模式库 + 决策日志 |
| 推理 | 硬编码规则 | 规则引擎 + LLM + 统计推理 三层 |
| 行动 | 直接修改 DB | 通过 Action API 统一执行，可审计 |
| 学习 | 无 | 从反馈中调整权重 / 阈值 / 策略 |

---

## 2. 架构总览

```
                        ┌─────────────────────────────┐
                        │       Neural Shell           │
                        │   (Cognitive Frontend)       │
                        │  /api/brain/ask /act /plan   │
                        └──────────┬──────────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
     ┌──────▼──────┐      ┌───────▼───────┐      ┌───────▼───────┐
     │ Perception  │      │  Cognition    │      │   Action      │
     │  (感知层)   │      │  (认知层)     │      │   (行动层)     │
     └──────┬──────┘      └───────┬───────┘      └───────┬───────┘
            │                     │                      │
     ┌──────▼──────┐      ┌───────▼───────┐      ┌───────▼───────┐
     │  Event Bus  │      │  Reasoning    │      │   Tool Call   │
     │  Router     │      │  Engine       │      │   Executor    │
     │  Pollers    │      │               │      │               │
     └──────┬──────┘      └───────┬───────┘      └───────┬───────┘
            │                     │                      │
     ┌──────▼──────┐      ┌───────▼───────┐      ┌───────▼───────┐
     │  Plugins    │      │   Memory      │      │   Workflow    │
     │  Webhooks   │      │   Store       │      │   Engine      │
     │  Cron       │      │   (DB + KV)   │      │   Auto-       │
     │             │      │               │      │   Approval    │
     └─────────────┘      └───────────────┘      └───────────────┘
```

---

## 3. 核心模块设计

### 3.1 感知层（Perception Layer）

**职责**：将外部信号转化为标准化的 `NeuralSignal`。

```python
# models/brain.py

class NeuralSignal(BaseModel):
    """感知信号 — 类脑系统的输入单元"""
    id: str                    # UUID
    source: str                # event_bus / webhook / cron / api_call / manual
    type: str                  # document_created / approval_pending / threshold_breach / ...
    payload: dict              # 原始数据
    urgency: int               # 0-100, 影响注意力分配
    context: dict              # 附加上下文（用户/部门/时间窗口）
    created_at: datetime
    processed: bool = False
```

**信号源**：

| 来源 | 实现 | 信号类型 |
|------|------|---------|
| 事件总线 | 订阅 `plugin_event_log` | `plugin_event` |
| 数据库轮询 | 定时扫描待审批单据 | `approval_pending` |
| 外部 Webhook | 接收第三方系统推送 | `external_event` |
| 定时任务 | 预算告警、库存预警 | `cron_alert` |
| API 调用 | 用户主动触发 | `user_request` |

**注意力机制**：

```python
class AttentionMechanism:
    """基于 urgency + 上下文相关性的动态注意力分配"""
    
    def score(self, signal: NeuralSignal, working_memory: dict) -> float:
        """返回 0.0-1.0 的注意力分数"""
        base = signal.urgency / 100.0
        
        # 上下文相关性加成
        relevance = self._compute_relevance(signal, working_memory)
        
        # 时间衰减（旧信号注意力降低）
        age_penalty = max(0, 1 - (now - signal.created_at).total_seconds() / 3600)
        
        return base * (0.5 + 0.5 * relevance) * (0.5 + 0.5 * age_penalty)
```

### 3.2 认知层（Cognition Layer）

#### 3.2.1 工作记忆（Working Memory）

短期上下文保持，按会话/任务隔离，TTL 可配置。

```python
class WorkingMemory:
    """类脑工作记忆 — 保持最近 N 轮认知上下文"""
    
    def __init__(self, ttl: int = 3600, max_items: int = 100):
        self._store: dict[str, list[dict]] = {}  # session_id -> signals
        self._ttl = ttl
        self._max_items = max_items
    
    def push(self, session_id: str, signal: NeuralSignal, cognition: dict):
        """存储信号 + 认知结果"""
        entry = {
            "signal": signal.dict(),
            "cognition": cognition,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if session_id not in self._store:
            self._store[session_id] = []
        self._store[session_id].append(entry)
        self._evict(session_id)
    
    def get_context(self, session_id: str) -> list[dict]:
        """获取当前会话的认知上下文"""
        return self._store.get(session_id, [])
    
    def _evict(self, session_id: str):
        """TTL 淘汰 + 容量限制"""
        now = datetime.utcnow()
        entries = self._store[session_id]
        self._store[session_id] = [
            e for e in entries
            if (now - datetime.fromisoformat(e["timestamp"])).total_seconds() < self._ttl
        ][-self._max_items:]
```

#### 3.2.2 推理引擎（Reasoning Engine）

三层推理架构，按成本递增调用：

```
L1: 规则引擎     → 确定性规则，毫秒级，零成本
L2: 统计推理     → 基于历史数据模式，百毫秒级，低成本
L3: LLM 推理     → 复杂判断/创造性任务，秒级，高成本
```

```python
class ReasoningEngine:
    """三层推理引擎 — 类脑认知核心"""
    
    def reason(self, signal: NeuralSignal, working_memory: list[dict]) -> CognitionResult:
        # L1: 规则引擎（现有 ai.py + auto_approval.py 逻辑）
        l1 = self._rule_engine(signal)
        if l1.confidence >= 0.8:
            return l1
        
        # L2: 统计推理（历史模式匹配）
        l2 = self._statistical_reasoning(signal, working_memory)
        if l2.confidence >= 0.7:
            return l2
        
        # L3: LLM 推理（需要外部 API）
        l3 = self._llm_reasoning(signal, working_memory)
        return l3
    
    def _rule_engine(self, signal: NeuralSignal) -> CognitionResult:
        """L1: 确定性规则匹配"""
        # 采购金额 > 50万 → 升级审批
        # 库存低于安全线 → 触发采购
        # 合同含排他条款 → 标记风险
        # ... 现有 ai.py 规则迁入此处
        
    def _statistical_reasoning(self, signal, memory) -> CognitionResult:
        """L2: 基于历史数据的统计推理"""
        # 同类单据历史通过率
        # 审批人平均处理时间
        # 预算消耗速率预测
        # 异常检测（z-score / 3-sigma）
        
    def _llm_reasoning(self, signal, memory) -> CognitionResult:
        """L3: LLM 推理（可选）"""
        # 构建 prompt（信号 + 上下文 + 历史）
        # 调用 LLM API
        # 解析结构化输出
```

**CognitionResult 数据结构**：

```python
class CognitionResult(BaseModel):
    signal_id: str
    reasoning_level: int         # 1/2/3
    confidence: float            # 0.0-1.0
    decision: str                # auto_approve / reject / escalate / flag / need_info
    reasoning: str               # 推理过程说明
    actions: list[Action]        # 建议执行的操作
    risks: list[str]             # 风险标记
    memory_updates: dict         # 需要持久化的学习数据
```

#### 3.2.3 长期记忆（Long-Term Memory）

```python
# DB 表设计

CREATE TABLE brain_memory (
    id INT AUTO_INCREMENT PRIMARY KEY,
    type ENUM('pattern', 'rule', 'feedback', 'lesson', 'preference') NOT NULL,
    module VARCHAR(64) NOT NULL,
    key VARCHAR(128) NOT NULL,
    value JSON NOT NULL,
    confidence FLOAT DEFAULT 0.5,
    hit_count INT DEFAULT 0,
    miss_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY (type, module, key),
    INDEX idx_type_module (type, module)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE brain_decision_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    signal_id VARCHAR(36) NOT NULL,
    signal_type VARCHAR(64) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    confidence FLOAT NOT NULL,
    reasoning_level INT NOT NULL,
    reasoning TEXT,
    actions JSON,
    outcome ENUM('correct', 'incorrect', 'pending', NULL) DEFAULT NULL,
    feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_signal (signal_id),
    INDEX idx_type_decision (signal_type, decision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3.3 行动层（Action Layer）

统一行动执行器，所有 AI 决策通过此层执行，确保可审计。

```python
class ActionExecutor:
    """统一行动执行器 — 类脑系统的输出通道"""
    
    def execute(self, action: Action, cognition: CognitionResult, db: Session) -> dict:
        """执行行动并记录审计日志"""
        # 1. 权限检查（AI agent 是否有权执行此操作）
        if not self._check_permission(action, cognition):
            return {"ok": False, "error": "permission_denied"}
        
        # 2. 执行前校验（状态机合法性检查）
        if not self._validate_precondition(action, db):
            return {"ok": False, "error": "invalid_state"}
        
        # 3. 执行行动
        result = self._dispatch(action, db)
        
        # 4. 写入决策日志
        self._log_decision(cognition, action, result)
        
        # 5. 更新长期记忆（学习反馈）
        self._update_memory(cognition, result)
        
        return result
    
    def _dispatch(self, action: Action, db: Session) -> dict:
        """路由到具体执行器"""
        executors = {
            "approve": self._exec_approve,
            "reject": self._exec_reject,
            "create_document": self._exec_create_document,
            "send_notification": self._exec_send_notification,
            "trigger_flow": self._exec_trigger_flow,
            "create_ticket": self._exec_create_ticket,
        }
        executor = executors.get(action.type)
        if not executor:
            return {"ok": False, "error": f"unknown_action: {action.type}"}
        return executor(action, db)
```

**Action 类型**：

| 类型 | 说明 | 示例 |
|------|------|------|
| `approve` | 审批通过 | AI 自动通过小额报销 |
| `reject` | 审批拒绝 | 拒绝超标支出 |
| `escalate` | 升级审批 | 大额采购需总监审批 |
| `create_document` | 创建单据 | 自动生成采购申请单 |
| `send_notification` | 发送通知 | 预算告警通知 |
| `trigger_flow` | 触发流程 | 启动审批流程实例 |
| `create_ticket` | 创建工单 | 质量问题工单 |
| `update_memory` | 更新记忆 | 记录决策模式 |

---

## 4. API 设计

### 4.1 核心 API

```
POST /api/brain/ask          — 主动咨询（同步推理）
POST /api/brain/observe      — 被动感知（提交信号，异步处理）
GET  /api/brain/status       — 系统状态（信号队列 / 活跃推理 / 统计）
GET  /api/brain/memory       — 查询长期记忆
POST /api/brain/learn        — 反馈学习（标记决策正确/错误）
```

### 4.2 Neural Shell API

```
POST /api/brain/ask
{
  "question": "当前待审批的采购单中有哪些高风险项？",
  "context": {"user_id": "admin", "department": "采购部"},
  "max_cost": "l1"   // l1=规则, l2=统计, l3=LLM
}

→ {
  "answer": "发现 3 项高风险采购单...",
  "reasoning_level": 2,
  "confidence": 0.85,
  "actions_suggested": [...]
}
```

```
POST /api/brain/observe
{
  "signal": {
    "type": "approval_pending",
    "payload": {"doctype": "ExpenseClaim", "name": "EXP-001"},
    "urgency": 60
  }
}

→ 202 Accepted（异步处理，结果通过事件总线推送）
```

### 4.3 管理 API

```
GET  /api/brain/config       — 推理引擎配置
PUT  /api/brain/config       — 更新配置
GET  /api/brain/stats        — 推理统计（各层级调用次数/置信度分布）
GET  /api/brain/learnings    — 学习记录列表
DELETE /api/brain/memory     — 清除指定记忆
```

---

## 5. 与现有系统的集成

### 5.1 现有模块映射

```
现有模块                          类脑系统对应
─────────────────────────────────────────────
routers/ai.py (_ai_*_consult)    → ReasoningEngine._rule_engine (L1)
services/auto_approval.py        → ReasoningEngine + ActionExecutor
services/flow_engine.py          → ActionExecutor._exec_trigger_flow
plugins/event_bus.py             → Perception Layer 信号源
plugins/loader.py                → ActionExecutor 插件扩展
routers/notifications.py         → ActionExecutor._exec_send_notification
routers/workflow.py              → ActionExecutor._exec_approve/reject
routers/audit_log.py             → ActionExecutor._log_decision
```

### 5.2 迁移路径

```
Phase 1: 包装（0 代码变更）
  - 将现有 AI 咨询路由包装为 Brain API 的 L1 推理
  - 事件总线信号转发为 NeuralSignal

Phase 2: 统一（中等改动）
  - 合并 ai.py + auto_approval.py 到 ReasoningEngine
  - 新增 brain_memory + brain_decision_log 表
  - 实现 WorkingMemory + AttentionMechanism

Phase 3: 增强（大改动）
  - L2 统计推理（历史模式匹配、异常检测）
  - L3 LLM 推理（接入外部 API）
  - 学习闭环（决策日志 → 记忆更新 → 推理权重调整）
```

---

## 6. 推理层级详细设计

### L1: 规则引擎

从现有 `ai.py` + `auto_approval.py` 提取规则，统一为规则表：

```python
@dataclass
class Rule:
    id: str
    module: str              # procurement / finance / hr / ...
    condition: Callable      # lambda ctx: bool
    action: str              # approve / reject / escalate / flag
    confidence: float        # 0.0-1.0
    description: str
    enabled: bool = True

RULES = [
    Rule(
        id="procurement_large_amount",
        module="procurement",
        condition=lambda ctx: ctx.get("amount", 0) > 500000,
        action="escalate",
        confidence=0.95,
        description="单笔采购超50万需升级审批",
    ),
    Rule(
        id="expense_small_auto",
        module="expense",
        condition=lambda ctx: ctx.get("amount", 0) <= 1000,
        action="approve",
        confidence=0.9,
        description="小额报销≤1000自动通过",
    ),
    # ... 更多规则
]
```

### L2: 统计推理

```python
def _statistical_reasoning(self, signal, memory):
    """基于历史数据的统计推理"""
    results = {}
    
    # 1. 历史通过率
    history = self._get_history(signal.type, signal.payload.get("doctype"))
    if len(history) >= 10:
        pass_rate = sum(1 for h in history if h["outcome"] == "correct") / len(history)
        results["historical_pass_rate"] = pass_rate
    
    # 2. 异常检测（Z-score）
    amounts = [h.get("amount", 0) for h in history if "amount" in h]
    if amounts:
        z = self._z_score(signal.payload.get("amount", 0), amounts)
        results["anomaly_score"] = min(1.0, abs(z) / 3.0)
        if abs(z) > 2.5:
            results["anomaly_flag"] = True
    
    # 3. 时间模式（审批人平均处理时间）
    if signal.type == "approval_pending":
        avg_hours = self._avg_approval_hours(signal.payload.get("doctype"))
        results["expected_hours"] = avg_hours
    
    return self._synthesize(results)
```

### L3: LLM 推理

```python
def _llm_reasoning(self, signal, memory):
    """LLM 推理（需配置 OPENAI_API_KEY）"""
    prompt = self._build_prompt(signal, memory)
    
    # 调用 LLM
    response = self._call_llm(prompt)
    
    # 解析结构化输出
    result = self._parse_llm_response(response)
    result.reasoning_level = 3
    result.confidence = min(result.confidence, 0.7)  # LLM 置信度上限
    
    return result
```

---

## 7. 学习闭环

```
信号 → 推理 → 行动 → 反馈 → 记忆更新 → 推理权重调整
  ↑                                                    │
  └────────────────────────────────────────────────────┘
```

```python
class LearningLoop:
    """学习闭环 — 从反馈中调整推理策略"""
    
    def record_outcome(self, signal_id: str, correct: bool, feedback: str = None):
        """记录决策结果"""
        # 1. 更新决策日志
        self._update_decision_log(signal_id, correct, feedback)
        
        # 2. 更新规则置信度
        rule = self._find_rule(signal_id)
        if rule:
            if correct:
                rule.confidence = min(1.0, rule.confidence + 0.02)
                rule.hit_count += 1
            else:
                rule.confidence = max(0.0, rule.confidence - 0.05)
                rule.miss_count += 1
            
            # 置信度过低 → 自动禁用规则
            if rule.confidence < 0.3:
                rule.enabled = False
        
        # 3. 更新长期记忆
        self._save_pattern(signal_id, correct, feedback)
    
    def adjust_thresholds(self):
        """定期调整审批阈值（基于学习数据）"""
        # 小额报销通过率 > 95% → 可考虑提高自动审批上限
        # 大额审批驳回率 > 30% → 可降低阈值
        pass
```

---

## 8. 文件结构

```
backend/
├── models/
│   └── brain.py                 # NeuralSignal / CognitionResult / Action / Rule
├── services/
│   ├── brain_engine.py          # ReasoningEngine（L1+L2+L3 推理）
│   ├── brain_memory.py          # WorkingMemory + LongTermMemory
│   ├── brain_attention.py       # AttentionMechanism
│   ├── brain_actions.py         # ActionExecutor
│   ├── brain_learning.py        # LearningLoop
│   └── brain_perception.py      # 信号采集器（事件总线/轮询/Webhook）
├── routers/
│   └── brain.py                 # /api/brain/* API
├── plugins/
│   └── (event_bus 信号源集成)
├── database.py                  # brain_memory + brain_decision_log 表 DDL
└── main.py                      # lifespan 初始化大脑系统
```

---

## 9. 配置

```python
# config.py 新增
BRAIN_ENABLED: bool = True
BRAIN_LLM_ENABLED: bool = False          # L3 LLM 推理开关
BRAIN_LLM_API_KEY: str = ""
BRAIN_LLM_MODEL: str = "gpt-4o"
BRAIN_WORKING_MEMORY_TTL: int = 3600     # 秒
BRAIN_WORKING_MEMORY_MAX: int = 100
BRAIN_ATTENTION_THRESHOLD: float = 0.3   # 低于此分数的信号忽略
BRAIN_AUTO_EXECUTE: bool = False         # 是否自动执行行动（默认仅建议）
BRAIN_LEARNING_ENABLED: bool = True
BRAIN_POLL_INTERVAL: int = 60            # 信号轮询间隔（秒）
```

---

## 10. 扩展性设计

### 10.1 新推理层接入

```python
# 实现一个自定义推理层
class CustomReasoningLayer:
    def reason(self, signal, memory) -> CognitionResult:
        ...

# 注册到推理引擎
brain_engine.register_layer(2, CustomReasoningLayer())
```

### 10.2 新行动类型

```python
# 注册新行动执行器
brain_actions.register_executor("send_email", exec_send_email)
```

### 10.3 新信号源

```python
# 通过事件总线发布信号
event_bus.publish("brain.signal", {
    "type": "custom_event",
    "payload": {...},
    "urgency": 70,
})
```

### 10.4 插件扩展

通过插件系统为大脑添加新的感知源、推理规则或行动执行器：

```python
# 插件 routes.py
@router.post("/brain/register-rule")
async def register_rule(request: Request):
    """动态注册推理规则"""
    from routers.brain import register_rule as brain_register_rule
    brain_register_rule(request.json())
```

---

## 11. 与类脑架构的映射

| 人脑结构 | 系统对应 | 功能 |
|---------|---------|------|
| 感官系统 | Perception Layer | 接收外部信号 |
| 丘脑（注意力） | AttentionMechanism | 过滤无关信息 |
| 工作记忆 | WorkingMemory | 短期上下文保持 |
| 皮层（推理） | ReasoningEngine | L1 规则 / L2 统计 / L3 LLM |
| 海马体（记忆） | LongTermMemory | 知识图谱 + 模式库 |
| 运动皮层 | ActionExecutor | 执行决策 |
| 突触可塑性 | LearningLoop | 反馈学习 + 权重调整 |
| 小脑（协调） | BrainEngine 调度 | 协调各模块工作流 |

---

## 12. 下一步实施计划

```
Step 1: 基础框架（1-2 天）
  - models/brain.py + database.py DDL
  - services/brain_engine.py (L1 only, 迁移现有规则)
  - routers/brain.py (ask/observe/status)
  - 验证：现有 AI 咨询功能无回退

Step 2: 感知 + 记忆（1-2 天）
  - brain_perception.py (事件总线信号采集)
  - brain_memory.py (WorkingMemory + LongTermMemory)
  - brain_attention.py (注意力机制)
  - 验证：信号自动采集 + 注意力过滤

Step 3: 行动 + 学习（2-3 天）
  - brain_actions.py (统一行动执行器)
  - brain_learning.py (学习闭环)
  - 决策日志 + 反馈 API
  - 验证：AI 审批端到端 + 学习记录

Step 4: L2/L3 增强（2-3 天）
  - L2 统计推理（历史模式 + 异常检测）
  - L3 LLM 推理（配置 API Key 后启用）
  - 验证：复杂场景推理 + 置信度评估

Step 5: 插件集成 + 优化（1 天）
  - 插件系统信号源注册
  - 性能优化（批量处理 + 缓存）
  - 监控面板
```
