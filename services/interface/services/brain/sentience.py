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

# 感受维度定义（每个维度 2 个输出神经元，起始 44）
SENTIENCE_DIMS: Dict[str, Dict[str, Any]] = {
    "threat": {"neurons": [44, 45], "desc": "威胁感：信号是否危险"},
    "safety": {"neurons": [46, 47], "desc": "安全感：是否符合已知情境"},
    "interest": {"neurons": [48, 49], "desc": "兴趣感：是否值得深入关注"},
    "confusion": {"neurons": [50, 51], "desc": "困惑感：是否理解信号"},
    "urgency": {"neurons": [52, 53], "desc": "紧迫感：是否时间敏感"},
    "familiarity": {"neurons": [54, 55], "desc": "熟悉感：是否见过类似信号"},
}

# 感受网络规模
SENTIENCE_NUM_NEURONS = 56  # 28 感知输入 + 16 隐藏 + 12 感受输出 (44-55)

# 感知输入神经元起始 ID
PERCEPTION_INPUT_START = 0
# 隐藏层神经元范围（16 个：28-43）
HIDDEN_START = 28
HIDDEN_END = 43
# 感受输出神经元起始
SENTIENCE_OUTPUT_START = 44
# 每个感受维度的专用隐藏组合神经元（2 个）
HIDDEN_PER_SENTIENCE = 2

# 感受维度到隐藏层的映射（每个维度 2 个组合检测神经元）
_SENTIENCE_HIDDEN_BASE: Dict[str, int] = {
    "threat": 28,
    "safety": 30,
    "interest": 32,
    "confusion": 34,
    "urgency": 36,
    "familiarity": 38,
}


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
        # 旧版本文件可能神经元数不足（拓扑已从 44 升级到 56），需重建
        if self.snn is None or self.snn.num_neurons < SENTIENCE_NUM_NEURONS:
            logger.info("sentience: creating/rebuilding default topology (%s)", self.snn.num_neurons if self.snn else None)
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

        28 感知输入 → 16 隐藏层（每个感受维度 2 个组合检测神经元）→ 12 感受输出。
        每个感受维度有专用隐藏组合神经元，学习时针对性调整不泛化。

        与业务 SNN v3 的区别：
        - 输入是感知特征（连续值），不是人工编码
        - 输出是感受，不是决策
        - 每个感受维度有专用隐藏组合层（特征组合检测）
        """
        import random
        random.seed(42)
        net = SNN(num_neurons=SENTIENCE_NUM_NEURONS)

        # 感知输入神经元 0-27（对应 28 维特征）
        for nid in range(PERCEPTION_INPUT_START, 28):
            net.add_neuron(nid, NeuronType.INPUT, threshold=0.3)

        # 隐藏层 28-43（16 个：每个感受维度 2 个组合检测神经元）
        for nid in range(HIDDEN_START, HIDDEN_END + 1):
            net.add_neuron(nid, NeuronType.EXCITATORY, threshold=1.5)

        # 感受输出 44-55（6 维度 × 2）
        for nid in range(SENTIENCE_OUTPUT_START, 56):
            net.add_neuron(nid, NeuronType.OUTPUT, threshold=0.8)

        # ── 结构化感受输出映射（确保基本可读，后续可学习调整） ──
        # 通道: lexical(0-7), sentiment(8-13), formality(14-17),
        #       numeric(18-23), structure(24-27)
        # sentiment: 8=pos, 9=neg, 10=arousal, 11=dominance, 12=uncertainty
        # formality: 14=formal, 15=politeness, 16=urgency_markers, 17=imperative
        # numeric: 18=has_number, 19=magnitude, 20=currency, 21=count
        # structure: 24=sentences, 25=avg_len, 26=has_question, 27=has_exclaim

        # 威胁感 (44,45)：负面情感 + 紧急标记为主，高金额为弱增益
        net.connect(9, 44, weight=3.0, delay=1)    # neg → threat_intensity
        net.connect(16, 44, weight=3.0, delay=1)   # urgency_markers → threat
        net.connect(19, 44, weight=0.5, delay=1)   # magnitude → 弱增益
        net.connect(9, 45, weight=2.0, delay=1)
        net.connect(19, 45, weight=1.5, delay=1)   # magnitude → threat_direction

        # 安全感 (46,47)：正面情感 + 熟悉结构
        net.connect(8, 46, weight=2.0, delay=1)    # pos → safety
        net.connect(11, 46, weight=1.5, delay=1)   # dominance → safety
        net.connect(17, 47, weight=-1.5, delay=1)  # imperative → safety_low
        net.connect(9, 47, weight=-1.5, delay=1)   # neg → safety_low

        # 兴趣感 (48,49)：结构复杂度 + 数值
        net.connect(24, 48, weight=1.5, delay=1)   # sentences → interest
        net.connect(18, 48, weight=1.5, delay=1)   # has_number → interest
        net.connect(25, 49, weight=1.0, delay=1)   # avg_len → interest_depth

        # 困惑感 (50,51)：不确定性 + 疑问结构
        net.connect(12, 50, weight=2.0, delay=1)   # uncertainty → confusion
        net.connect(26, 50, weight=1.5, delay=1)   # has_question → confusion
        net.connect(10, 51, weight=1.0, delay=1)   # arousal → confusion_depth

        # 紧迫感 (52,53)：紧急标记 + 命令式
        net.connect(16, 52, weight=2.5, delay=1)   # urgency_markers → urgency
        net.connect(17, 52, weight=1.5, delay=1)   # imperative → urgency
        net.connect(19, 53, weight=1.0, delay=1)   # magnitude → urgency_depth

        # 熟悉感 (54,55)：词汇稳定性 + 结构
        net.connect(0, 54, weight=1.5, delay=1)    # lexical → familiarity
        net.connect(5, 54, weight=1.0, delay=1)    # unique_ratio → familiarity
        net.connect(9, 55, weight=-1.5, delay=1)   # neg → familiarity_low

        # ── 隐藏组合层：每个感受维度 2 个组合检测神经元 ──
        # 隐藏神经元检测"特征组合"（多输入 AND），驱动对应感受输出
        # 这些是学习的主战场：调整隐藏→感受输出权重可针对性增强/削弱
        # 每个维度的基础特征（组合检测的候选）
        # threat 组合只连 neg+urgency（不连 mag，避免 500元 mag=0.45 误触发）
        # urgency 组合只连 urgency_markers+imperative（不连 mag）
        dim_features: Dict[str, List[int]] = {
            "threat": [9, 16],            # neg + urgency_markers（不含 mag）
            "safety": [8, 11, 17],        # pos + dominance + imperative
            "interest": [18, 24, 25],     # has_number + sentences + avg_len
            "confusion": [12, 26, 10],    # uncertainty + has_question + arousal
            "urgency": [16, 17],          # urgency_markers + imperative（不含 mag）
            "familiarity": [0, 5, 9],     # lexical + unique_ratio + neg
        }
        for dim, features in dim_features.items():
            base = _SENTIENCE_HIDDEN_BASE[dim]
            for k in range(HIDDEN_PER_SENTIENCE):
                hid = base + k
                # 隐藏→感受输出（初始权重 1.0，学习可调）
                out = SENTIENCE_DIMS[dim]["neurons"][0]
                net.connect(hid, out, weight=1.0, delay=1)
                # 特征→隐藏（组合检测：2 个特征即可触发，阈值 1.5）
                for feat in features:
                    net.connect(feat, hid, weight=0.9, delay=1)

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

        # 重置推理状态 + 禁用 Hebbian（纯推理，不改变权重）
        self.snn.reset_learning_state()
        self.snn.enable_hebbian = False

        # 按特征强度注入感知输入
        flat = perception.to_flat_vector()
        self._last_flat = flat
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
        # 金额大额判断：mag>0.55（约金额>3500）才享受全额强度
        # 防止连续金额特征（mag）突触发生后被小额场景泛化
        last_flat = getattr(self, "_last_flat", [])
        mag = last_flat[19] if len(last_flat) > 19 else 0.0
        large_amount = 1.0 if mag > 0.55 else 0.3

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
            # 金额调制：threat/urgency 维度受大额限制
            if dim in ("threat", "urgency") and intensity > 0:
                intensity *= large_amount
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

    # ── 持续学习 ──
    def learn(
        self,
        perception: PerceptionResult,
        sentiments: Dict[str, float],
        feedback: Dict[str, str],
        eta: float = 0.02,
    ) -> Dict[str, Any]:
        """感受层持续学习：根据反馈调整"特征→感受"映射。

        Args:
            perception: 感知结果
            sentiments: 当前感受（sense() 的输出）
            feedback: 期望方向 {"threat": "high"/"low", ...}
            eta: 学习率

        Returns:
            {dim: strengthened/penalized 统计}
        """
        stats: Dict[str, Any] = {}
        flat = perception.to_flat_vector()

        for dim, direction in feedback.items():
            if dim not in SENTIENCE_DIMS:
                continue
            out_neurons = SENTIENCE_DIMS[dim]["neurons"]
            # 期望输出神经元：high → 第1个（强度），low → 削弱
            target = out_neurons[0]

            if direction == "high":
                # 应高：加强该维度的专用隐藏组合→感受输出
                strengthened = self._strengthen_path(flat, target, eta, dim)
                stats[dim] = {"direction": "high", "strengthened": strengthened}
            elif direction == "low":
                # 应低：削弱该维度的专用隐藏组合→感受输出
                penalized = self._penalize_path(flat, target, eta, dim)
                stats[dim] = {"direction": "low", "penalized": penalized}

        self._save()
        self._stats["learn_calls"] = self._stats.get("learn_calls", 0) + 1
        self._save_stats()
        return stats

    def _strengthen_path(self, flat: List[float], target: int, eta: float, dim: str = "") -> int:
        """加强感知特征→目标感受的路径。

        先加强 该维度专用隐藏组合→感受输出 的连接（已被激活的）。
        若无可激活组合（该场景特征未触发维度组合），则尝试突触发生：
        从当前场景的高幅值特征（>0.6，区别于低威胁场景）创建→感受输出。

        这样学习只影响"特定特征组合是否触发感受"，不泛化共享特征。
        """
        strengthened = 0
        active_inputs = [i for i, val in enumerate(flat) if i < 28 and val > 0.05]
        if not active_inputs:
            return 0
        hidden_ids = self._dim_hidden_ids(dim)

        # 1. 加强已被激活的隐藏组合→感受输出
        for hid_id in hidden_ids:
            conn = self.snn.out_edges.get(hid_id, {}).get(target)
            if conn:
                driven = any(
                    self.snn.out_edges.get(i, {}).get(hid_id)
                    for i in active_inputs
                )
                if driven:
                    conn.weight = min(self.snn.max_weight, conn.weight + eta)
                    strengthened += 1

        # 2. 突触发生：无可激活组合时，从高幅值特征创建→感受输出
        if strengthened == 0:
            # 高幅值特征（>0.6）：场景独有特征，区别于低威胁场景
            high_features = [i for i in active_inputs if flat[i] > 0.6]
            for feat in high_features:
                # 若已有连接，加强；否则新建（低权重，需多次学习强化）
                conn = self.snn.out_edges.get(feat, {}).get(target)
                if conn:
                    conn.weight = min(self.snn.max_weight, conn.weight + eta)
                    strengthened += 1
                elif feat not in self.snn.in_edges.get(target, {}):
                    self.snn.connect(feat, target, weight=eta * 2, delay=1)
                    strengthened += 1

        return strengthened

    def _penalize_path(self, flat: List[float], target: int, eta: float, dim: str = "") -> int:
        """削弱感知特征→目标感受的路径。

        只削弱 该维度专用隐藏组合→感受输出 的连接，
        以及当前场景高幅值特征→感受输出 的连接。
        """
        penalized = 0
        active_inputs = [i for i, val in enumerate(flat) if i < 28 and val > 0.05]
        if not active_inputs:
            return 0
        hidden_ids = self._dim_hidden_ids(dim)
        for hid_id in hidden_ids:
            conn = self.snn.out_edges.get(hid_id, {}).get(target)
            if conn and conn.weight > 0:
                driven = any(
                    self.snn.out_edges.get(i, {}).get(hid_id)
                    for i in active_inputs
                )
                if driven:
                    conn.weight = max(0, conn.weight - eta)
                    penalized += 1
        # 削弱高幅值特征→感受输出（学习降低威胁时）
        high_features = [i for i in active_inputs if flat[i] > 0.6]
        for feat in high_features:
            conn = self.snn.out_edges.get(feat, {}).get(target)
            if conn and conn.weight > 0:
                conn.weight = max(0, conn.weight - eta)
                penalized += 1
        return penalized

    def _dim_hidden_ids(self, dim: str) -> List[int]:
        """获取感受维度的专用隐藏组合神经元 ID 列表。"""
        if dim not in _SENTIENCE_HIDDEN_BASE:
            return []
        base = _SENTIENCE_HIDDEN_BASE[dim]
        return [base + k for k in range(HIDDEN_PER_SENTIENCE)]


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
