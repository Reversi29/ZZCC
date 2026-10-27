"""services/brain/sentience.py — Layer 2: 感受层

从感知特征提取"感受"——不是决策，是"这个信号让我感觉怎么样"。

核心原则：
- 感受层输出"我感觉怎么样"，不是"我该怎么做"
- 感受是认知的基础，不是认知本身
- 感受维度：threat/safety/interest/confusion/urgency/familiarity

结构：
- 28 感知输入神经元（对应感知特征通道）
- 16 隐藏层神经元（学习特征→感受映射）
- 12 感受输出神经元（6 感受维度 × 2 神经元：强度+方向）

与业务 SNN 的区别：
- 输入是感知特征向量（连续值，按强度注入），不是人工编码的 type/urgency
- 输出是感受维度，不是决策
- 感受解码基于放电模式，不是预设标签
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.brain.perception import PerceptionResult, CHANNELS
from services.brain.snn import SNN, NeuronType

logger = logging.getLogger("brain.sentience")

# 感受维度定义（每个维度 2 个输出神经元）
SENTIENCE_DIMS: Dict[str, Dict[str, Any]] = {
    "threat": {"neurons": [32, 33], "desc": "威胁感：信号是否危险"},
    "safety": {"neurons": [34, 35], "desc": "安全感：是否符合已知情境"},
    "interest": {"neurons": [36, 37], "desc": "兴趣感：是否值得深入关注"},
    "confusion": {"neurons": [38, 39], "desc": "困惑感：是否理解信号"},
    "urgency": {"neurons": [40, 41], "desc": "紧迫感：是否时间敏感"},
    "familiarity": {"neurons": [42, 43], "desc": "熟悉感：是否见过类似信号"},
}

# 感受网络规模
SENTIENCE_NUM_NEURONS = 44  # 28 感知输入 + 16 隐藏 + 12 感受输出 (32-43) 已含

# 感知输入神经元起始 ID
PERCEPTION_INPUT_START = 0
# 隐藏层神经元范围
HIDDEN_START = 28
HIDDEN_END = 43  # 含 28-43 共 16 个？实际隐藏用 28-31，感受输出 32-43
# 感受输出神经元起始
SENTIENCE_OUTPUT_START = 32


@dataclass
class SentimentState:
    """感受状态：系统对输入的内在反应。"""
    sentiments: Dict[str, float] = field(default_factory=dict)
    firing_neurons: List[int] = field(default_factory=list)
    perceived_at: float = field(default_factory=time.time)

    def get(self, dim: str, default: float = 0.0) -> float:
        return self.sentiments.get(dim, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiments": {k: round(v, 4) for k, v in self.sentiments.items()},
            "firing_neurons": self.firing_neurons,
            "perceived_at": self.perceived_at,
        }


class SentienceNet:
    """感受网络：感知特征 → 感受状态。

    复用 SNN 架构（膜电位/放电/突触可塑性），
    但输入是感知特征向量（连续值，按强度注入），
    输出是感受维度（不是决策）。
    """

    def __init__(self, path: Optional[str] = None):
        self.save_path = path or "/app/config_data/sentience_network.json"
        self.snn = SNN.load(self.save_path)
        if self.snn is None:
            logger.info("sentience: creating default topology")
            self.snn = self._create_sentience_topology()
            self._save()
        self._stats = {
            "sense_calls": 0,
            "total_fires": 0,
            "last_sentiments": {},
        }
        self._load_stats()

    # ── 拓扑创建 ──
    def _create_sentience_topology(self) -> SNN:
        """创建感受网络拓扑。

        28 感知输入 → 16 隐藏层 → 12 感受输出。
        稀疏连接：感知输入与隐藏层随机连接（seed 固定），
        隐藏层与感受输出选择性连接（感受维度映射）。

        与业务 SNN v3 的区别：
        - 输入是感知特征（连续值），不是人工编码
        - 输出是感受，不是决策
        - 初始连接较弱（需要学习），但结构化感受输出映射确保基本可读
        """
        import random
        random.seed(42)
        net = SNN(num_neurons=SENTIENCE_NUM_NEURONS)

        # 感知输入神经元 0-27（对应 28 维特征）
        for nid in range(PERCEPTION_INPUT_START, 28):
            net.add_neuron(nid, NeuronType.INPUT, threshold=0.3)

        # 隐藏层 28-31（初始少量，学习时扩展）
        for nid in range(HIDDEN_START, HIDDEN_START + 4):
            net.add_neuron(nid, NeuronType.EXCITATORY, threshold=1.0)

        # 感受输出 32-43（6 维度 × 2）
        for nid in range(SENTIENCE_OUTPUT_START, 44):
            net.add_neuron(nid, NeuronType.OUTPUT, threshold=0.8)
        # 威胁感 32 需多输入（neg/urgency）触发，阈值提高防 mag 单独触发
        net.neurons[32].threshold = 0.8

        # ── 结构化感受输出映射（确保基本可读，后续可学习调整） ──
        # 每个感受维度从感知通道提取关键特征
        # 通道: lexical(0-7), sentiment(8-13), formality(14-17),
        #       numeric(18-23), structure(24-27)
        # sentiment: 8=pos, 9=neg, 10=arousal, 11=dominance, 12=uncertainty
        # formality: 14=formal, 15=politeness, 16=urgency_markers, 17=imperative
        # numeric: 18=has_number, 19=magnitude, 20=currency, 21=count
        # structure: 24=sentences, 25=avg_len, 26=has_question, 27=has_exclaim

        # 威胁感 (32,33)：负面情感 + 紧急标记为主，高金额为弱增益
        # 32=强度(neg+urgency主导，mag弱增益)，33=方向
        # 500元(neg=0,urgency=0,mag=0.45) → 低威胁
        # 88000元(neg=0.059,urgency=0.059,mag=0.824) → 高威胁
        net.connect(9, 32, weight=3.0, delay=1)    # neg → threat_intensity
        net.connect(16, 32, weight=3.0, delay=1)   # urgency_markers → threat
        net.connect(19, 32, weight=0.5, delay=1)   # magnitude → 弱增益
        net.connect(9, 33, weight=2.0, delay=1)
        net.connect(19, 33, weight=1.5, delay=1)   # magnitude → threat_direction

        # 安全感 (34,35)：正面情感 + 熟悉结构
        net.connect(8, 34, weight=2.0, delay=1)    # pos → safety
        net.connect(11, 34, weight=1.5, delay=1)   # dominance → safety
        net.connect(17, 35, weight=-1.5, delay=1)  # imperative → safety_low
        net.connect(9, 35, weight=-1.5, delay=1)   # neg → safety_low

        # 兴趣感 (36,37)：结构复杂度 + 数值
        net.connect(24, 36, weight=1.5, delay=1)   # sentences → interest
        net.connect(18, 36, weight=1.5, delay=1)   # has_number → interest
        net.connect(25, 37, weight=1.0, delay=1)   # avg_len → interest_depth

        # 困惑感 (38,39)：不确定性 + 疑问结构
        net.connect(12, 38, weight=2.0, delay=1)   # uncertainty → confusion
        net.connect(26, 38, weight=1.5, delay=1)   # has_question → confusion
        net.connect(10, 39, weight=1.0, delay=1)   # arousal → confusion_depth

        # 紧迫感 (40,41)：紧急标记 + 命令式
        net.connect(16, 40, weight=2.5, delay=1)   # urgency_markers → urgency
        net.connect(17, 40, weight=1.5, delay=1)   # imperative → urgency
        net.connect(19, 41, weight=1.0, delay=1)   # magnitude → urgency_depth

        # 熟悉感 (42,43)：词汇稳定性 + 结构
        net.connect(0, 42, weight=1.5, delay=1)    # lexical → familiarity
        net.connect(5, 42, weight=1.0, delay=1)    # unique_ratio → familiarity
        net.connect(9, 43, weight=-1.5, delay=1)   # neg → familiarity_low

        # 隐藏层连接（初始稀疏，供学习扩展）
        # 感知输入 → 隐藏层（随机 8 条）
        candidate_inputs = [0, 8, 9, 12, 16, 17, 18, 19, 24, 26]
        for hid in range(HIDDEN_START, HIDDEN_START + 4):
            for _ in range(2):
                src = random.choice(candidate_inputs)
                net.connect(src, hid, weight=random.uniform(0.5, 1.5), delay=1)
        # 隐藏层 → 感受输出（随机 4 条）
        for _ in range(4):
            hid = random.choice(list(range(HIDDEN_START, HIDDEN_START + 4)))
            out = random.choice(list(range(SENTIENCE_OUTPUT_START, 44)))
            net.connect(hid, out, weight=random.uniform(0.5, 1.0), delay=1)

        return net

    # ── 感受计算 ──
    def sense(self, perception: PerceptionResult) -> SentimentState:
        """从感知结果产生感受。

        Args:
            perception: 感知结果（多通道特征向量）

        Returns:
            SentimentState — {sentiment: intensity}
        """
        self._stats["sense_calls"] += 1

        # 重置推理状态
        self.snn.reset_learning_state()

        # 按特征强度注入感知输入
        flat = perception.to_flat_vector()
        active_inputs = self._inject_features(flat)

        # 运行多个时间步
        outputs: Dict[int, bool] = {}
        for step in range(10):
            outputs = self.snn.step()
            fired = [nid for nid, v in outputs.items() if v]
            if fired and step >= 3:
                break

        # 解码感受
        sentiments = self._decode_sentiments(outputs)
        firing = [nid for nid, v in outputs.items() if v]

        self._stats["total_fires"] += len(firing)
        self._stats["last_sentiments"] = sentiments
        self._save_stats()

        return SentimentState(
            sentiments=sentiments,
            firing_neurons=firing,
        )

    def _inject_features(self, flat: List[float]) -> List[int]:
        """将特征向量按强度注入感知输入神经元。

        用 rate coding：特征值决定放电频率，而非膜电位幅度。
        - 特征 > 0.05：激活该输入神经元
        - 特征值越大，重复注入越多（模拟高频放电）
        """
        active: List[int] = []
        for i, val in enumerate(flat):
            if i >= 28:
                break
            if val > 0.05:
                active.append(i)
                # 特征值越大，注入次数越多（模拟放电频率）
                repeats = max(1, int(val * 10))
                for _ in range(repeats):
                    self.snn.inject_input(i, strength=1.0)
        if not active:
            active = [10]  # 默认激活（无显著特征）
        return active

    def _decode_sentiments(self, outputs: Dict[int, bool]) -> Dict[str, float]:
        """将输出神经元放电转为感受强度（0-1）。

        每个感受维度 2 个输出神经元：
        - 第 1 个（强度）：正相关
        - 第 2 个（方向）：正或负相关
        用膜电位连续值 + 放电综合判断（不用二值，避免信息丢失）。
        """
        sentiments: Dict[str, float] = {}
        for dim, cfg in SENTIENCE_DIMS.items():
            n1, n2 = cfg["neurons"]
            # 用膜电位 + 放电综合：膜电位越高感受越强
            mem1 = max(0.0, self.snn.neurons[n1].membrane)
            mem2 = max(0.0, self.snn.neurons[n2].membrane)
            fired1 = self.snn.neurons[n1].last_fire_time >= 0
            fired2 = self.snn.neurons[n2].last_fire_time >= 0

            # 放电 → 基础强度 0.7+；未放电 → 用膜电位比例
            base = 0.7 + (0.3 if fired2 else 0.0) if fired1 else 0.0
            # 膜电位贡献（0-1 缩放）
            mem_contrib = min(1.0, (mem1 + mem2) / 3.0) * 0.5
            intensity = max(base, mem_contrib)
            sentiments[dim] = round(min(1.0, intensity), 4)
        return sentiments

    # ── 持久化 ──
    def _save(self) -> None:
        try:
            self.snn.save(self.save_path)
        except Exception as e:
            logger.warning("sentience: save failed: %s", str(e))

    def _load_stats(self) -> None:
        stats_path = self.save_path.replace(".json", "_stats.json")
        try:
            if os.path.exists(stats_path):
                with open(stats_path, "r") as f:
                    self._stats.update(json.load(f))
        except Exception:
            pass

    def _save_stats(self) -> None:
        stats_path = self.save_path.replace(".json", "_stats.json")
        try:
            os.makedirs(os.path.dirname(stats_path), exist_ok=True)
            with open(stats_path, "w") as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)


# ── 感受驱动预算 ──
class SentienceDrivenBudget:
    """基于感受状态的认知资源分配。

    不预设意图，根据感受动态分配脑区资源。
    """

    def __init__(self, base_budget):
        self.base_budget = base_budget

    def allocate(self, sentiments: Dict[str, float]) -> Dict[str, Any]:
        """根据感受分配算力。

        规则（示例，可学习）：
        - 高 threat → 激活 rule + llm + snn（多脑区协商）
        - 高 confusion → 激活 semantic + episodic（检索记忆）
        - 高 familiarity → 只激活 rule（快速处理）
        - 低 interest → 减少所有脑区资源

        返回 {region_name: RegionBudget}，与 v1 ComputeBudget 兼容。
        """
        from services.brain.compute_budget import RegionBudget

        threat = sentiments.get("threat", 0.0)
        confusion = sentiments.get("confusion", 0.0)
        familiarity = sentiments.get("familiarity", 0.0)
        urgency = sentiments.get("urgency", 0.0)
        safety = sentiments.get("safety", 0.0)

        def _b(time_ms: float, tokens: int) -> RegionBudget:
            return RegionBudget(
                time_ms=time_ms,
                tokens=tokens,
                allowed=time_ms > 0 or tokens > 0,
            )

        plan: Dict[str, RegionBudget] = {}

        # 闲聊/安全感受：只激活 rule（快速），不激活 SNN（避免误审批）
        if safety > 0.6 and threat < 0.2:
            plan["rule"] = _b(30, 0)
            plan["llm"] = _b(10000, 512)
            plan["snn"] = _b(0, 0)
            plan["semantic"] = _b(0, 0)
            plan["episodic"] = _b(300, 0)
            return plan

        # 高威胁：增强 rule/llm/snn（多脑区协商）
        if threat > 0.7:
            plan["rule"] = _b(100, 0)
            plan["statistical"] = _b(200, 0)
            plan["llm"] = _b(45000, 4096)
            plan["snn"] = _b(800, 0)
            plan["semantic"] = _b(2000, 0)
            plan["episodic"] = _b(800, 0)
            plan["shadow:snn_aux"] = _b(300, 0)
            return plan

        # 高困惑：增强 semantic/episodic（检索记忆）
        if confusion > 0.6:
            plan["rule"] = _b(50, 0)
            plan["llm"] = _b(20000, 1024)
            plan["snn"] = _b(0, 0)
            plan["semantic"] = _b(2000, 0)
            plan["episodic"] = _b(1000, 0)
            return plan

        # 高熟悉：快速处理，减少 LLM
        if familiarity > 0.8:
            plan["rule"] = _b(50, 0)
            plan["llm"] = _b(5000, 512)
            plan["snn"] = _b(500, 0)
            plan["semantic"] = _b(1500, 0)
            plan["episodic"] = _b(500, 0)
            return plan

        # 默认：标准业务预算
        plan["rule"] = _b(50, 0)
        plan["statistical"] = _b(200, 0)
        plan["llm"] = _b(30000, 2048)
        plan["snn"] = _b(500, 0)
        plan["semantic"] = _b(1500, 0)
        plan["episodic"] = _b(500, 0)
        plan["shadow:snn_aux"] = _b(300, 0)
        return plan
