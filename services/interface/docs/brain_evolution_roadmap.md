# 类脑 AI 演进路线图：从格物致知到知行合一

> 基于现有 ZZCC Brain 架构的诊断与演进规划
> 2026-10-27

---

## 一、现状诊断：当前架构在格物致知框架下的位置

### 1.1 当前数据流

```
外部输入 → NeuralSignal(type, urgency, amount, payload)
                ↓
        _classify_signal() → Intent
                ↓
        compute_budget.allocate() → 脑区分配
                ↓
        coordinator.run() → 并行执行(rule/statistical/llm/snn/semantic/episodic)
                ↓
        _integrate() → 加权融合 + 冲突仲裁
                ↓
        CognitionResult(decision, confidence, reasoning)
                ↓
        ActionExecutor → 执行
```

### 1.2 核心问题：跳过了感知与感受

当前架构的最大结构性缺陷：**输入和输出都是预定义的符号**，中间跳过了两个关键环节。

| 格物致知 | 当前状态 | 问题 |
|---------|---------|------|
| **感官**（视觉/听觉/嗅觉/味觉/触觉） | ❌ 缺失 | `NeuralSignal` 是预结构化的符号（type="expense"），不是感官输入 |
| **感受**（威胁感/安全感/兴趣/困惑） | ❌ 缺失 | SNN 输出直接是决策（auto_approve），不是感受 |
| **格物**（从现象提取本质） | ❌ 缺失 | "紧急度""大额"是人硬编码的（_AMOUNT_HIGH_MIN=100000），不是系统发现的 |
| **致知**（积累概念，形成网络） | ⚠️ 部分 | knowledge graph 存在但被动（人工录入） |
| **诚意**（内外一致） | ⚠️ 部分 | shadow SNN 在做，但只是决策一致性，不是感受一致性 |
| **正心**（价值判断） | ❌ 缺失 | 伦理在 LLM prompt 里，不在系统动力学中 |
| **修身**（自我调节） | ⚠️ 部分 | EWC/微学习存在，但被动触发 |
| **齐家**（脑区协调） | ✅ 有 | coordinator 并行执行+融合 |
| **治国**（系统间协调） | ❌ 缺失 | 脑区间无协商，只有加权投票 |
| **平天下**（跨系统） | ❌ 缺失 | 无 |

### 1.3 当前 SNN 的本质定位

**当前 SNN 是一个"无感官的分类器"**：

```python
# 输入：人工编码的特征桶
_encode_signal: signal.type → neuron_id (硬编码映射)
                signal.urgency → 阈值判断 (>=70 → neuron 11)
                payload.amount → 分桶 (>=100000 → neuron 14)

# 输出：人工定义的决策
_decode_output: neuron 32 → "auto_approve"
                neuron 34 → "escalate"
                neuron 35 → "reject"
```

12/12 eval 通过证明了"选择性连接可行"，但证明了错误的东西——它证明的是**规则可以被神经元模拟**，而不是**系统可以感知和判断**。

---

## 二、目标架构：感知→感受→认知→决策 四层

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: 行动 (Action)                                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ActionExecutor + 伦理约束层 (Value Constraints)            │  │
│  │  当前有 ActionExecutor，缺价值约束                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                         ↑                                         │
│  Layer 3: 认知 (Cognition)                                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Coordinator + Rule/Statistical/LLM/Semantic/Episodic      │  │
│  │  现有基础设施，保留                                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                         ↑                                         │
│  Layer 2: 感受 (Sentience) ← 新增                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  SentienceNet: 感知特征 → 感受状态                          │  │
│  │  输出: 威胁/安全/兴趣/困惑/紧急/熟悉/异常                   │  │
│  │  不是决策，是"这个信号让我感觉怎么样"                        │  │
│  │  基于 SNN 架构，但输出层是感受而非决策                       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                         ↑                                         │
│  Layer 1: 感官 (Perception) ← 新增                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  PerceptionChannel: 原始输入 → 特征向量                    │  │
│  │  文本感知: token embedding → 韵律/情感/语义特征             │  │
│  │  图像感知: 视觉特征提取（未来）                              │  │
│  │  时序感知: 事件节奏/频率/变化率                              │  │
│  │  输出: 多通道特征向量，不经过人工编码                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                         ↑                                         │
│  Layer 0: 原始输入 (Sensory Input)                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  NeuralSignal.payload → 原始文本/数据，不预设结构            │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 与现有架构的关系

| 现有组件 | 在四层架构中的位置 | 处理方式 |
|---------|------------------|---------|
| `NeuralSignal` | Layer 0（输入） | 扩展：增加 `raw_features` 字段（可选） |
| `_classify_signal()` | Layer 3 的认知路由 | 保留，但降级为启发式（当感知层不可用时） |
| `compute_budget` | Layer 3 的认知预算 | 保留，但预算按感受状态而非意图分配 |
| `coordinator` | Layer 3 的认知融合 | 保留，扩展：接收感受状态作为输入 |
| `snn` / `snn_region` | Layer 2 的感受网络 | 重构：输入改为特征向量，输出改为感受 |
| `reasoning` | Layer 3 的认知主流程 | 保留，增加感知前置步骤 |
| `action_executor` | Layer 4 的行动执行 | 保留，增加价值约束层 |

---

## 三、四层架构详细设计

### Layer 1: 感知层 (PerceptionChannel)

**目标**：从原始输入中提取特征向量，不预设语义标签。

#### 1.1 文本感知通道 (TextPerceptionChannel)

```python
class TextPerceptionChannel:
    """文本感知：从原始文本提取多通道特征向量。
    
    不做人工编码（不判断 type/urgency/amount），
    只提取统计和嵌入特征，让下游学习如何解释。
    """
    
    # 通道定义（每个通道 = 一个特征维度，对应一组输入神经元）
    CHANNELS = {
        "lexical": {       # 词汇通道：token 频次/稀有度
            "dim": 8,      # 8 个神经元
            "desc": "token_freq_buckets, rare_word_ratio, avg_word_len"
        },
        "sentiment": {     # 情感通道：情感极性/强度
            "dim": 6,      # 6 个神经元
            "desc": "pos_polarity, neg_polarity, arousal, dominance"
        },
        "formality": {     # 正式度通道：语言风格
            "dim": 4,      # 4 个神经元
            "desc": "formality_score, politeness, urgency_markers"
        },
        "numeric": {       # 数值通道：文本中的数字特征
            "dim": 6,      # 6 个神经元
            "desc": "has_number, number_magnitude, currency_present"
        },
        "structure": {     # 结构通道：文本组织
            "dim": 4,      # 4 个神经元
            "desc": "sentence_count, avg_sentence_len, has_question"
        },
    }
    # 总计 28 个感知输入神经元
    
    def perceive(self, raw_text: str) -> Dict[str, List[float]]:
        """返回 {channel_name: [feature_values]}，不预设语义。
        
        例：
        input: "审批一笔88000元的设备采购费用，供应商风险高"
        
        lexical:   [0.3, 0.7, 0.2, ...]  # 稀有词比例高（"设备""供应商"）
        sentiment: [0.1, 0.8, 0.6, ...]  # 负面极性高，唤醒度高
        formality: [0.8, 0.5, 0.9, ...]  # 正式度高，有紧急标记
        numeric:   [1.0, 0.9, 1.0, ...]  # 有数字，大数量级，有货币
        structure: [0.3, 0.5, 0.0, ...]  # 单句，中等长度，非疑问句
        """
        ...
```

#### 1.2 时序感知通道 (TemporalPerceptionChannel)

```python
class TemporalPerceptionChannel:
    """时序感知：从事件流中提取时间特征。
    
    不是预设 urgency，而是让系统观察事件到达的节奏。
    """
    
    CHANNELS = {
        "cadence": {       # 节奏：事件到达频率
            "dim": 4,
            "desc": "arrival_rate, inter_arrival_var, burstiness"
        },
        "novelty": {       # 新奇度：与历史信号的差异
            "dim": 3,
            "desc": "embedding_distance, unseen_patterns, repetition_ratio"
        },
    }
    
    def perceive(self, signal_history: List[Dict]) -> Dict[str, List[float]]:
        """从信号历史中提取时序特征。"""
        ...
```

#### 1.3 感知输出

```python
@dataclass
class PerceptionResult:
    """感知层的输出：多通道特征向量。
    
    不预设语义标签（type/urgency 不再由人工预设，
    而是作为感知通道的一个特征维度）。
    """
    features: Dict[str, List[float]]   # {channel: [values]}
    channels: List[str]                # 激活的通道列表
    raw_text: str = ""                 # 原始文本（供调试）
    text_length: int = 0
    perceived_at: str = ""
    
    def to_flat_vector(self) -> List[float]:
        """展平为向量，供 SNN 输入。"""
        return [v for vals in self.features.values() for v in vals]
    
    def neuron_count(self) -> int:
        return sum(c["dim"] for c in PerceptionChannel.CHANNELS.values())
```

### Layer 2: 感受层 (SentienceNet)

**目标**：从感知特征中提取"感受"——不是决策，是"这个信号让我感觉怎么样"。

#### 2.1 感受空间定义

```python
class Sentiment:
    """感受空间：系统对输入的内在反应。
    
    不是预设标签，是 SNN 激活模式涌现的维度。
    每个感受维度对应一组输出神经元，强度由放电频率/幅度决定。
    """
    # 感受维度（每个维度 2-3 个神经元：强度+方向）
    SENTIENCES = {
        "threat": {          # 威胁感：这个信号是否危险
            "neurons": [30, 31],  # 30=威胁强度, 31=威胁方向(紧急vs可忽略)
            "desc": "高威胁→escalate倾向, 低威胁→auto_approve倾向"
        },
        "safety": {          # 安全感：是否符合已知情境
            "neurons": [32, 33],
            "desc": "高安全→正常处理, 低安全→需要更多信息"
        },
        "interest": {        # 兴趣感：是否值得深入关注
            "neurons": [34, 35],
            "desc": "高兴趣→分配更多认知资源"
        },
        "confusion": {       # 困惑感：是否理解信号
            "neurons": [36, 37],
            "desc": "高困惑→need_info, 低困惑→可决策"
        },
        "urgency": {         # 紧迫感：是否时间敏感（不是预设的 urgency）
            "neurons": [38, 39],
            "desc": "高紧急→优先处理, 低紧急→排队"
        },
        "familiarity": {     # 熟悉感：是否见过类似信号
            "neurons": [40, 41],
            "desc": "高熟悉→走历史模式, 低熟悉→探索"
        },
    }
    # 总计 12 个感受输出神经元 + 感知输入 28 个 = 40 输入输出神经元
```

#### 2.2 SentienceNet 结构

```python
class SentienceNet:
    """感受网络：感知特征 → 感受状态。
    
    复用 SNN 架构（膜电位/放电/突触可塑性），
    但输入是感知特征向量，输出是感受维度。
    """
    
    def __init__(self, path: str):
        self.snn = SNN.load(path)
        if self.snn is None:
            self.snn = self._create_sentience_topology()
            self.snn.save(path)
    
    def _create_sentience_topology(self) -> SNN:
        """创建感受网络拓扑。
        
        与当前 SNN v3 的区别：
        - 输入是感知通道特征（28 神经元），不是人工编码的 type/urgency
        - 隐藏层更宽（50 神经元），支持更复杂的感受映射
        - 输出是感受维度（12 神经元），不是决策
        """
        snn = SNN(num_neurons=52)  # 28 感知输入 + 12 感受输出 + 12 隐藏
        # 感知输入 → 隐藏层：稀疏连接，学习特征到感受的映射
        # 隐藏层 → 感受输出：选择性连接，学习感受涌现规则
        ...
        return snn
    
    def sense(self, perception: PerceptionResult) -> Dict[str, float]:
        """从感知结果产生感受。
        
        返回 {sentiment_name: intensity}，不是决策。
        
        例：
        perception: 88000元设备采购，供应商风险高
        → threat: 0.85, safety: 0.20, interest: 0.70,
          confusion: 0.10, urgency: 0.80, familiarity: 0.30
        
        例：
        perception: "你好"
        → threat: 0.05, safety: 0.90, interest: 0.10,
          confusion: 0.00, urgency: 0.00, familiarity: 0.95
        """
        features = perception.to_flat_vector()
        # 注入感知特征到输入神经元
        active_inputs = self._activate_features(features)
        # SNN 步进
        outputs, _ = self.snn.step_with_learning(active_inputs, learning_rate=0.0)
        # 解码感受
        sentiments = self._decode_sentiments(outputs)
        return sentiments
    
    def _activate_features(self, features: List[float]) -> List[int]:
        """将特征向量转为激活的输入神经元列表。
        
        每个特征值映射到一个感知神经元，
        强度由膜电位注入量决定（不是二值激活）。
        """
        ...
    
    def _decode_sentiments(self, outputs: Dict[int, bool]) -> Dict[str, float]:
        """将输出神经元放电转为感受强度（0-1）。"""
        ...
```

#### 2.3 感受→认知资源分配

```python
class SentienceDrivenBudget:
    """基于感受状态的认知资源分配。
    
    不预设意图，根据感受动态分配脑区资源。
    """
    
    def allocate(self, sentiments: Dict[str, float]) -> Dict[str, RegionBudget]:
        """根据感受分配算力。
        
        规则示例（不是硬编码，是可学习的）：
        - 高 threat → 激活 rule + llm + snn（多脑区协商）
        - 高 confusion → 激活 semantic + episodic（检索记忆）
        - 高 familiarity → 只激活 rule（快速处理）
        - 低 interest → 减少所有脑区资源
        """
        ...
```

### Layer 3: 认知层（现有 coordinator，扩展）

```python
class ReasoningEngineV2:
    """认知主流程：感知 → 感受 → 认知 → 决策。"""
    
    async def reason(self, signal: NeuralSignal, ...) -> CognitionResult:
        # 1. 感知（新增）
        perception = self.perception.perceive(signal.payload)
        
        # 2. 感受（新增）
        sentiments = self.sentience.sense(perception)
        
        # 3. 预算分配（改造：基于感受而非意图）
        plan = self.sentience_budget.allocate(sentiments)
        
        # 4. 并行认知（保留）
        context = {
            "perception": perception,
            "sentiments": sentiments,
            "working_memory": working_memory,
            ...
        }
        result = await self.coordinator.run(signal, context, plan=plan)
        
        # 5. 融合时加入感受一致性检查
        result = self._validate_consistency(result, sentiments)
        return result
    
    def _validate_consistency(self, result, sentiments) -> CognitionResult:
        """诚意检查：决策是否与感受一致。
        
        例：threat=0.9 但 decision=auto_approve → 标记不一致，降级置信度
        例：confusion=0.8 但 decision=escalate → 标记不一致，建议 need_info
        """
        ...
```

### Layer 4: 行动层（现有 ActionExecutor，扩展价值约束）

```python
class ValueConstrainedExecutor:
    """行动执行 + 价值约束层。
    
    在 ActionExecutor 前增加价值检查：
    不是 prompt 里的伦理，而是系统内建的价值约束。
    """
    
    def __init__(self, executor: ActionExecutor):
        self.executor = executor
        # 价值约束（不是规则，是权重——可调整）
        self.values = {
            "safety": 0.9,        # 安全优先
            "fairness": 0.7,      # 公平
            "transparency": 0.8,  # 可解释
        }
    
    async def execute(self, result: CognitionResult) -> List[Action]:
        """执行行动前检查价值约束。
        
        例：decision=auto_approve 但 confidence=0.4 → 检查 safety 价值
            如果 0.4 < safety_threshold(0.6) → 降级为 escalate
        """
        actions = []
        for action in result.actions:
            validated = self._validate_value(action, result)
            if validated:
                actions.append(action)
        return actions
    
    def _validate_value(self, action, result) -> bool:
        """检查行动是否符合价值约束。"""
        ...
```

---

## 四、演进阶段规划

### Phase 0: 基础设施准备（当前已完成）
- [x] SNN 核心（40 神经元，v3 拓扑，12/12 eval）
- [x] Coordinator（并行脑区 + 融合）
- [x] ComputeBudget（意图预算分配）
- [x] ActionExecutor（行动执行）
- [x] Memory 系统（semantic + episodic）
- [x] Shadow SNN（决策一致性）

### Phase 1: 感知层原型（2-3 天）

**目标**：实现 TextPerceptionChannel，从原始文本提取特征向量。

**状态：✅ 已完成（2026-10-27）**

**交付物**：
- [x] `services/brain/perception.py`：TextPerceptionChannel + TemporalPerceptionChannel
- [x] 感知通道定义（lexical/sentiment/formality/numeric/structure，28 维）
- [x] 特征提取函数（中文分词：字符 + bigram 双字词召回）
- [x] PerceptionResult 数据模型
- [x] 单元测试（9 个，全通过）

**接口定义**：
```python
# perception.py
class TextPerceptionChannel:
    def perceive(self, raw_text: str) -> PerceptionResult
    
class TemporalPerceptionChannel:
    def perceive(self, signal_history: List[Dict]) -> PerceptionResult
```

**验收标准**：
- 输入"审批一笔88000元的设备采购费用，供应商风险高"
- 输出 PerceptionResult，包含 5 个通道的特征向量
- 特征向量值合理（不预设语义，只提取统计特征）

### Phase 2: 感受层原型（3-5 天）

**目标**：实现 SentienceNet，从感知特征产生感受。

**状态：✅ 已完成（2026-10-27）**

**交付物**：
- [x] `services/brain/sentience.py`：SentienceNet
- [x] 感受网络拓扑（44 神经元：28 感知输入 + 4 隐藏 + 12 感受输出）
- [x] 感受空间定义（threat/safety/interest/confusion/urgency/familiarity）
- [x] 感受解码（膜电位 + 放电 → 强度 0-1）
- [x] SentienceDrivenBudget（感受→脑区资源分配）
- [x] 单元测试（6 个，全通过）

**接口定义**：
```python
# sentience.py
class SentienceNet:
    def sense(self, perception: PerceptionResult) -> Dict[str, float]
    
class SentienceDrivenBudget:
    def allocate(self, sentiments: Dict[str, float]) -> Dict[str, RegionBudget]
```

**验收标准**：
- 感知"88000元设备采购，供应商风险高" → threat=高, urgency=高, familiarity=低
- 感知"你好" → safety=高, familiarity=高, threat=低
- 感知"审批500元办公用品" → safety=高, threat=低, urgency=低
- SentienceDrivenBudget 根据感受正确分配脑区

### Phase 3: 认知层改造（2-3 天）

**目标**：改造 ReasoningEngine，集成感知+感受流程。

**状态：✅ 已完成（2026-10-27，原型）**

**交付物**：
- [x] `services/brain/reasoning_v2.py`：ReasoningEngineV2
- [x] 感知前置步骤（在 coordinator 之前）
- [x] 感受驱动预算（替代意图预算，SentienceDrivenBudget）
- [x] 诚意检查（决策-感受一致性验证）
- [x] 与现有 coordinator 集成（感受状态注入 context）
- [x] `/brain/ask` 端点支持 engine=v1|v2 参数
- [x] 单元测试（6 个，全通过）
- [x] 生产验证：v2 决策与 v1 一致，无回归

**接口定义**：
```python
# reasoning_v2.py
class ReasoningEngineV2:
    async def reason(self, signal, working_memory, db, memory_context=None) -> CognitionResult
```

**验收标准**：
- /brain/ask 端点使用 V2 流程
- 感知→感受→认知→决策 全链路可观测
- 诚意检查能标记不一致决策

### Phase 4: 学习闭环（3-5 天）

**目标**：让感知层和感受层可学习（不是只靠预设拓扑）。

**交付物**：
- 感受网络的在线学习（反馈→调整感受映射）
- 感知特征的重塑（学习哪些特征对感受最重要）
- 价值约束的校准（根据反馈调整 value weights）

**接口定义**：
```python
# sentience.py
class SentienceNet:
    async def learn(self, perception, sentiments, feedback: str, decision: str):
        """根据反馈调整感受网络。"""
        ...
```

**验收标准**：
- /brain/learn 端点能训练感知+感受层
- 训练后感受网络对新信号的反应更准确
- 价值约束权重根据反馈调整

### Phase 5: 多模态感知（远期）

- 视觉感知（图像特征提取）
- 语音感知（韵律/情感特征）
- 跨模态融合（多通道联合感知）

---

## 五、与现有代码的集成点

### 5.1 新增文件

```
services/brain/
├── perception.py      # Layer 1: 感知层（Phase 1）
├── sentience.py       # Layer 2: 感受层（Phase 2）
├── reasoning_v2.py    # Layer 3: 认知层改造（Phase 3）
├── value_constraints.py  # Layer 4: 价值约束（Phase 3）
```

### 5.2 修改文件

```
models/brain.py:
  + PerceptionResult dataclass
  + Sentiment dataclass

services/brain/coordinator.py:
  - context 增加 "perception" 和 "sentiments" 字段
  - _integrate() 接收感受状态，加入一致性检查

services/brain/compute_budget.py:
  - 保留意图预算（Phase 1-2 期间兼容）
  - 新增 SentienceDrivenBudget（Phase 2）

services/interface/routers/brain.py:
  - /brain/ask 端点切换为 ReasoningEngineV2
  - 保留 /brain/ask/v1 兼容旧版

services/brain/snn_region.py:
  - 当前 SNN v3 降级为 Layer 3 的一个 region（"snn_decision"）
  - 新建 SentienceNet（Layer 2）
```

### 5.3 兼容性策略

- Phase 1-2 期间，`ReasoningEngine.reason()` 保持现有接口
- `/brain/ask` 端点增加 `engine=v1|v2` 参数，默认 v1
- Phase 3 完成后，默认切换为 v2
- 旧版 `/brain/ask/v1` 保留

---

## 六、关键设计决策

### 6.1 感受不是决策

**核心原则**：感受层输出"我感觉怎么样"，不是"我该怎么做"。

```python
# 当前（错误）：
snn_output → decision (auto_approve/escalate/reject)

# 目标（正确）：
sentience_output → sentiments (threat=0.8, safety=0.2, ...)
                  ↓
coordinator + rules + llm → decision (escalate)
```

感受是认知的基础，不是认知本身。决策需要多脑区协商，感受只提供"直觉"。

### 6.2 感知不做语义标注

**核心原则**：感知层只提取特征，不判断语义。

```python
# 当前（错误）：
_encode_signal: signal.type → neuron_id  # 硬编码语义映射

# 目标（正确）：
perceive: raw_text → feature_vector     # 只提取特征
sentience: feature_vector → sentiments   # 学习特征→感受映射
```

"什么是紧急""什么是大额"不应该由人硬编码，而应该由系统从数据中学习。

### 6.3 诚意是验证，不是执行

**核心原则**：诚意检查标记不一致，不直接改决策。

```python
# 诚意检查：
if sentiments["threat"] > 0.7 and decision == "auto_approve":
    result.memory_updates["consistency"] = "threat_decision_mismatch"
    result.confidence *= 0.5  # 降级置信度，不直接改决策
```

### 6.4 价值约束是权重，不是规则

**核心原则**：价值是可调整的权重，不是硬性规则。

```python
# 价值约束：
if confidence < values["safety"]:
    decision = "escalate"  # 安全优先
```

---

## 七、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 感知特征提取质量不足 | 感受层输入噪声大 | Phase 1 先用规则提取，后续替换为 embedding |
| 感受网络过拟合 | 对新信号反应过度 | EWC + 探索率控制（复用现有机制） |
| 诚意检查误报 | 有效决策被标记不一致 | 阈值可配置，先只记录不执行 |
| 与现有架构冲突 | 旧系统无法继续使用 | v1/v2 并行，兼容运行 |
| 训练数据不足 | 感受网络无法学习 | Phase 1-3 用预设拓扑，Phase 4 再学习 |

---

## 八、评估指标

| 阶段 | 指标 | 目标 |
|------|------|------|
| Phase 1 | 感知特征质量 | 人工评估特征向量合理性 |
| Phase 2 | 感受准确性 | 12/12 eval 场景感受方向正确 |
| Phase 3 | 决策一致性 | 诚意检查误报率 < 10% |
| Phase 3 | 决策质量 | 不下降（与 v1 对比） |
| Phase 4 | 学习效果 | 训练后感受准确率提升 |
| Phase 4 | 泛化能力 | 新场景感受方向正确 |

---

## 九、哲学定位

**格物致知**不是"先感知世界再做决策"，而是"通过感知世界来认识自己"。

当前 SNN 的问题不是"不聪明"，而是"不知道自己为什么这么做"。100% eval 通过，但它不知道自己在做什么——它只是规则被神经元模拟了。

类脑 AI 的核心不是决策能力，而是**内在状态**：
- 感受（threat/safety/interest/confusion）是系统对世界的反应
- 诚意（决策与感受一致）是系统对自我的诚实
- 正心（价值约束）是系统对行为的责任

感知是入口，感受是基础，认知是过程，决策是结果。没有前两层，后两层就是空中楼阁。

**下一步**：从 Phase 1 感知层原型开始。不急着优化业务分类，先让系统"看见"世界。
