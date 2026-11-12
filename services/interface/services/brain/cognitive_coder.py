"""services/brain/cognitive_coder.py — Layer 2.5: 多模态认知编码器（认知对齐）

格物致知：感知(perception) → 认知编码(cognitive_coder) → 感受(sentience) → 决策。

问题背景：
    多模态认知对齐的目标是"视觉认苹果、文字/音频映射到同一概念"。
    不同模态（视觉/语言/音频）通过各自感知通道产生特征，但必须
    对齐到**同一个概念表征**，否则"苹果的图片"和"苹果的文字"在
    系统里是两回事，无法形成统一认知。

设计：
    CognitiveCoder 是统一概念编码器。它接收多模态感知输入，输出
    一个**统一概念向量**（unified concept embedding），维度固定
    （CONCEPT_DIMS），每个维度代表一个抽象概念（如 apple/danger/
    urgency/approval...）。

    编码方式（Phase 2）：每个模态有一个独立 SNN（ModalSNNEncoder），
    把该模态的原始特征编码为"模态概念激活"。所有模态概念激活通过
    对齐层融合到统一概念空间。

    Phase 1：规则式编码（_text_to_concepts/_visual_to_concepts/
    _audio_to_concepts）+ 加权融合，可解释、无需训练。
    Phase 2：模态专用 SNN 编码（ModalSNNEncoder），用规则式编码
    作为教师信号蒸馏初始化，再通过对比学习（跨模态互信息）微调。

    对齐层是学习的主战场：不同模态对同一概念的激活通过对比学习
    收敛到同一概念维度。

    这样：
    - 视觉"苹果图片" → 概念向量 [apple=0.9, ...]
    - 文字"苹果" → 概念向量 [apple=0.85, ...]
    - 两个概念向量接近 → 系统知道是同一个"苹果"

    输出对齐后的概念向量直接喂给感受层（sentience），感受层对概念
    响应（如 apple 概念 → familiarity 升高），实现跨模态统一感受。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("brain.cognitive_coder")

# ── 概念维度配置 ──
# 每个维度是一个抽象概念。概念空间是开放集，可动态扩展。
CONCEPT_NAMES: List[str] = [
    "apple",        # 0: 苹果
    "danger",       # 1: 危险
    "urgency",      # 2: 紧急
    "approval",     # 3: 审批通过
    "rejection",    # 4: 拒绝
    "escalation",   # 5: 升级
    "query",        # 6: 查询/疑问
    "chitchat",     # 7: 闲聊
    "familiarity",  # 8: 熟悉
    "novelty",      # 9: 新颖
]

CONCEPT_DIMS = len(CONCEPT_NAMES)

# 概念索引映射
CONCEPT_IDX: Dict[str, int] = {name: i for i, name in enumerate(CONCEPT_NAMES)}


class ConceptRegistry:
    """概念空间开放集注册表。

    初始概念空间固定（CONCEPT_NAMES），但支持动态注册新概念
    （如视觉认出'香蕉'→register('banana')→分配新维度）。

    参照 neuro_registry.InputRegistry 模式：
    - 初始固定概念
    - register(name) 动态分配新维度
    - get/all 查询
    """

    def __init__(self, initial: Optional[List[str]] = None):
        self.names: List[str] = list(initial or CONCEPT_NAMES)
        self.idx: Dict[str, int] = {name: i for i, name in enumerate(self.names)}
        self._next_slot = len(self.names)
        # 概念别名（中文名等）：alias → canonical name
        self.aliases: Dict[str, str] = {}

    def register(self, name: str, aliases: Optional[List[str]] = None) -> int:
        """注册新概念，返回维度索引。已存在则返回原索引。

        Args:
            name: 规范概念名（如 banana）
            aliases: 别名列表（如 ["香蕉"]），用于多语言/多模态匹配
        """
        if name in self.idx:
            return self.idx[name]
        idx = self._next_slot
        self._next_slot += 1
        self.names.append(name)
        self.idx[name] = idx
        if aliases:
            for a in aliases:
                self.aliases[a] = name
        return idx

    def resolve(self, token: str) -> Optional[str]:
        """解析 token 到规范概念名（含别名）。"""
        if token in self.idx:
            return token
        return self.aliases.get(token)

    def get(self, name: str) -> Optional[int]:
        """查询概念维度索引。"""
        return self.idx.get(name)

    def all(self) -> List[str]:
        """全部概念名。"""
        return list(self.names)

    def __len__(self) -> int:
        return len(self.names)


@dataclass
class ConceptVector:
    """统一概念向量：多模态对齐后的认知表征。

    每个维度 [0,1] 表示该概念的激活强度。
    """
    concepts: Dict[str, float] = field(default_factory=dict)
    modality_sources: Dict[str, List[str]] = field(default_factory=dict)  # 概念 → 贡献模态
    aligned_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concepts": {k: round(v, 3) for k, v in self.concepts.items()},
            "modality_sources": self.modality_sources,
            "aligned_at": self.aligned_at,
        }

    def to_vector(self) -> List[float]:
        """转固定维度向量。"""
        return [self.concepts.get(name, 0.0) for name in CONCEPT_NAMES]

    def dominant(self, top: int = 3) -> List[Dict[str, Any]]:
        """Top-N 主导概念。"""
        sorted_c = sorted(self.concepts.items(), key=lambda x: x[1], reverse=True)
        return [
            {"concept": k, "strength": round(v, 3)}
            for k, v in sorted_c[:top]
            if v > 0.05
        ]


# ── 模态特征定义 ──
# 视觉特征维度
VISUAL_FEATURES = ["red", "green", "blue", "round", "square", "large", "small", "bright", "dark"]
# 音频特征维度
AUDIO_FEATURES = ["loudness", "pitch", "rhythm"]
# 文本语义特征维度（低层特征，非概念；SNN 学习特征→概念推理）
TEXT_FEATURES = [
    "urgent_marker",   # 紧急标记（urgent/asap/立即/加急）
    "risk_marker",     # 风险标记（danger/risk/critical/违规）
    "has_number",      # 数值存在（有金额/数量）
    "query_marker",    # 疑问句（?/请问/查询）
    "approval_marker", # 审批标记（批准/同意/通过）
    "rejection_marker",# 拒绝标记（拒绝/驳回）
    "greeting_marker", # 问候标记（hello/hi/你好）
    "apple_marker",    # 苹果标记（apple/苹果）
]

# 概念的先验特征（规则式初始化用，Phase 2 可被 SNN 学习替代）
# 视觉：红+圆→apple，暗+红→danger，亮→novelty
_VISUAL_CONCEPT_PRIOR = {
    "apple": ["red", "green", "round"],
    "danger": ["dark", "red"],
    "novelty": ["bright"],
}
# 音频：响度+音调→danger/urgency
_AUDIO_CONCEPT_PRIOR = {
    "danger": ["loudness", "pitch"],
    "urgency": ["loudness", "pitch"],
}
# 文本：低层语义特征→概念（三模态对称）
_TEXT_CONCEPT_PRIOR = {
    "urgency": ["urgent_marker"],
    "danger": ["risk_marker"],
    "approval": ["approval_marker"],
    "rejection": ["rejection_marker"],
    "query": ["query_marker"],
    "chitchat": ["greeting_marker"],
    "apple": ["apple_marker"],
}


# ── 模态专用 SNN 编码器 ──
class ModalSNNEncoder:
    """模态专用 SNN 编码器。

    每个模态一个小 SNN：
    - 输入层 = 模态特征维度（视觉 9 / 音频 3）
    - 隐藏层 = 每个概念一个检测神经元
    - 输出层 = 概念激活（CONCEPT_DIMS）

    用规则式先验初始化连接（特征→概念的先验映射），
    再用蒸馏/对比学习训练。Phase 2 核心。

    使用本地轻量脉冲网络（复用 SNN 类，纯 Python，无重依赖）。
    """

    def __init__(self, modality: str, feature_names: List[str], concept_prior: Dict[str, List[str]],
                 registry: Optional[ConceptRegistry] = None):
        self.modality = modality
        self.feature_names = list(feature_names)
        self.concept_prior = concept_prior
        self.registry = registry or ConceptRegistry()
        self.num_features = len(self.feature_names)
        # 神经元布局：0..num_features-1 输入，num_features..num_features+len(registry)-1 概念检测，+len 输出
        self._input_start = 0
        self._hidden_start = self.num_features
        self._output_start = self.num_features + len(self.registry)
        self.num_neurons = self._output_start + len(self.registry)

        # 纯 Python 脉冲网络状态（轻量，不依赖 SNN 类避免循环依赖）
        self._init_network()

    def _concept_count(self) -> int:
        """当前概念数（实例级，支持动态注册）。"""
        return len(self.registry)

    def register_feature(self, name: str) -> int:
        """动态注册新感知特征（开放集）。

        新物体特征（如 yellow/curved）动态注册，扩展输入层维度。
        注册后重建网络（输入→概念检测→输出），概念先验连接重建。

        Args:
            name: 特征名（如 yellow）

        Returns:
            特征索引（已存在则返回原索引）
        """
        if name in self.feature_names:
            return self.feature_names.index(name)
        # 追加特征，重建网络布局
        self.feature_names.append(name)
        self.num_features = len(self.feature_names)
        self._hidden_start = self.num_features
        self._output_start = self.num_features + len(self.registry)
        self.num_neurons = self._output_start + len(self.registry)
        # 重建网络（保留 registry 概念，先验连接重建）
        self._init_network()
        return self.num_features - 1

    def _init_network(self):
        """初始化完整 SNN 实例（升级：真正的脉冲动力学 + STDP）。

        神经元布局：
        - 0..F-1 输入层（特征，阈值 0.5）
        - F..F+C-1 概念检测层（阈值 0.5，先验连接）
        - F+C..F+2C-1 概念输出层（阈值 0.3）

        用 snn.py 的完整 SNN 类建拓扑，enable_hebbian 控制 STDP。
        蒸馏（有监督）用 set_weight 直接更新，推理时 enable_hebbian=False
        防意外 LTD（主 SNN 的 Hebbian bug 教训）。
        """
        from services.brain.snn import SNN, NeuronType

        self._input_start = 0
        self._hidden_start = self.num_features
        self._output_start = self.num_features + len(self.registry)
        total = self._output_start + len(self.registry)
        self.num_neurons = total

        # 完整 SNN 实例
        self.snn = SNN(num_neurons=total)
        # 输入层：特征神经元
        for i in range(self.num_features):
            self.snn.add_neuron(i, NeuronType.INPUT, threshold=0.5)
        # 概念检测层（阈值 1.0：AND 门，靠连接权重区分单/多特征）
        for i in range(self._hidden_start, self._output_start):
            self.snn.add_neuron(i, NeuronType.EXCITATORY, threshold=1.0)
        # 概念输出层
        for i in range(self._output_start, total):
            self.snn.add_neuron(i, NeuronType.OUTPUT, threshold=0.3)

        # 先验连接：特征 → 概念检测（权重适应先验特征数）
        # 单特征概念（如 novelty=[bright]）：权重 1.5，单特征放电
        # 多特征概念（如 apple=[red,green,round]）：权重 0.9，需≥2 特征放电（AND）
        for cidx, concept in enumerate(self.registry.all()):
            feats = self.concept_prior.get(concept, [])
            w = 1.5 if len(feats) <= 1 else 0.9
            for feat in feats:
                if feat in self.feature_names:
                    fidx = self.feature_names.index(feat)
                    self.snn.connect(fidx, self._hidden_start + cidx, weight=w)
        # 概念检测 → 概念输出
        self._rebuild_hidden_output()
        # 推理时禁用 Hebbian（防意外 LTD）
        self.snn.enable_hebbian = False

    def _set_weight(self, src: int, tgt: int, w: float):
        """更新完整 SNN 权重（连接不存在则新建，兼容轻量模型 setdefault）。"""
        if hasattr(self, "snn"):
            conn = self.snn.out_edges.get(src, {}).get(tgt)
            if conn:
                self.snn.set_weight(src, tgt, w)
            else:
                # 新连接：connect 建连接（延迟 1，默认阈值传播）
                self.snn.connect(src, tgt, weight=max(0, min(3.0, w)), delay=1)
        else:
            self.weights.setdefault(src, {})[tgt] = w

    def _get_weight(self, src: int, tgt: int) -> float:
        """读取完整 SNN 权重（兼容轻量模型回退）。"""
        if hasattr(self, "snn"):
            conn = self.snn.out_edges.get(src, {}).get(tgt)
            return conn.weight if conn else 0.0
        return self.weights.get(src, {}).get(tgt, 0.0)

    def encode(self, features: Dict[str, float]) -> Dict[str, float]:
        """模态特征 → 概念激活（完整 SNN 脉冲传播）。

        输入特征注入 → 概念检测神经元积分 → 放电 → 概念输出激活。
        返回 {concept: activation}。
        """
        # 推理时禁用 Hebbian（防意外 LTD）
        self.snn.enable_hebbian = False
        # 重置状态（清前次编码残留膜电位/事件，不清权重）
        self.snn.reset()
        # 1. 注入输入特征（增益中性：概念编码不需连续通道 gain，
        # 避免 gain(1+s*0.55) 放大传播导致单特征误激活）
        for fname, fval in features.items():
            if fname in self.feature_names:
                self.snn.inject_input(self.feature_names.index(fname), fval)

        # 2. 脉冲传播（输入→概念检测→概念输出）
        activations: Dict[str, float] = {}
        max_act: Dict[int, float] = {}
        for _ in range(5):
            self.snn.step()
            out = self.snn.get_outputs()
            for nid, firing in out.items():
                if firing:
                    cidx = nid - self._output_start
                    if 0 <= cidx < self._concept_count():
                        max_act[nid] = max(max_act.get(nid, 0.0), 1.0)
        # 3. 概念激活（放电即激活；膜电位已清零，用放电记录）
        for cidx in range(self._concept_count()):
            out_nid = self._output_start + cidx
            if out_nid in max_act:
                activations[self.registry.all()[cidx]] = 1.0
        return activations

    def distill_step(self, features: Dict[str, float], teacher: Dict[str, float], eta: float = 0.05):
        """蒸馏训练：让 SNN 逼近规则式教师编码。

        对教师激活的概念，加强其特征→概念检测的连接；
        对教师未激活的概念，削弱（如果误激活）。

        Args:
            features: 模态特征
            teacher: 规则式教师编码 {concept: strength}
            eta: 学习率
        """
        # ── 脉冲前向 + STDP（方向2：真正的脉冲学习） ──
        # 训练时启用 Hebbian：特征放电→概念检测跟随（delay+2 窗口）→LTP
        # 时序因果强化教师概念的路径；delta 规则下方补突触发生（新连接）
        self.snn.enable_hebbian = True
        self.snn.reset()
        for fname, fval in features.items():
            if fname in self.feature_names:
                self.snn.inject_input(self.feature_names.index(fname), fval)
        for _ in range(4):
            self.snn.step()
        self.snn.enable_hebbian = False

        for concept, t_val in teacher.items():
            cidx = self.registry.get(concept)
            if cidx is None:
                continue
            hid = self._hidden_start + cidx
            if t_val > 0.3:
                # 教师激活：加强该概念的特征连接
                feats = self.concept_prior.get(concept, [])
                # 无先验特征 → 突触发生：用输入高幅值特征建立连接
                if not feats:
                    feats = [f for f, v in features.items() if v > 0.5]
                for feat in feats:
                    if feat in self.feature_names:
                        fidx = self.feature_names.index(feat)
                        cur = self._get_weight(fidx, hid)
                        self._set_weight(fidx, hid, min(3.0, cur + eta))
            else:
                # 教师未激活：削弱该概念连接（如果过高）
                feats = self.concept_prior.get(concept, [])
                for feat in feats:
                    if feat in self.feature_names:
                        fidx = self.feature_names.index(feat)
                        cur = self._get_weight(fidx, hid)
                        if cur > 0.3:
                            self._set_weight(fidx, hid, max(0.1, cur - eta * 0.5))

    def register_concept(self, name: str, prior_features: Optional[List[str]] = None) -> int:
        """动态注册新概念（开放集）。

        新概念分配新维度，并建立先验特征→概念检测连接。

        Args:
            name: 概念名（如 banana）
            prior_features: 先验特征列表（如 ["yellow", "curved"]）

        Returns:
            新概念维度索引
        """
        from services.brain.snn import NeuronType
        cidx = self.registry.register(name)
        # 更新输出层起始位置：隐藏层容量 = 概念数，输出层紧随其后
        # 关键：保证隐藏层与输出层不重叠（_output_start >= _hidden_start + len(registry)）
        self._output_start = self.num_features + len(self.registry)
        # 扩展神经元容量（完整 SNN：add_neuron）
        new_num_neurons = self._output_start + len(self.registry)
        if new_num_neurons > self.num_neurons:
            # 新增概念检测神经元（阈值 1.0：AND 门）
            for i in range(self.num_neurons, new_num_neurons):
                if i >= self._hidden_start and i < self._output_start:
                    self.snn.add_neuron(i, NeuronType.EXCITATORY, threshold=1.0)
                else:
                    self.snn.add_neuron(i, NeuronType.OUTPUT, threshold=0.3)
            self.num_neurons = new_num_neurons

        # 建立先验连接（权重适配先验特征数：单特征 1.5，多特征 0.9）
        if prior_features:
            w = 1.5 if len(prior_features) <= 1 else 0.9
            for feat in prior_features:
                if feat in self.feature_names:
                    fidx = self.feature_names.index(feat)
                    self._set_weight(fidx, self._hidden_start + cidx, w)
        # 重建所有 hidden→output 连接（用新的 _output_start，保证不重叠）
        self._rebuild_hidden_output()
        return cidx

    def _rebuild_hidden_output(self):
        """重建所有 hidden→output 连接（概念数变化后调用）。

        保证隐藏层神经元（_hidden_start + cidx）连到正确的输出
        （_output_start + cidx），避免概念数变化后错位。
        """
        # 移除旧 hidden→output 连接（完整 SNN 用 disconnect）
        if hasattr(self, "snn"):
            for src in list(self.snn.out_edges.keys()):
                for tgt in list(self.snn.out_edges[src].keys()):
                    if self._hidden_start <= src < self._output_start and tgt >= self._output_start:
                        self.snn.disconnect(src, tgt)
        else:
            for src in list(self.weights.keys()):
                for tgt in list(self.weights[src].keys()):
                    if self._hidden_start <= src < self._output_start and tgt >= self._output_start:
                        del self.weights[src][tgt]
        # 重建
        for cidx in range(len(self.registry)):
            hid = self._hidden_start + cidx
            out = self._output_start + cidx
            self._set_weight(hid, out, 1.0)


# ── 模态特征提取（Phase 1 规则式） ──
def _visual_to_concepts(visual_features: Dict[str, float]) -> Dict[str, float]:
    """视觉特征 → 概念假设（规则式，Phase 1）。"""
    concepts: Dict[str, float] = {}
    red = visual_features.get("red", 0.0)
    green = visual_features.get("green", 0.0)
    round_s = visual_features.get("round", 0.0)
    bright = visual_features.get("bright", 0.0)
    dark = visual_features.get("dark", 0.0)

    apple = (red + green) / 2.0 * round_s
    if apple > 0.1:
        concepts["apple"] = min(1.0, apple)
    danger = (dark * 0.5 + red * 0.3)
    if danger > 0.1:
        concepts["danger"] = min(1.0, danger)
    if bright > 0.6:
        concepts["novelty"] = min(1.0, bright * 0.7)

    return concepts


def _text_to_concepts(text: str) -> Dict[str, float]:
    """文本特征 → 概念假设（关键词规则，Phase 1）。"""
    concepts: Dict[str, float] = {}
    if not text:
        return concepts
    t = text.lower()

    if any(k in t for k in ("苹果", "apple")):
        concepts["apple"] = 0.9
    if any(k in t for k in ("危险", "风险", "违规", "danger", "risk", "critical")):
        concepts["danger"] = 0.9
    if any(k in t for k in ("紧急", "立即", "马上", "加急", "urgent", "asap")):
        concepts["urgency"] = 0.9
    if any(k in t for k in ("批准", "同意", "通过", "审批", "approve", "approved", "ok")):
        concepts["approval"] = 0.8
    if any(k in t for k in ("拒绝", "驳回", "reject", "deny")):
        concepts["rejection"] = 0.8
    if any(k in t for k in ("升级", "上报", "escalate", "escalation")):
        concepts["escalation"] = 0.8
    if any(k in t for k in ("?", "？", "查询", "请问", "query", "how", "where", "when")):
        concepts["query"] = 0.7
    if any(k in t for k in ("hello", "hi", "你好", "哈哈", "呵呵", "nice", "great")):
        concepts["chitchat"] = 0.7

    return concepts


def _text_to_features(text: str) -> Dict[str, float]:
    """文本 → 低层语义特征（非概念，供 text_snn 编码）。

    提取低层语义指示器：紧急/风险/数值/疑问/审批/拒绝/问候/苹果。
    这些是原始信号（非概念），SNN 学习特征→概念推理。
    """
    feats: Dict[str, float] = {}
    if not text:
        return feats
    t = text.lower()
    if any(k in t for k in ("紧急", "立即", "马上", "加急", "urgent", "asap")):
        feats["urgent_marker"] = 0.9
    if any(k in t for k in ("危险", "风险", "违规", "danger", "risk", "critical")):
        feats["risk_marker"] = 0.9
    if any(k in t for k in ("?", "？", "查询", "请问", "query", "how", "where", "when")):
        feats["query_marker"] = 0.7
    if any(k in t for k in ("批准", "同意", "通过", "审批", "approve", "approved", "ok")):
        feats["approval_marker"] = 0.8
    if any(k in t for k in ("拒绝", "驳回", "reject", "deny")):
        feats["rejection_marker"] = 0.8
    if any(k in t for k in ("hello", "hi", "你好", "哈哈", "呵呵", "nice", "great")):
        feats["greeting_marker"] = 0.7
    if any(k in t for k in ("苹果", "apple")):
        feats["apple_marker"] = 0.9
    # 数值存在（金额/数量）
    import re
    if re.search(r"\d", text):
        feats["has_number"] = 0.6
    return feats


def _audio_to_concepts(audio_features: Dict[str, float]) -> Dict[str, float]:
    """音频特征 → 概念假设（规则式，Phase 1）。"""
    concepts: Dict[str, float] = {}
    loudness = audio_features.get("loudness", 0.0)
    pitch = audio_features.get("pitch", 0.0)

    alarm = loudness * pitch
    if alarm > 0.2:
        concepts["danger"] = min(1.0, alarm)
        concepts["urgency"] = min(1.0, alarm * 0.8)

    return concepts


# ── 多模态对齐 ──
class CognitiveCoder:
    """多模态认知编码器：各模态特征 → 统一概念空间。

    职责：
    1. 接收多模态原始特征（视觉/文本/音频）
    2. 每模态独立编码为概念假设
    3. 对齐层融合（对比学习收敛到统一概念）
    4. 输出 ConceptVector（统一概念向量）

    Phase 1：规则式编码 + 加权融合（可学习）。
    Phase 2：模态专用 SNN 编码（ModalSNNEncoder）+ 蒸馏/对比学习。
    """

    def __init__(self):
        self._stats = {
            "encode_calls": 0,
            "alignment_strength": 0.0,
            "distill_calls": 0,
        }
        # 概念空间开放集注册表（视觉/音频 SNN 共享）
        self.registry = ConceptRegistry()
        # 模态权重（可学习，Phase 2 自动调整）
        self.modality_weights: Dict[str, float] = {
            "visual": 1.0,
            "text": 1.0,
            "audio": 1.0,
        }
        # 模态专用 SNN 编码器（Phase 2，共享概念注册表）
        self.visual_snn = ModalSNNEncoder("visual", VISUAL_FEATURES, _VISUAL_CONCEPT_PRIOR, registry=self.registry)
        self.audio_snn = ModalSNNEncoder("audio", AUDIO_FEATURES, _AUDIO_CONCEPT_PRIOR, registry=self.registry)
        # 文本模态 SNN（三模态对称）：低层语义特征 → 概念
        self.text_snn = ModalSNNEncoder("text", TEXT_FEATURES, _TEXT_CONCEPT_PRIOR, registry=self.registry)
        # Phase 2 开关：默认用 SNN 编码（有先验初始化，冷启动可用）
        self.use_snn_encoding = True
        # 真实标注训练样本积累（方向3：反馈驱动）
        self._pending_training_samples: List[Dict[str, Any]] = []
        self._training_batch_size: int = 10
        self._training_eta: float = 0.05

    def register_concept(self, name: str, prior_features: Optional[Dict[str, List[str]]] = None,
                         aliases: Optional[List[str]] = None) -> int:
        """动态注册新概念（开放集）。

        新概念在视觉/音频 SNN 中同步注册，分配新维度。

        Args:
            name: 概念名（如 banana）
            prior_features: 各模态先验特征 {"visual": [...], "audio": [...]}
            aliases: 概念别名（如 ["香蕉"]），用于多语言匹配

        Returns:
            新概念维度索引
        """
        idx = self.registry.register(name, aliases=aliases)
        # 视觉 SNN 同步注册（先注册未知特征，再注册概念）
        vis_priors = (prior_features or {}).get("visual")
        if vis_priors:
            for feat in vis_priors:
                if feat not in self.visual_snn.feature_names:
                    self.visual_snn.register_feature(feat)
        self.visual_snn.register_concept(name, vis_priors)
        # 音频 SNN 同步注册
        aud_priors = (prior_features or {}).get("audio")
        if aud_priors:
            for feat in aud_priors:
                if feat not in self.audio_snn.feature_names:
                    self.audio_snn.register_feature(feat)
        self.audio_snn.register_concept(name, aud_priors)
        # 文本 SNN 同步注册
        txt_priors = (prior_features or {}).get("text")
        if txt_priors:
            for feat in txt_priors:
                if feat not in self.text_snn.feature_names:
                    self.text_snn.register_feature(feat)
        self.text_snn.register_concept(name, txt_priors)
        self._stats["registered_concepts"] = self._stats.get("registered_concepts", 0) + 1
        return idx

    def register_feature(self, modality: str, name: str) -> int:
        """动态注册新感知特征（开放集）。

        Args:
            modality: 模态（visual/audio）
            name: 特征名（如 yellow/curved）

        Returns:
            特征索引
        """
        if modality == "visual":
            return self.visual_snn.register_feature(name)
        elif modality == "audio":
            return self.audio_snn.register_feature(name)
        raise ValueError(f"unknown modality: {modality}")

    def encode(
        self,
        text: str = "",
        visual: Optional[Dict[str, float]] = None,
        audio: Optional[Dict[str, float]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> ConceptVector:
        """多模态输入 → 统一概念向量。

        Args:
            text: 文本输入
            visual: 视觉特征 {red, green, blue, round, square, ...}
            audio: 音频特征 {loudness, pitch, rhythm, ...}
            payload: 原始信号 payload（含结构化字段）

        Returns:
            ConceptVector（统一概念表征）
        """
        self._stats["encode_calls"] += 1
        payload = payload or {}

        # ── 1. 各模态独立编码 ──
        modal_concepts: Dict[str, Dict[str, float]] = {}

        # 文本模态（Phase 2：SNN 编码，三模态对称）
        text_src = text or str(payload.get("question", "")) or str(payload.get("description", ""))
        if text_src:
            # 规则式概念提取（含动态概念）
            rule_concepts = self._text_to_concepts_registry(text_src)
            if self.use_snn_encoding:
                # SNN 编码：低层语义特征 → 概念
                text_feats = _text_to_features(text_src)
                if text_feats:
                    snn_concepts = self.text_snn.encode(text_feats)
                    # 融合：同概念取高（SNN 学习 + 规则式先验）
                    merged = dict(rule_concepts)
                    for c, v in snn_concepts.items():
                        merged[c] = max(merged.get(c, 0.0), v)
                    modal_concepts["text"] = merged
                else:
                    modal_concepts["text"] = rule_concepts
            else:
                modal_concepts["text"] = rule_concepts

        # 视觉模态（Phase 2：SNN 编码）
        if visual:
            if self.use_snn_encoding:
                modal_concepts["visual"] = self.visual_snn.encode(visual)
            else:
                modal_concepts["visual"] = _visual_to_concepts(visual)

        # 音频模态（Phase 2：SNN 编码）
        if audio:
            if self.use_snn_encoding:
                modal_concepts["audio"] = self.audio_snn.encode(audio)
            else:
                modal_concepts["audio"] = _audio_to_concepts(audio)

        # 结构化字段 → 概念（金额/风险注入）
        struct_concepts = self._payload_to_concepts(payload)
        if struct_concepts:
            modal_concepts["structured"] = struct_concepts

        # ── 2. 对齐层融合（协同推理：多模态交叉验证） ──
        unified: Dict[str, float] = {}
        sources: Dict[str, List[str]] = {}
        for modality, concepts in modal_concepts.items():
            w = self.modality_weights.get(modality, 1.0)
            for concept, strength in concepts.items():
                contrib = strength * w
                if concept not in unified:
                    sources[concept] = []
                    unified[concept] = contrib
                elif contrib > unified[concept]:
                    unified[concept] = contrib
                sources[concept].append(modality)

        # ── 3. 协同推理：多模态交叉验证 ──
        # 同概念多模态激活 → 共识提升置信（2 模态 +10%，3 模态 +20%）
        # 冲突（不同模态强度差异大）保持取高，不刻意压制（保留多模态信息）
        for concept in unified:
            n = len(sources.get(concept, []))
            if n > 1:
                unified[concept] = min(1.0, unified[concept] * (1 + 0.1 * (n - 1)))

        # ── 4. 归一化 ──
        for concept in unified:
            unified[concept] = min(1.0, unified[concept])

        # 对齐强度：多模态同概念激活越多，对齐越强
        multi_modal = sum(1 for s in sources.values() if len(s) > 1)
        self._stats["alignment_strength"] = multi_modal / max(1, len(unified))

        from datetime import datetime, timezone
        return ConceptVector(
            concepts=unified,
            modality_sources=sources,
            aligned_at=datetime.now(timezone.utc).isoformat(),
        )

    def distill(self, samples: List[Dict[str, Any]], eta: float = 0.05) -> Dict[str, int]:
        """蒸馏训练：用规则式编码作为教师，训练模态 SNN。

        Args:
            samples: 训练样本列表，每个含 visual/audio 特征
            eta: 学习率

        Returns:
            {visual_distill: n, audio_distill: n, text_distill: n}
        """
        stats = {"visual_distill": 0, "audio_distill": 0, "text_distill": 0}
        for sample in samples:
            visual = sample.get("visual")
            if visual:
                teacher = _visual_to_concepts(visual)
                self.visual_snn.distill_step(visual, teacher, eta)
                stats["visual_distill"] += 1
            audio = sample.get("audio")
            if audio:
                teacher = _audio_to_concepts(audio)
                self.audio_snn.distill_step(audio, teacher, eta)
                stats["audio_distill"] += 1
            text = sample.get("text")
            if text:
                text_feats = _text_to_features(text)
                if text_feats:
                    teacher = _text_to_concepts(text)
                    self.text_snn.distill_step(text_feats, teacher, eta)
                    stats["text_distill"] += 1
        self._stats["distill_calls"] += len(samples)
        return stats

    def train_supervised(self, samples: List[Dict[str, Any]], eta: float = 0.05) -> Dict[str, int]:
        """有监督训练：用真实标注（concepts 标签）训练模态 SNN。

        区别于 distill（规则式教师），train_supervised 用**真实标注**
        作为教师——接收人工标注或外部知识库的概念标签，直接驱动
        模态 SNN 学习（真实数据训练）。

        Args:
            samples: 训练样本列表，每个含 visual/audio + concepts 标签
                {"visual": {...}, "concepts": {"apple": 0.9, ...}}
            eta: 学习率

        Returns:
            {visual: n, audio: n} 训练步数
        """
        stats = {"visual": 0, "audio": 0, "text": 0}
        for sample in samples:
            concepts = sample.get("concepts")
            if not isinstance(concepts, dict) or not concepts:
                continue
            visual = sample.get("visual")
            if visual:
                # 真实标注 concepts 作为教师
                self.visual_snn.distill_step(visual, concepts, eta)
                stats["visual"] += 1
            audio = sample.get("audio")
            if audio:
                self.audio_snn.distill_step(audio, concepts, eta)
                stats["audio"] += 1
            text = sample.get("text")
            if text:
                text_feats = _text_to_features(text)
                if text_feats:
                    self.text_snn.distill_step(text_feats, concepts, eta)
                    stats["text"] += 1
        self._stats["supervised_calls"] = self._stats.get("supervised_calls", 0) + len(samples)
        return stats

    def contrastive_align(self, samples: List[Dict[str, Any]], eta: float = 0.05) -> Dict[str, int]:
        """对比学习对齐：跨模态互信息对齐（InfoNCE 风格）。

        不是机械模仿规则式教师，而是让模态 SNN 通过**跨模态一致性**
        学习对齐——同一概念在不同模态下应激活同一维度。

        对每个多模态样本：
        1. 各模态独立编码出概念激活
        2. 正对：跨模态同概念 → 加强双方该概念路径（拉近）
        3. 负对：跨模态不同概念 → 削弱误激活路径（推远）

        用其他模态作为"软教师"：当其他模态对某概念激活强而本模态弱时，
        加强本模态该概念路径（跨模态拉近），实现真实的对齐学习。

        Args:
            samples: 多模态样本列表，每个含 visual/audio/text 特征
            eta: 学习率

        Returns:
            {visual: n, audio: n, text: n} 对齐步数
        """
        stats = {"visual": 0, "audio": 0, "text": 0}

        for sample in samples:
            # 各模态独立编码
            modal_acts: Dict[str, Dict[str, float]] = {}
            if sample.get("visual"):
                modal_acts["visual"] = self.visual_snn.encode(sample["visual"])
            if sample.get("audio"):
                modal_acts["audio"] = self.audio_snn.encode(sample["audio"])
            if sample.get("text"):
                modal_acts["text"] = _text_to_concepts(sample["text"])

            # 逐模态对比学习：用其他模态作为软教师
            modals = list(modal_acts.keys())
            for m in modals:
                # 其他模态对本概念的最大激活（软教师）
                teacher: Dict[str, float] = {}
                for other in modals:
                    if other == m:
                        continue
                    for concept, strength in modal_acts[other].items():
                        teacher[concept] = max(teacher.get(concept, 0), strength)

                # 无其他模态 → 无法对比，跳过
                if not teacher:
                    continue

                # 用软教师更新本模态 SNN
                if m == "visual":
                    self.visual_snn.distill_step(sample["visual"], teacher, eta)
                    stats["visual"] += 1
                elif m == "audio":
                    self.audio_snn.distill_step(sample["audio"], teacher, eta)
                    stats["audio"] += 1

        self._stats["contrastive_calls"] = self._stats.get("contrastive_calls", 0) + len(samples)
        return stats


    def _text_to_concepts_registry(self, text: str) -> Dict[str, float]:
        """文本 → 概念（含动态注册概念检测）。

        先跑模块级关键词规则（固定概念），再检测 registry 中
        动态注册的概念名是否出现在文本（开放集）。
        """
        concepts = _text_to_concepts(text)
        t = text.lower()
        # 动态注册概念：概念名/别名出现在文本 → 激活
        for name in self.registry.all():
            if name in concepts:
                continue
            if name in t:
                concepts[name] = 0.9
                continue
            # 别名匹配（中文等）
            for alias, canonical in self.registry.aliases.items():
                if canonical == name and alias in text:
                    concepts[name] = 0.9
        return concepts

    def _payload_to_concepts(self, payload: Dict[str, Any]) -> Dict[str, float]:
        """结构化 payload 字段 → 概念。

        金额/风险/紧急度等结构化字段映射到概念空间。
        """
        concepts: Dict[str, float] = {}

        amount = payload.get("amount")
        if amount is None:
            amount = payload.get("price") or payload.get("value") or payload.get("total")
        if isinstance(amount, (int, float)) and amount > 0:
            if amount >= 50000:
                concepts["escalation"] = min(1.0, concepts.get("escalation", 0) + 0.7)
                concepts["danger"] = min(1.0, concepts.get("danger", 0) + 0.4)

        risk = str(payload.get("risk_level", "") or payload.get("risk", "")).lower()
        if risk and any(k in risk for k in ("critical", "high", "严重", "高风险", "紧急")):
            concepts["danger"] = 0.9
            concepts["urgency"] = 0.9

        deadline = str(payload.get("deadline", "")).lower()
        if deadline and any(k in deadline for k in ("today", "今天", "immediate", "立即", "now")):
            concepts["urgency"] = 0.9

        return concepts

    def learn_from_feedback(self, visual: Optional[Dict[str, float]] = None,
                            audio: Optional[Dict[str, float]] = None,
                            correct_decision: str = "",
                            eta: float = 0.05) -> Dict[str, int]:
        """概念层持续学习：根据决策反馈更新模态 SNN。

        反馈的正确决策 → 概念教师（approve→approval, reject→rejection,
        escalate→escalation），用蒸馏更新视觉/音频 SNN 的概念路径。

        这样当系统学到"视觉红+亮应升级"时，视觉 SNN 的 escalation
        概念路径被加强（跨模态对齐的持续学习）。

        Args:
            visual: 视觉特征（如 {red:0.9, round:0.9}）
            audio: 音频特征
            correct_decision: 正确决策（approve/reject/escalate/flag/no_action）
            eta: 学习率

        Returns:
            {visual: n, audio: n} 更新步数
        """
        # 决策 → 概念教师映射
        decision_concept = {
            "auto_approve": "approval",
            "approve": "approval",
            "reject": "rejection",
            "escalate": "escalation",
            "flag": "escalation",
            "no_action": "novelty",
            "chat": "chitchat",
        }.get(correct_decision, "")

        stats = {"visual": 0, "audio": 0}
        if not decision_concept:
            return stats

        teacher: Dict[str, float] = {decision_concept: 0.9}

        if visual:
            self.visual_snn.distill_step(visual, teacher, eta)
            stats["visual"] += 1
        if audio:
            self.audio_snn.distill_step(audio, teacher, eta)
            stats["audio"] += 1

        # 真实标注数据积累：feedback 的正确决策作为教师，
        # 积累样本供批量有监督训练（方向3：真实标注数据积累）
        self._accumulate_feedback_sample(visual, audio, decision_concept)

        self._stats["learn_feedback_calls"] = self._stats.get("learn_feedback_calls", 0) + 1
        return stats

    def _accumulate_feedback_sample(self, visual: Optional[Dict[str, float]] = None,
                                    audio: Optional[Dict[str, float]] = None,
                                    decision_concept: str = "",
                                    text: Optional[str] = None) -> Dict[str, int]:
        """积累真实标注训练样本（反馈驱动）。

        把 learn 反馈的正确决策作为真实标签，积累样本。
        达到批量阈值后自动调用 train_supervised（有监督训练）。

        Args:
            visual: 视觉特征
            audio: 音频特征
            decision_concept: 正确决策对应概念
            text: 文本（可选）

        Returns:
            {accumulated: n, trained: n}
        """
        if not decision_concept:
            return {"accumulated": len(self._pending_training_samples), "trained": 0}
        sample: Dict[str, Any] = {"concepts": {decision_concept: 0.9}}
        if visual:
            sample["visual"] = visual
        if audio:
            sample["audio"] = audio
        if text:
            sample["text"] = text
        self._pending_training_samples.append(sample)
        result = {"accumulated": len(self._pending_training_samples), "trained": 0}
        # 批量阈值：达到后自动训练
        if len(self._pending_training_samples) >= self._training_batch_size:
            stats = self.train_supervised(self._pending_training_samples, eta=self._training_eta)
            result["trained"] = stats.get("visual", 0) + stats.get("audio", 0) + stats.get("text", 0)
            self._pending_training_samples.clear()
        return result

    def to_sentience_input(self, concept_vector: ConceptVector) -> Dict[str, float]:
        """概念向量 → 感受层输入映射。

        统一概念 → 感受维度的桥接。不同模态对同一概念激活，
        感受层对概念响应（如 apple 概念 → familiarity）。
        """
        c = concept_vector.concepts
        sentience_input: Dict[str, float] = {}
        sentience_input["familiarity"] = min(1.0, c.get("familiarity", 0) + c.get("apple", 0) * 0.5)
        sentience_input["threat"] = c.get("danger", 0.0)
        sentience_input["urgency"] = c.get("urgency", 0.0)
        sentience_input["confusion"] = c.get("query", 0.0) * 0.6
        sentience_input["safety"] = c.get("chitchat", 0.0) * 0.7
        sentience_input["interest"] = min(1.0, c.get("novelty", 0) + c.get("query", 0) * 0.3)
        return sentience_input


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
