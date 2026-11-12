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

    def __init__(self, modality: str, feature_names: List[str], concept_prior: Dict[str, List[str]]):
        self.modality = modality
        self.feature_names = feature_names
        self.concept_prior = concept_prior
        self.num_features = len(feature_names)
        # 神经元布局：0..num_features-1 输入，num_features..num_features+CONCEPT_DIMS-1 概念检测，+CONCEPT_DIMS 输出
        self._input_start = 0
        self._hidden_start = self.num_features
        self._output_start = self.num_features + CONCEPT_DIMS
        self.num_neurons = self._output_start + CONCEPT_DIMS

        # 纯 Python 脉冲网络状态（轻量，不依赖 SNN 类避免循环依赖）
        self._init_network()

    def _init_network(self):
        """初始化轻量脉冲网络。

        简化脉冲模型（Phase 2 可换用完整 SNN）：
        - 每个神经元有膜电位、阈值、不应期
        - 输入特征注入 → 概念检测神经元积分 → 超过阈值放电 → 输出激活
        """
        self.membrane = [0.0] * self.num_neurons
        self.threshold = [1.0] * self.num_neurons
        self.last_fire = [-100] * self.num_neurons
        self.refractory = 3
        self.decay = 0.85
        # 权重矩阵：source → {target: weight}
        self.weights: Dict[int, Dict[int, float]] = {}
        # 先验连接：特征 → 概念检测
        for concept, feats in self.concept_prior.items():
            cidx = CONCEPT_IDX.get(concept)
            if cidx is None:
                continue
            for feat in feats:
                if feat in self.feature_names:
                    fidx = self.feature_names.index(feat)
                    self._set_weight(fidx, self._hidden_start + cidx, 0.8)
            # 概念检测 → 概念输出（固定，检测放电即概念激活）
            self._set_weight(self._hidden_start + cidx, self._output_start + cidx, 1.0)

    def _set_weight(self, src: int, tgt: int, w: float):
        self.weights.setdefault(src, {})[tgt] = w

    def encode(self, features: Dict[str, float]) -> Dict[str, float]:
        """模态特征 → 概念激活。

        输入特征注入 → 概念检测神经元积分 → 放电 → 概念激活。
        返回 {concept: activation}。
        """
        # 重置膜电位（单次推理）
        self.membrane = [0.0] * self.num_neurons
        self.last_fire = [-100] * self.num_neurons

        # 1. 注入输入特征（强度=特征值）
        for fname, fval in features.items():
            if fname in self.feature_names:
                fidx = self.feature_names.index(fname)
                self.membrane[fidx] = max(self.membrane[fidx], fval)

        # 2. 传播 2 步（输入→概念检测→概念输出）
        activations: Dict[str, float] = {}
        for step in range(2):
            new_membrane = list(self.membrane)
            for src, targets in self.weights.items():
                if self.membrane[src] < 0.3:  # 源未激活
                    continue
                src_strength = self.membrane[src]
                for tgt, w in targets.items():
                    # 膜电位积分
                    new_membrane[tgt] += src_strength * w
            # 衰减 + 不应期
            self.membrane = [m * self.decay for m in new_membrane]
            # 概念输出检测
            for cidx in range(CONCEPT_DIMS):
                out_nid = self._output_start + cidx
                if self.membrane[out_nid] > 0.3:
                    activations[CONCEPT_NAMES[cidx]] = min(1.0, self.membrane[out_nid])

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
        for concept, t_val in teacher.items():
            cidx = CONCEPT_IDX.get(concept)
            if cidx is None:
                continue
            hid = self._hidden_start + cidx
            if t_val > 0.3:
                # 教师激活：加强该概念的先验特征连接
                feats = self.concept_prior.get(concept, [])
                for feat in feats:
                    if feat in self.feature_names:
                        fidx = self.feature_names.index(feat)
                        cur = self.weights.get(fidx, {}).get(hid, 0.0)
                        self._set_weight(fidx, hid, min(3.0, cur + eta))
            else:
                # 教师未激活：削弱该概念连接（如果过高）
                feats = self.concept_prior.get(concept, [])
                for feat in feats:
                    if feat in self.feature_names:
                        fidx = self.feature_names.index(feat)
                        cur = self.weights.get(fidx, {}).get(hid, 0.0)
                        if cur > 0.3:
                            self._set_weight(fidx, hid, max(0.1, cur - eta * 0.5))


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
    if any(k in t for k in ("批准", "同意", "通过", "approve", "approved", "ok")):
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
        # 模态权重（可学习，Phase 2 自动调整）
        self.modality_weights: Dict[str, float] = {
            "visual": 1.0,
            "text": 1.0,
            "audio": 1.0,
        }
        # 模态专用 SNN 编码器（Phase 2）
        self.visual_snn = ModalSNNEncoder("visual", VISUAL_FEATURES, _VISUAL_CONCEPT_PRIOR)
        self.audio_snn = ModalSNNEncoder("audio", AUDIO_FEATURES, _AUDIO_CONCEPT_PRIOR)
        # Phase 2 开关：默认用 SNN 编码（有先验初始化，冷启动可用）
        self.use_snn_encoding = True

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

        # 文本模态
        text_src = text or str(payload.get("question", "")) or str(payload.get("description", ""))
        if text_src:
            modal_concepts["text"] = _text_to_concepts(text_src)

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

        # ── 2. 对齐层融合（加权，同概念跨模态取高） ──
        unified: Dict[str, float] = {}
        sources: Dict[str, List[str]] = {}
        for modality, concepts in modal_concepts.items():
            w = self.modality_weights.get(modality, 1.0)
            for concept, strength in concepts.items():
                contrib = strength * w
                if concept not in unified or contrib > unified[concept]:
                    if concept not in unified:
                        sources[concept] = []
                    unified[concept] = contrib
                    sources[concept].append(modality)
                elif concept in sources:
                    sources[concept].append(modality)

        # ── 3. 归一化 ──
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
            {visual_distill: n, audio_distill: n}
        """
        stats = {"visual_distill": 0, "audio_distill": 0}
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
        self._stats["distill_calls"] += len(samples)
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
