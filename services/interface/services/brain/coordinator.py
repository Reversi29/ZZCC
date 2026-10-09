"""services/brain/coordinator.py — 脑区协调器

类脑推理的核心调度层。取代旧的 L1→L2→L3 瀑布推理，改为：

1. 并行激活各脑区（asyncio.gather）
2. 收集候选结果
3. 加权融合 + 冲突解决 + 一致性增强
4. 产出最终 CognitionResult

脑区清单：
- RuleRegion        — L1 规则推理（低成本，窄范围）
- StatisticalRegion — L2 统计推理（低成本，模式匹配）
- LLMRegion         — L3 LLM 推理（高成本，宽范围）
- SemanticRegion    — 语义记忆检索（enrichment）
- EpisodicRegion    — 情景记忆检索（enrichment）

集成策略：
- 共识增强：多脑区同意 → 置信度加成
- 冲突仲裁：加权投票，权重由脑区类型决定
- 偏离检测：某脑区显著优于其他 → 信任该脑区
- 记忆增强：语义/情景记忆作为上下文注入，不直接决策
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from models.brain import Action, CognitionResult, NeuralSignal

logger = logging.getLogger("brain.coordinator")


@dataclass
class RegionResult:
    """单个脑区的推理输出。"""
    region: str                        # rule / statistical / llm / semantic / episodic
    ok: bool = True
    result: Optional[CognitionResult] = None
    context: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    tokens: int = 0
    error: str = ""
    timeout: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region": self.region,
            "ok": self.ok,
            "has_result": self.result is not None,
            "decision": self.result.decision if self.result else None,
            "confidence": self.result.confidence if self.result else 0.0,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "tokens": self.tokens,
            "timeout": self.timeout,
            "error": self.error,
        }


# 脑区权重配置（用于融合决策）
_REGION_WEIGHTS: Dict[str, float] = {
    "rule":        0.80,   # 规则引擎：高置信度但窄范围
    "statistical": 0.60,   # 统计推理：模式匹配，中等置信度
    "llm":         0.50,   # LLM：宽范围但可变置信度
    "snn":         0.55,   # SNN：脉冲神经网络，训练后精准匹配
    "semantic":    0.20,   # 语义记忆：仅做上下文增强
    "episodic":    0.20,   # 情景记忆：仅做上下文增强
}

# 冲突时，按优先级决定最终决策方向
_DECISION_PRIORITY: Dict[str, int] = {
    "reject": 5,          # 拒绝优先（安全侧）
    "escalate": 4,        # 升级人工
    "flag": 3,            # 标记待审
    "need_info": 2,       # 需要更多信息
    "auto_approve": 1,    # 自动批准（最低优先级）
    "approve": 1,
    "no_action": 0,
    "chat": 0,            # 闲聊：不参与安全侧仲裁
    "reply": 0,           # 知识回复：不参与仲裁
}


class RegionCoordinator:
    """脑区并行协调器。

    用法：
        coordinator = RegionCoordinator()
        # 注册各脑区
        coordinator.register("rule", rule_fn)
        coordinator.register("statistical", stat_fn)
        coordinator.register("llm", llm_fn)
        coordinator.register("semantic", semantic_fn)
        coordinator.register("episodic", episodic_fn)
        # 并行执行 + 融合
        result = await coordinator.run(signal, context)
    """

    def __init__(self):
        self._regions: Dict[str, Callable] = {}
        self._region_weights = dict(_REGION_WEIGHTS)

    def register(self, region: str, fn: Callable, weight: Optional[float] = None) -> None:
        """注册脑区推理函数。

        fn 签名: async (signal: NeuralSignal, context: Dict, budget: RegionBudget) -> RegionResult
        """
        self._regions[region] = fn
        if weight is not None:
            self._region_weights[region] = weight

    def set_weight(self, region: str, weight: float) -> None:
        self._region_weights[region] = weight

    async def run(
        self,
        signal: NeuralSignal,
        context: Dict[str, Any],
        plan: Optional[Dict[str, Any]] = None,  # from ComputeBudget.allocate()
        timeout_ms: float = 30000.0,
    ) -> CognitionResult:
        """并行执行所有启用的脑区，融合结果后返回。

        Args:
            signal: 输入信号
            context: 上下文字典（工作记忆、记忆上下文等）
            plan: 算力预算分配（{region: RegionBudget}），None 表示全部启用
            timeout_ms: 总超时（毫秒）

        Returns:
            CognitionResult — 融合后的最终认知结果
        """
        start = time.time()
        plan = plan or {}

        # 收集启用的脑区
        enabled_regions: List[str] = []
        skipped: Dict[str, str] = {}
        for name, fn in self._regions.items():
            budget = plan.get(name)
            if budget is not None and not getattr(budget, "allowed", True):
                skipped[name] = "intent 不激活"
            else:
                enabled_regions.append(name)

        # 并行执行 — 使用 as_completed 收集已完成结果，避免全局超时丢弃快脑区结果
        tasks_map: Dict[asyncio.Task, str] = {}
        for name in enabled_regions:
            fn = self._regions[name]
            budget = plan.get(name)
            task = asyncio.ensure_future(self._run_region(name, fn, signal, context, budget))
            tasks_map[task] = name

        processed: List[RegionResult] = []
        deadline = start + timeout_ms / 1000.0
        try:
            for coro in asyncio.as_completed(list(tasks_map.keys()), timeout=timeout_ms / 1000.0):
                try:
                    r = await coro
                    processed.append(r)
                except Exception as e:
                    # 找到对应的 region name
                    pass  # 异常已在 _run_region 中处理
        except asyncio.TimeoutError:
            # 全局超时——收集已完成的，标记未完成的
            elapsed_now = (time.time() - start) * 1000
            completed_names = {r.region for r in processed}
            for task, name in tasks_map.items():
                if name not in completed_names and not task.done():
                    task.cancel()
                    processed.append(RegionResult(
                        region=name, ok=False, error="超时",
                        elapsed_ms=elapsed_now, timeout=True,
                    ))
                elif name not in completed_names and task.done():
                    # task 完成但 as_completed 循环已退出
                    try:
                        r = task.result()
                        if isinstance(r, RegionResult):
                            processed.append(r)
                    except Exception:
                        pass
            logger.warning("coordinator: global timeout after %dms, %d/%d regions completed",
                          int((time.time() - start) * 1000), len(processed), len(enabled_regions))

        # 加上跳过的脑区
        for name, reason in skipped.items():
            processed.append(RegionResult(region=name, ok=False, error=reason,
                                          elapsed_ms=0, timeout=False))

        # 融合
        final = self._integrate(signal, processed, context)
        total_ms = (time.time() - start) * 1000

        logger.debug("coordinator: %dms, %d regions active, %d skipped, decision=%s conf=%.2f",
                      total_ms, len(enabled_regions), len(skipped), final.decision, final.confidence)

        return final

    async def _run_region(
        self,
        name: str,
        fn: Callable,
        signal: NeuralSignal,
        context: Dict[str, Any],
        budget: Any,
    ) -> RegionResult:
        """执行单个脑区，包装为 RegionResult。"""
        start = time.time()
        try:
            result = await fn(signal, context, budget)
            elapsed = (time.time() - start) * 1000
            if isinstance(result, CognitionResult):
                return RegionResult(
                    region=name, ok=True, result=result,
                    elapsed_ms=elapsed,
                    tokens=getattr(result, "memory_updates", {}).get("_tokens", 0) if hasattr(result, "memory_updates") else 0,
                )
            elif isinstance(result, RegionResult):
                result.elapsed_ms = elapsed
                return result
            elif result is None:
                return RegionResult(region=name, ok=True, result=None,
                                    elapsed_ms=elapsed)
            else:
                return RegionResult(region=name, ok=False, error=f"unexpected return type: {type(result)}",
                                    elapsed_ms=elapsed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error("region %s failed: %s", name, e)
            return RegionResult(region=name, ok=False, error=str(e),
                                elapsed_ms=elapsed)

    def _integrate(
        self,
        signal: NeuralSignal,
        results: List[RegionResult],
        context: Dict[str, Any],
    ) -> CognitionResult:
        """融合多个脑区的候选结果。

        融合策略：
        1. 收集所有有效候选（有 result 且 ok）
        2. 加权置信度排序
        3. 冲突检测：决策方向不一致时，按优先级仲裁
        4. 共识增强：多脑区同意同一决策 → 置信度加成
        5. 记忆增强：合并所有脑区的 memory_updates
        6. 行动合并：去重后合并 actions
        7. 推理链：拼接各脑区的 reasoning
        """
        # 收集有效候选
        candidates: List[tuple] = []  # (region_name, CognitionResult, weight)
        enrichment_context: Dict[str, Any] = {}

        for r in results:
            if not r.ok:
                continue
            if r.result is not None:
                weight = self._region_weights.get(r.region, 0.3)
                candidates.append((r.region, r.result, weight))
            # 收集 enrichment context（语义/情景记忆等）
            if r.context:
                enrichment_context[r.region] = r.context

        # 空脑区兜底
        if not candidates:
            return CognitionResult(
                signal_id=signal.id,
                reasoning_level=1,
                confidence=0.0,
                decision="no_action",
                reasoning="所有脑区均无结论",
                actions=[],
                risks=[],
                memory_updates={"coordinator": {"results": [r.to_dict() for r in results],
                                                "enrichment": enrichment_context}},
            )

        # 按加权置信度排序
        def _weighted_conf(c: tuple) -> float:
            _, result, weight = c
            return result.confidence * weight
        candidates.sort(key=_weighted_conf, reverse=True)

        top_region, top_result, top_weight = candidates[0]
        top_weighted = top_result.confidence * top_weight

        # 冲突检测与共识增强
        decisions: List[str] = [c[1].decision for c in candidates]
        unique_decisions = set(decisions)

        final_decision = top_result.decision
        final_confidence = top_result.confidence

        # 共识加成：多脑区同意同一决策
        agreement_count = sum(1 for d in decisions if d == top_result.decision)
        if agreement_count >= 2:
            consensus_bonus = min(0.2, 0.05 * (agreement_count - 1))
            final_confidence = min(1.0, final_confidence + consensus_bonus)
            logger.debug("coordinator: consensus on %s from %d regions, bonus +%.2f",
                          top_result.decision, agreement_count, consensus_bonus)

        # 冲突仲裁：如果有拒绝/升级类决策且与主决策冲突，仲裁
        if len(unique_decisions) > 1:
            for region_name, result, weight in candidates:
                if result.decision == top_result.decision:
                    continue
                # 安全侧决策优先：reject/escalate/flag 优先级更高
                safe_priority = _DECISION_PRIORITY.get(result.decision, 0)
                top_priority = _DECISION_PRIORITY.get(top_result.decision, 0)
                if safe_priority > top_priority and weight >= top_weight * 0.5:
                    # 安全侧脑区置信度足够 → 仲裁为安全决策
                    logger.info("coordinator: conflict resolution — %s overrides %s (priority %d > %d)",
                                 result.decision, top_result.decision, safe_priority, top_priority)
                    final_decision = result.decision
                    final_confidence = min(final_confidence, result.confidence)
                    break

        # 偏离检测：如果 top 脑区置信度显著高于其他（>2x），信任它
        if len(candidates) > 1:
            second_weighted = candidates[1][1].confidence * candidates[1][2]
            if top_weighted / max(second_weighted, 0.01) > 2.0:
                logger.debug("coordinator: top region %s dominates (%.2f vs %.2f)",
                              top_region, top_weighted, second_weighted)

        # 合并 memory_updates
        merged_memory: Dict[str, Any] = {}
        for region_name, result, _ in candidates:
            if result.memory_updates:
                merged_memory[region_name] = {
                    k: v for k, v in result.memory_updates.items()
                    if not k.startswith("_")
                }
        merged_memory["coordinator"] = {
            "results": [r.to_dict() for r in results],
            "enrichment": enrichment_context,
            "conflict": len(unique_decisions) > 1,
            "agreement_count": agreement_count,
            "top_region": top_region,
            "top_weight": top_weight,
        }

        # 合并 actions（去重）
        all_actions: List[Action] = []
        seen_actions: set = set()
        for _, result, _ in candidates:
            for a in result.actions:
                # params 里可能有 list/dict，json.dumps 后再 hash
                key = (a.type, json.dumps(a.params, ensure_ascii=False, sort_keys=True, default=str))
                if key not in seen_actions:
                    seen_actions.add(key)
                    all_actions.append(a)

        # 合并 risks
        all_risks: List[str] = []
        seen_risks: set = set()
        for _, result, _ in candidates:
            for risk in result.risks:
                if risk not in seen_risks:
                    seen_risks.add(risk)
                    all_risks.append(risk)

        # 拼接推理链
        reasoning_parts: List[str] = []
        for region_name, result, weight in candidates:
            if result.reasoning:
                reasoning_parts.append(f"[{region_name}] {result.reasoning}")
        final_reasoning = " | ".join(reasoning_parts) if reasoning_parts else top_result.reasoning

        # 确定最终 reasoning_level（取最高层）
        final_level = max(c[1].reasoning_level for c in candidates)

        return CognitionResult(
            signal_id=signal.id,
            reasoning_level=final_level,
            confidence=round(final_confidence, 3),
            decision=final_decision,
            reasoning=final_reasoning,
            actions=all_actions,
            risks=all_risks,
            memory_updates=merged_memory,
        )


# 全局协调器单例
coordinator = RegionCoordinator()
