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

    编码方式：每个模态有一个独立 SNN（模态专用网络），把该模态的
    原始特征编码为"模态概念激活"。所有模态概念激活通过对齐层融合
    到统一概念空间。

    对齐层是学习的主战场：不同模态对同一概念的激活通过对比学习
    （模态间互信息最大化）收敛到同一概念维度。

    这样：
    - 视觉"苹果图片" → 概念向量 [apple=0.9, ...]
    - 文字"苹果" → 概念向量 [apple=0.85, ...]
    - 两个概念向量接近 → 系统知道是同一个"苹果"

    输出对齐后的概念向量直接喂给感受层（sentience），感受层对概念
    响应（如 apple 概念 → familiarity 升高），实现跨模态统一感受。

    CognitiveCoder 不替代 perception/sentience，而是**桥接**它们：
    perception 提取模态原始特征 → CognitiveCoder 对齐到统一概念 →
    sentience 产生感受。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("brain.cognitive_coder")

# ── 概念维度配置 ──
# 每个维度是一个抽象概念。概念空间是开放集，可动态扩展。
# 固定概念（Phase 1）：常见认知原型，后续可学习扩展
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


# ── 模态特征提取（Phase 1：规则式，后续替换为模态专用 SNN） ──

# 视觉模态：颜色/形状/纹理特征 → 概念假设
# 视觉特征维度：红/绿/蓝/圆/方/大/小/亮/暗
_VISUAL_FEATURES = ["red", "green", "blue", "round", "square", "large", "small", "bright", "dark"]


def _visual_to_concepts(visual_features: Dict[str, float]) -> Dict[str, float]:
    """视觉特征 → 概念假设（规则式，Phase 1）。

    红色圆形 → 苹果假设；红/暗 → 危险假设。
    真实系统应训练视觉 SNN 学习这些映射。
    """
    concepts: Dict[str, float] = {}
    red = visual_features.get("red", 0.0)
    green = visual_features.get("green", 0.0)
    round_s = visual_features.get("round", 0.0)
    bright = visual_features.get("bright", 0.0)
    dark = visual_features.get("dark", 0.0)

    # 苹果：红/绿 + 圆形
    apple = (red + green) / 2.0 * round_s
    if apple > 0.1:
        concepts["apple"] = min(1.0, apple)
    # 危险：暗 + 红（血/警报）
    danger = (dark * 0.5 + red * 0.3)
    if danger > 0.1:
        concepts["danger"] = min(1.0, danger)

    return concepts


def _text_to_concepts(text: str) -> Dict[str, float]:
    """文本特征 → 概念假设（关键词规则，Phase 1）。

    真实系统应训练语言 SNN 学习这些映射。
    """
    concepts: Dict[str, float] = {}
    if not text:
        return concepts
    t = text.lower()

    # 苹果
    if any(k in t for k in ("苹果", "apple")):
        concepts["apple"] = 0.9
    # 危险
    if any(k in t for k in ("危险", "风险", "违规", "danger", "risk", "critical")):
        concepts["danger"] = 0.9
    # 紧急
    if any(k in t for k in ("紧急", "立即", "马上", "加急", "urgent", "asap")):
        concepts["urgency"] = 0.9
    # 审批通过
    if any(k in t for k in ("批准", "同意", "通过", "approve", "approved", "ok")):
        concepts["approval"] = 0.8
    # 拒绝
    if any(k in t for k in ("拒绝", "驳回", "reject", "deny")):
        concepts["rejection"] = 0.8
    # 升级
    if any(k in t for k in ("升级", "上报", "escalate", "escalation")):
        concepts["escalation"] = 0.8
    # 查询
    if any(k in t for k in ("?", "？", "查询", "请问", "query", "how", "where", "when")):
        concepts["query"] = 0.7
    # 闲聊
    if any(k in t for k in ("hello", "hi", "你好", "哈哈", "呵呵", "nice", "great")):
        concepts["chitchat"] = 0.7

    return concepts


def _audio_to_concepts(audio_features: Dict[str, float]) -> Dict[str, float]:
    """音频特征 → 概念假设（规则式，Phase 1）。

    音调/响度/节奏特征。高响度+高频 → 警报（危险/紧急）。
    真实系统应训练音频 SNN 学习这些映射。
    """
    concepts: Dict[str, float] = {}
    loudness = audio_features.get("loudness", 0.0)
    pitch = audio_features.get("pitch", 0.0)
    rhythm = audio_features.get("rhythm", 0.0)

    # 警报：高响度 + 高音调
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
    Phase 2：每模态专用 SNN 编码 + 对比学习对齐。
    """

    def __init__(self):
        self._stats = {
            "encode_calls": 0,
            "alignment_strength": 0.0,
        }
        # 模态权重（可学习，Phase 2 自动调整）
        self.modality_weights: Dict[str, float] = {
            "visual": 1.0,
            "text": 1.0,
            "audio": 1.0,
        }

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

        # 视觉模态
        if visual:
            modal_concepts["visual"] = _visual_to_concepts(visual)

        # 音频模态
        if audio:
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
                    # 同概念多模态 → 取最强激活（跨模态对齐：任一模态激活即概念成立）
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

    def _payload_to_concepts(self, payload: Dict[str, Any]) -> Dict[str, float]:
        """结构化 payload 字段 → 概念。

        金额/风险/紧急度等结构化字段映射到概念空间。
        """
        concepts: Dict[str, float] = {}

        amount = payload.get("amount")
        if amount is None:
            amount = payload.get("price") or payload.get("value") or payload.get("total")
        if isinstance(amount, (int, float)) and amount > 0:
            # 高金额 → 升级/危险假设
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

        Phase 1：概念→感受的规则映射（可学习）。
        """
        c = concept_vector.concepts
        sentience_input: Dict[str, float] = {}
        # apple/familiarity/novelty → 熟悉感
        sentience_input["familiarity"] = min(1.0, c.get("familiarity", 0) + c.get("apple", 0) * 0.5)
        # danger → 威胁感
        sentience_input["threat"] = c.get("danger", 0.0)
        # urgency → 紧迫感
        sentience_input["urgency"] = c.get("urgency", 0.0)
        # query → 困惑感
        sentience_input["confusion"] = c.get("query", 0.0) * 0.6
        # chitchat → 安全+兴趣
        sentience_input["safety"] = c.get("chitchat", 0.0) * 0.7
        sentience_input["interest"] = min(1.0, c.get("novelty", 0) + c.get("query", 0) * 0.3)
        return sentience_input


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
