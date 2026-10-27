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
        self.sentience_budget = SentienceDrivenBudget(base.compute_budget)
        self._stats = {
            "v2_calls": 0,
            "consistency_flags": 0,
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

        # ── 2. 感受 ──
        sentiment_state = self.sentience.sense(perception)
        sentiments = sentiment_state.sentiments

        # ── 3. 感受注入上下文（供 coordinator 使用） ──
        # 把感受状态放入 context，脑区可读取（如 LLM prompt 增强）
        # 同时把感受强度用于意图分类的增强
        enhanced_context = dict(memory_context)
        enhanced_context["perception"] = perception.to_dict()
        enhanced_context["sentiments"] = sentiment_state.to_dict()
        enhanced_context["sentience"] = sentiments

        # ── 4. 感受驱动预算（若感受显著则用 v2 预算，否则回退 v1 意图预算） ──
        plan = None
        if self._has_significant_sentiment(sentiments):
            try:
                # 用感受驱动预算（基于 v1 的 compute_budget）
                plan = self.sentience_budget.allocate(sentiments)
            except Exception as e:
                logger.warning("v2: sentiment budget failed, fallback v1: %s", str(e))
                plan = None

        # ── 5. 调用 v1 引擎的协调器（带 v2 context） ──
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

        # ── 6. 诚意检查（决策-感受一致性） ──
        result = self._validate_consistency(result, sentiments, signal)

        # 附加感知/感受信息
        result.memory_updates["perception"] = perception.to_dict()
        result.memory_updates["sentience"] = sentiment_state.to_dict()
        result.memory_updates["_v2"] = {
            "perception_dim": perception.neuron_count(),
            "sentiment_dims": list(sentiments.keys()),
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
