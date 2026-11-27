"""services/brain/multimodal_dataset.py — 多模态认知数据集（无感映射训练数据）

用户 2026-11-26 洞察：整理多模态数据集，包括"同事物的无感映射"。
即同一概念（如 苹果/危险/紧急）在不同模态（视觉/文本/音频）下的
不同表面表示，应映射到同一深层概念。

本模块提供：
1. MULTIMODAL_SAMPLES: 内建多模态样本集（同一概念的多模态表示）
2. MultimodalDataset: 数据集类（加载/保存/增强/按概念检索）
3. build_contrastive_pairs(): 构造跨模态对比学习正/负对

设计原则：
- 每样本含同一概念的多模态表示（visual/text/audio/structured）
- concepts 字段标注该样本的规范概念（无感映射目标）
- 支持动态扩充（开放集：新概念追加新样本）
- 持久化到 JSON，重启不丢失

用法（无感映射训练）：
    from services.brain.multimodal_dataset import MultimodalDataset
    ds = MultimodalDataset()
    coder.contrastive_align(ds.samples())       # 跨模态对齐
    coder.train_supervised(ds.labeled())        # 有监督（概念标注）

验证：
    cv = coder.encode(visual={"red":0.9,"round":0.9})   # 视觉苹果
    cv2 = coder.encode(text="我想吃苹果")                # 文本苹果
    # 两模态都应激活 apple 概念（无感映射）
"""
from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional


# ── 内建多模态样本：同一概念的多模态表示 ──
# 每个样本：概念 + 各模态特征（同事物无感映射的目标集）
# 概念集与 cognitive_coder.CONCEPT_NAMES 对齐（apple/danger/novelty/urgency/...）
MULTIMODAL_SAMPLES: List[Dict[str, Any]] = [
    # ── 苹果（apple）：视觉红圆 / 文本"苹果" / 语义特征 ──
    {
        "concept": "apple",
        "visual": {"red": 0.9, "green": 0.2, "round": 0.9},
        "text": "我想吃一个红苹果",
        "features": {"apple_marker": 0.9},
    },
    {
        "concept": "apple",
        "visual": {"red": 0.8, "round": 0.85},
        "text": "apple fruit",
        "features": {"apple_marker": 0.9},
    },
    {
        "concept": "apple",
        "visual": {"green": 0.7, "round": 0.8},
        "text": "青苹果",
        "features": {"apple_marker": 0.8},
    },
    # ── 危险（danger）：视觉暗红 / 文本危险标记 / 音频响亮 ──
    {
        "concept": "danger",
        "visual": {"dark": 0.9, "red": 0.8},
        "text": "检测到危险信号，需要立即处理",
        "features": {"risk_marker": 0.9, "urgent_marker": 0.7},
        "audio": {"loudness": 0.9, "pitch": 0.7},
    },
    {
        "concept": "danger",
        "visual": {"dark": 0.85, "red": 0.75},
        "text": "danger critical risk",
        "features": {"risk_marker": 0.9},
        "audio": {"loudness": 0.85},
    },
    # ── 紧急（urgency）：文本紧急 / 音频急促 ──
    {
        "concept": "urgency",
        "text": "紧急！这个审批必须马上处理",
        "features": {"urgent_marker": 0.9},
        "audio": {"loudness": 0.9, "pitch": 0.8},
    },
    {
        "concept": "urgency",
        "text": "urgent asap now",
        "features": {"urgent_marker": 0.9},
        "audio": {"pitch": 0.9, "loudness": 0.7},
    },
    # ── 新异（novelty）：视觉亮 ──
    {
        "concept": "novelty",
        "visual": {"bright": 0.9},
        "text": "发现一个全新的东西",
    },
    # ── 审批（approval）：文本批准 ──
    {
        "concept": "approval",
        "text": "同意，批准这个申请",
        "features": {"approval_marker": 0.9},
    },
    # ── 拒绝（rejection）：文本拒绝 ──
    {
        "concept": "rejection",
        "text": "驳回，不同意",
        "features": {"rejection_marker": 0.9},
    },
    # ── 查询（query）：文本疑问 ──
    {
        "concept": "query",
        "text": "请问这个怎么处理？",
        "features": {"query_marker": 0.9},
    },
    # ── 闲聊（chitchat）：文本问候 ──
    {
        "concept": "chitchat",
        "text": "hello 你好呀",
        "features": {"greeting_marker": 0.9},
    },
]


def _sample_key(s: Dict[str, Any]):
    """样本去重指纹。

    原实现仅用 (concept, visual_keys)，对无 visual 的纯文本/结构化样本
    visual_keys 恒为 ()，不同内容的样本被误判重复而丢失。
    现纳入 text/payload 内容摘要，保证同 concept 不同内容的样本不被误去重。

    `_src` 是样本来源标识：内建样本无此字段，构造样本（图标/话术/表格）有，
    避免构造样本与内建同 concept 样本合法碰撞而被误过滤。
    """
    text = str(s.get("text") or "")
    payload = s.get("payload") or {}
    pstr = "".join(f"{k}={v}" for k, v in sorted(
        (k, v) for k, v in payload.items() if k in ("fields", "rows", "columns")
    ))
    visual = tuple(sorted((s.get("visual") or {}).keys()))
    audio = tuple(sorted((s.get("audio") or {}).keys()))
    return (s.get("concept"), s.get("_src"), text, pstr, visual, audio)


class MultimodalDataset:
    """多模态数据集：同事物多模态表示，供无感映射训练。

    支持内建样本 + 动态扩充（开放集）。
    """

    def __init__(self, path: Optional[str] = None, samples: Optional[List[Dict[str, Any]]] = None):
        config_dir = os.environ.get("BRAIN_CONFIG_DIR", "/app/config_data")
        self.path = path or os.path.join(config_dir, "multimodal_dataset.json")
        self._samples: List[Dict[str, Any]] = list(samples or MULTIMODAL_SAMPLES)
        self._load()

    def _load(self):
        """从磁盘加载扩充样本（内建 + 持久化）。"""
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                extra = data.get("extra_samples", [])
                # 去重：按内容指纹（concept + 模态内容），非仅 concept+visual_keys
                existing = {_sample_key(s) for s in self._samples}
                for s in extra:
                    key = _sample_key(s)
                    if key not in existing:
                        self._samples.append(s)
                        existing.add(key)
        except Exception:
            pass

    def save(self):
        """持久化扩充样本。"""
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            builtin_keys = {_sample_key(s) for s in MULTIMODAL_SAMPLES}
            extra = [s for s in self._samples if _sample_key(s) not in builtin_keys]
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"extra_samples": extra}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def samples(self) -> List[Dict[str, Any]]:
        """全部样本（内建 + 扩充）。"""
        return list(self._samples)

    def labeled(self) -> List[Dict[str, Any]]:
        """有监督训练样本：含 concepts 标注（concept → 0.9）。"""
        out = []
        for s in self._samples:
            c = s.get("concept")
            if not c:
                continue
            labeled = dict(s)
            labeled["concepts"] = {c: 0.9}
            out.append(labeled)
        return out

    def by_concept(self, concept: str) -> List[Dict[str, Any]]:
        """按概念检索样本。"""
        return [s for s in self._samples if s.get("concept") == concept]

    def concepts(self) -> List[str]:
        """全部概念。"""
        return sorted({s.get("concept") for s in self._samples if s.get("concept")})

    def add_sample(self, sample: Dict[str, Any]):
        """动态扩充（开放集：新概念/新表示追加）。"""
        self._samples.append(sample)
        self.save()

    def stats(self) -> Dict[str, Any]:
        """数据集统计。"""
        concepts = self.concepts()
        by_concept = {c: len(self.by_concept(c)) for c in concepts}
        modal_count = {
            "visual": sum(1 for s in self._samples if s.get("visual")),
            "text": sum(1 for s in self._samples if s.get("text")),
            "audio": sum(1 for s in self._samples if s.get("audio")),
            "structured": sum(1 for s in self._samples if s.get("payload")),
        }
        return {
            "total": len(self._samples),
            "concepts": concepts,
            "by_concept": by_concept,
            "modal_count": modal_count,
            "multi_modal": sum(1 for s in self._samples
                               if sum(1 for m in ("visual", "text", "audio") if s.get(m)) >= 2),
        }


def build_contrastive_pairs(
    samples: List[Dict[str, Any]],
    concept_registry: Optional[Any] = None,
    seed: int = 7,
) -> Dict[str, List[Dict[str, Any]]]:
    """构造跨模态对比学习正/负对。

    正对：同一概念的不同模态表示（拉近，无感映射目标）
    负对：不同概念的不同模态表示（推远，防混淆）

    Returns:
        {"positive": [...], "negative": [...]}
        每个对：{"anchor": {...}, "other": {...}, "concept": str}
    """
    random.seed(seed)
    positive = []
    negative = []

    # 按概念分组
    by_concept: Dict[str, List[Dict[str, Any]]] = {}
    for s in samples:
        c = s.get("concept")
        if c:
            by_concept.setdefault(c, []).append(s)

    concepts = list(by_concept.keys())

    # 正对：同概念跨模态（anchor 一种模态，other 另一模态）
    for c, group in by_concept.items():
        for i, a in enumerate(group):
            for j, b in enumerate(group):
                if i >= j:
                    continue
                # 确保跨模态（非纯同模态）
                if a.get("visual") and b.get("text") or a.get("text") and b.get("visual"):
                    positive.append({"anchor": a, "other": b, "concept": c})

    # 负对：不同概念
    for c1, group1 in by_concept.items():
        for c2 in concepts:
            if c1 >= c2:
                continue
            g2 = by_concept[c2]
            # 取前几个组合（控规模）
            for a in group1[:3]:
                for b in g2[:3]:
                    negative.append({"anchor": a, "other": b, "concept": c1})

    return {"positive": positive, "negative": negative}
