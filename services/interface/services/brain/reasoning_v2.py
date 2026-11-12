"""services/brain/reasoning_v2.py — Layer 3: 认知层（感知+感受前置）

格物致知路线：感知→感受→认知→决策。

与 reasoning.py (v1) 的区别：
- v1: 信号 → 意图分类 → 预算分配 → 并行脑区 → 融合决策
- v2: 信号 → 感知特征 → 感受状态 → 感受驱动预算 → 并行脑区 → 融合决策 → 诚意检查

v2 是增量演进，保留 v1 的 coordinator/compute_budget/脑区注册，
只在前端加感知层和感受层，在融合后加诚意检查。

兼容策略：
- v1 (ReasoningEngine) 保持默认
- v2 (ReasoningEngineV2) 通过 engine=v2 参数启用
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from models.brain import CognitionResult, NeuralSignal
from services.brain.perception import Perception, PerceptionResult
from services.brain.sentience import SentienceNet, SentimentState, SentienceDrivenBudget
from services.brain.cognitive_coder import CognitiveCoder, ConceptVector
from services.brain.reasoning import ReasoningEngine

logger = logging.getLogger("brain.reasoning_v2")


class ReasoningEngineV2:
    """认知主流程：感知 → 感受 → 认知 → 决策。

    复用 v1 的 coordinator/脑区，前端加感知+感受。
    """

    def __init__(self, base: ReasoningEngine):
        self.base = base  # v1 引擎（含 coordinator/regions/budget）
        self.perception = Perception()
        self.sentience = SentienceNet()
        self.cognitive_coder = CognitiveCoder()  # 多模态认知编码器
        self.sentience_budget = SentienceDrivenBudget(base.compute_budget)
        self._stats = {
            "v2_calls": 0,
            "consistency_flags": 0,
            "concept_calls": 0,
        }

    async def reason(
        self,
        signal: NeuralSignal,
        working_memory: List[dict],
        db,
        memory_context: Optional[Dict[str, Any]] = None,
    ) -> CognitionResult:
        """主入口：感知→感受→认知→决策。

        Args:
            signal: 输入信号
            working_memory: 工作记忆
            db: 数据库连接
            memory_context: 记忆上下文

        Returns:
            CognitionResult（含感知/感受信息在 memory_updates）
        """
        self._stats["v2_calls"] += 1
        memory_context = memory_context or {}

        # ── 1. 感知 ──
        payload = signal.payload or {}
        perception = self.perception.perceive(payload)

        # ── 2. 多模态认知编码（认知对齐） ──
        # 感知特征 → 统一概念向量。不同模态（视觉/语言/音频）对同一
        # 概念（如苹果/危险/紧急）激活收敛到统一概念空间，实现跨模态认知。
        raw_text = perception.raw_text
        # 从 payload 提取视觉/音频字段（多模态输入经 signal.payload 传入）
        visual_feat = payload.get("visual")
        if not isinstance(visual_feat, dict):
            visual_feat = None
        audio_feat = payload.get("audio")
        if not isinstance(audio_feat, dict):
            audio_feat = None
        concept_vector = self.cognitive_coder.encode(
            text=raw_text,
            visual=visual_feat,
            audio=audio_feat,
            payload=payload,
        )
        self._stats["concept_calls"] += 1
        concept_input = self.cognitive_coder.to_sentience_input(concept_vector)

        # ── 3. 感受 ──
        # 感受层接收：感知向量 + 认知编码注入的概念感受
        sentiment_state = self.sentience.sense(perception)
        sentiments = sentiment_state.sentiments
        # 概念感受叠加（认知对齐：概念激活增强对应感受）
        for dim, val in concept_input.items():
            if val > 0.05:
                sentiments[dim] = max(sentiments.get(dim, 0.0), val)

        # ── 4. 感受注入上下文（供 coordinator 使用） ──
        # 把感受状态放入 context，脑区可读取（如 LLM prompt 增强）
        # 同时把感受强度用于意图分类的增强
        enhanced_context = dict(memory_context)
        enhanced_context["perception"] = perception.to_dict()
        enhanced_context["sentiments"] = sentiment_state.to_dict()
        enhanced_context["sentience"] = sentiments
        enhanced_context["concepts"] = concept_vector.to_dict()
        enhanced_context["concept_vector"] = concept_vector.to_vector()

        # ── 5. 感受驱动预算（若感受显著则用 v2 预算，否则回退 v1 意图预算） ──
        plan = None
        if self._has_significant_sentiment(sentiments):
            try:
                # 用感受驱动预算（基于 v1 的 compute_budget）
                plan = self.sentience_budget.allocate(sentiments)
            except Exception as e:
                logger.warning("v2: sentiment budget failed, fallback v1: %s", str(e))
                plan = None

        # ── 6. 调用 v1 引擎的协调器（带 v2 context） ──
        # v1.reason() 内部会重新分配意图预算，这里直接调 coordinator
        if plan is not None:
            result = await self.base.coordinator.run(
                signal, enhanced_context, plan=plan
            )
        else:
            # 回退：v1 完整流程
            result = await self.base.reason(
                signal, working_memory, db, memory_context=enhanced_context
            )

        # ── 7. 诚意检查（决策-感受一致性） ──
        result = self._validate_consistency(result, sentiments, signal)

        # 附加感知/感受/概念信息
        result.memory_updates["perception"] = perception.to_dict()
        result.memory_updates["sentience"] = sentiment_state.to_dict()
        result.memory_updates["concepts"] = concept_vector.to_dict()
        result.memory_updates["_v2"] = {
            "perception_dim": perception.neuron_count(),
            "sentiment_dims": list(sentiments.keys()),
            "concept_dims": len(concept_vector.to_vector()),
            "dominant_concepts": concept_vector.dominant(top=3),
            "consistency_flags": self._stats["consistency_flags"],
        }

        return result

    # ── 辅助 ──
    def _has_significant_sentiment(self, sentiments: Dict[str, float]) -> bool:
        """感受是否显著（有维度超过阈值）。"""
        return any(v > 0.3 for v in sentiments.values())

    def _validate_consistency(
        self,
        result: CognitionResult,
        sentiments: Dict[str, float],
        signal: NeuralSignal,
    ) -> CognitionResult:
        """诚意检查：决策是否与感受一致。

        不一致时标记（不直接改决策，只降级置信度并记录）。

        规则：
        - threat 高但 decision=auto_approve → 不一致（风险信号被批准）
        - confusion 高但 decision=escalate → 不一致（没理解就升级）
        - safety 高但 decision=escalate → 轻微不一致（安全信号被过度处理）
        """
        threat = sentiments.get("threat", 0.0)
        confusion = sentiments.get("confusion", 0.0)
        safety = sentiments.get("safety", 0.0)
        urgency = sentiments.get("urgency", 0.0)

        flags: List[str] = []

        if threat > 0.7 and result.decision in ("auto_approve", "approve"):
            flags.append("threat_but_approved")
            result.confidence *= 0.7
        if confusion > 0.6 and result.decision == "escalate":
            flags.append("confused_but_escalated")
            result.confidence *= 0.8
        if safety > 0.8 and result.decision == "escalate":
            flags.append("safe_but_escalated")
            result.confidence *= 0.9
        if urgency > 0.8 and result.decision == "no_action":
            flags.append("urgent_but_noaction")
            result.confidence *= 0.7

        if flags:
            self._stats["consistency_flags"] += 1
            result.memory_updates["consistency"] = {
                "flags": flags,
                "sentiments": {k: round(v, 3) for k, v in sentiments.items()},
            }

        return result
