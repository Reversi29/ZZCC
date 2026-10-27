"""services/brain/perception.py — Layer 1: 感知层

从原始输入提取特征向量，不预设语义标签。

核心原则：
- 感知层只提取特征，不判断语义（不做 type/urgency/amount 的人工编码）
- 输出 PerceptionResult（多通道特征向量），供感受层使用
- 当前用规则提取（Phase 1），后续可替换为 embedding

通道定义：
- lexical: 词汇通道（token 频次/稀有度）
- sentiment: 情感通道（极性/唤醒度）
- formality: 正式度通道（语言风格/紧急标记）
- numeric: 数值通道（数字/货币特征）
- structure: 结构通道（句长/疑问/组织）
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ── 通道定义 ──
@dataclass(frozen=True)
class ChannelDef:
    """感知通道定义。"""
    name: str
    dim: int
    desc: str = ""


# 通道配置（每个通道的维度数决定输入神经元数量）
CHANNELS: Dict[str, ChannelDef] = {
    "lexical": ChannelDef("lexical", 8, "token_freq_buckets, rare_word_ratio, avg_word_len, unique_ratio"),
    "sentiment": ChannelDef("sentiment", 6, "pos_polarity, neg_polarity, arousal, dominance, uncertainty"),
    "formality": ChannelDef("formality", 4, "formality_score, politeness, urgency_markers, imperative"),
    "numeric": ChannelDef("numeric", 6, "has_number, number_magnitude, currency_present, count_numbers"),
    "structure": ChannelDef("structure", 4, "sentence_count, avg_sentence_len, has_question, has_exclamation"),
}


# 情感词典（Phase 1 用规则，后续可替换为 embedding）
POSITIVE_WORDS = {
    "通过", "批准", "同意", "确认", "完成", "成功", "顺利", "正常", "好", "可", "ok", "approved",
    "支持", "欢迎", "感谢", "感谢", "nice", "good", "great", "fine", "yes",
}
NEGATIVE_WORDS = {
    "拒绝", "驳回", "失败", "错误", "异常", "风险", "高", "违规", "超过", "超标", "严重",
    "危险", "紧急", "urgent", "risk", "error", "failed", "violation", "breach",
    "reject", "deny", "alert", "危险", "问题", "缺失", "缺少", "不", "无",
}
UNCERTAIN_WORDS = {
    "可能", "或许", "大概", "估计", "不确定", "待定", "需要", "可能", "unknown", "maybe",
    "不确定", "pending", "likely", "consider", "建议",
}
URGENCY_MARKERS = {
    "紧急", "马上", "立即", "立刻", "尽快", "加急", "urgent", "asap", "now", "immediately",
    "高", "风险", "违规", "紧急", "马上", "立刻", "尽快", "加急", "urgent", "asap",
}
FORMAL_WORDS = {
    "审批", "申请", "采购", "报销", "合同", "部门", "预算", "费用", "金额", "供应商",
    "approval", "purchase", "expense", "contract", "budget", "request",
}
IMPERATIVE_PATTERNS = [
    r"^(请|帮我|麻烦|请帮我|请协助|需要|我要)",
    r"^(approve|reject|escalate|please|help|need|i want)",
]


# ── 感知结果 ──
@dataclass
class PerceptionResult:
    """感知层的输出：多通道特征向量。

    不预设语义标签，只包含从原始输入提取的统计特征。
    """
    features: Dict[str, List[float]] = field(default_factory=dict)
    channels: List[str] = field(default_factory=list)
    raw_text: str = ""
    text_length: int = 0
    token_count: int = 0
    perceived_at: str = field(default_factory=_now_iso)

    def to_flat_vector(self) -> List[float]:
        """展平为向量，供 SNN 输入。"""
        flat: List[float] = []
        for ch_name, ch_def in CHANNELS.items():
            flat.extend(self.features.get(ch_name, [0.0] * ch_def.dim))
        return flat

    def neuron_count(self) -> int:
        """感知输入神经元总数。"""
        return sum(ch.dim for ch in CHANNELS.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "features": self.features,
            "channels": self.channels,
            "raw_text": self.raw_text[:200],
            "text_length": self.text_length,
            "token_count": self.token_count,
            "perceived_at": self.perceived_at,
        }


# ── 工具函数 ──
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _bucket(value: float, buckets: int = 8, lo: float = 0.0, hi: float = 1.0) -> List[float]:
    """将连续值分桶为 one-hot 向量。"""
    out = [0.0] * buckets
    if hi <= lo:
        return out
    idx = int((_clip01((value - lo) / (hi - lo))) * (buckets - 1))
    out[idx] = 1.0
    return out


# ── 感知通道 ──
class TextPerceptionChannel:
    """文本感知：从原始文本提取多通道特征向量。

    不做人工编码（不判断 type/urgency/amount），
    只提取统计和结构特征，让下游学习如何解释。
    """

    def perceive(self, raw_text: str) -> PerceptionResult:
        """从原始文本提取特征向量。"""
        text = (raw_text or "").strip()
        if not text:
            return PerceptionResult(
                features={ch.name: [0.0] * ch.dim for ch in CHANNELS.values()},
                channels=list(CHANNELS.keys()),
                raw_text="",
                text_length=0,
                token_count=0,
            )

        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        # 中文分词：含中文的 token 拆为字符级（避免长串淹没关键词）
        # 同时生成 bigram（双字组合）用于双字词匹配
        char_tokens: List[str] = []
        bigram_tokens: List[str] = []
        for t in tokens:
            if re.search(r"[\u4e00-\u9fff]", t):
                segs = re.findall(r"[\u4e00-\u9fff]+|[0-9]+", t)
                for seg in segs:
                    if re.match(r"^[\u4e00-\u9fff]+$", seg):
                        chars = list(seg)
                        char_tokens.extend(chars)
                        # bigram：相邻两字组合
                        for i in range(len(chars) - 1):
                            bigram_tokens.append(chars[i] + chars[i + 1])
                    else:
                        char_tokens.append(seg)
            else:
                char_tokens.append(t)
        # 关键词匹配用：字符 + bigram 联合（提高双字词召回）
        match_tokens = char_tokens + bigram_tokens
        token_count = len(char_tokens) if char_tokens else 0
        text_length = len(text)

        features: Dict[str, List[float]] = {}

        # ── lexical 通道（8 维） ──
        unique_ratio = len(set(tokens)) / token_count if token_count else 0.0
        avg_word_len = sum(len(t) for t in tokens) / token_count if token_count else 0.0
        features["lexical"] = [
            *([0.0] * 8),
        ]
        # token 频次分桶（按出现频率）
        freq_counts = [0.0] * 8
        if tokens:
            from collections import Counter
            freq = Counter(tokens)
            total = token_count
            # 按频次从低到高排序，分 8 桶
            sorted_tokens = sorted(freq.items(), key=lambda x: x[1])
            for i, (_, cnt) in enumerate(sorted_tokens):
                bucket = int(i * 8 / len(sorted_tokens)) if sorted_tokens else 0
                freq_counts[min(bucket, 7)] = _clip01(cnt / total)
        features["lexical"] = freq_counts

        # ── sentiment 通道（6 维） ──
        # 用 match_tokens（字符+bigram）提高双字词召回
        pos_hits = sum(1 for t in match_tokens if t in POSITIVE_WORDS)
        neg_hits = sum(1 for t in match_tokens if t in NEGATIVE_WORDS)
        unc_hits = sum(1 for t in match_tokens if t in UNCERTAIN_WORDS)
        match_count = max(1, len(match_tokens))
        features["sentiment"] = [
            _clip01(pos_hits / match_count),
            _clip01(neg_hits / match_count),
            _clip01((pos_hits + neg_hits) / match_count),  # arousal
            _clip01((pos_hits - neg_hits) / match_count),   # dominance
            _clip01(unc_hits / match_count),
            _clip01(0.0),
        ]

        # ── formality 通道（4 维） ──
        formal_hits = sum(1 for t in match_tokens if t in FORMAL_WORDS)
        urgency_hits = sum(1 for t in match_tokens if t in URGENCY_MARKERS)
        is_imperative = any(re.match(p, text.lower()) for p in IMPERATIVE_PATTERNS)
        features["formality"] = [
            _clip01(formal_hits / match_count),
            _clip01(0.0),  # politeness（Phase 1 简化）
            _clip01(urgency_hits / match_count),
            _clip01(1.0 if is_imperative else 0.0),
        ]

        # ── numeric 通道（6 维） ──
        numbers = re.findall(r"\d+", text)
        number_values = [float(n) for n in numbers] if numbers else []
        has_number = _clip01(1.0 if number_values else 0.0)
        max_magnitude = max(number_values) if number_values else 0.0
        magnitude = _clip01(math.log10(max_magnitude + 1) / 6.0) if number_values else 0.0
        has_currency = _clip01(1.0 if re.search(r"[¥￥$€£元]", text) else 0.0)
        features["numeric"] = [
            has_number,
            magnitude,
            has_currency,
            _clip01(len(number_values) / 5.0),
            _clip01(0.0),
            _clip01(0.0),
        ]

        # ── structure 通道（4 维） ──
        sentences = re.split(r"[。！？.!?；;]", text)
        sentences = [s for s in sentences if s.strip()]
        avg_sentence_len = sum(len(s) for s in sentences) / len(sentences) if sentences else 0.0
        features["structure"] = [
            _clip01(len(sentences) / 5.0),
            _clip01(avg_sentence_len / 50.0),
            _clip01(1.0 if "?" in text or "？" in text else 0.0),
            _clip01(1.0 if "!" in text or "！" in text else 0.0),
        ]

        return PerceptionResult(
            features=features,
            channels=list(CHANNELS.keys()),
            raw_text=text,
            text_length=text_length,
            token_count=token_count,
        )


# ── 时序感知通道 ──
class TemporalPerceptionChannel:
    """时序感知：从事件流中提取时间特征。

    不是预设 urgency，而是让系统观察事件到达的节奏。
    """

    def perceive(self, signal_history: List[Dict]) -> PerceptionResult:
        """从信号历史中提取时序特征。"""
        features: Dict[str, List[float]] = {}
        n = len(signal_history)

        # cadence 通道（4 维）
        if n < 2:
            features["cadence"] = [0.0, 0.0, 0.0, 0.0]
        else:
            # 事件到达率
            times = []
            for s in signal_history:
                ts = s.get("created_at", "")
                try:
                    times.append(datetime.fromisoformat(ts).timestamp())
                except (ValueError, TypeError):
                    times.append(0.0)
            times = [t for t in times if t > 0]
            if len(times) >= 2:
                intervals = [times[i + 1] - times[i] for i in range(len(times) - 1)]
                avg_interval = sum(intervals) / len(intervals) if intervals else 0.0
                var_interval = (
                    sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)
                    if intervals else 0.0
                )
                features["cadence"] = [
                    _clip01(1.0 / (avg_interval + 1.0)),
                    _clip01(var_interval / (avg_interval ** 2 + 1.0)),
                    _clip01(0.0),  # burstiness（简化）
                    _clip01(0.0),
                ]
            else:
                features["cadence"] = [0.0, 0.0, 0.0, 0.0]

        # novelty 通道（3 维）
        features["novelty"] = [0.0, 0.0, 0.0]

        return PerceptionResult(
            features=features,
            channels=list(features.keys()),
            raw_text="",
            text_length=n,
            token_count=n,
        )


# 需要 math（顶部 import 后补充）
import math  # noqa: E402


# ── 统一感知入口 ──
class Perception:
    """感知层主入口：组合文本 + 时序通道。"""

    def __init__(self):
        self.text_channel = TextPerceptionChannel()
        self.temporal_channel = TemporalPerceptionChannel()

    def perceive(self, payload: Dict[str, Any], signal_history: Optional[List[Dict]] = None) -> PerceptionResult:
        """从 payload 感知。

        Args:
            payload: 信号 payload（含 question/text/message/description 等）
            signal_history: 信号历史（用于时序感知）

        Returns:
            PerceptionResult
        """
        # 提取原始文本
        raw_text = " ".join([
            str(payload.get("question", "")),
            str(payload.get("text", "")),
            str(payload.get("message", "")),
            str(payload.get("description", "")),
            str(payload.get("title", "")),
        ]).strip()

        # 文本感知
        text_result = self.text_channel.perceive(raw_text)

        # 时序感知（有历史时）
        if signal_history:
            temporal_result = self.temporal_channel.perceive(signal_history)
            # 合并特征
            text_result.features.update(temporal_result.features)
            text_result.channels.extend(temporal_result.channels)

        return text_result
