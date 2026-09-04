"""services/brain/reasoning.py — 三层推理引擎

L1: 规则引擎     — 确定性规则，毫秒级，零成本
L2: 统计推理     — 基于历史模式，百毫秒级，低成本（Z-score 异常检测 + 历史通过率）
L3: LLM 推理     — 复杂判断，秒级，高成本（需要 OPENAI_API_KEY）
"""
from __future__ import annotations

import json
import logging
import os
import statistics
from typing import Any, Dict, List, Optional

from models.brain import Action, CognitionResult, NeuralSignal
from services.brain import memory as mem
from services.brain import rules as rules_mod

logger = logging.getLogger("brain.reasoning")


# ═══════════════════════════════════════════════════════════
# 推理引擎
# ═══════════════════════════════════════════════════════════
class ReasoningEngine:
    """三层推理引擎。"""

    def __init__(
        self,
        l1_threshold: float = 0.8,
        l2_threshold: float = 0.65,
        llm_api_key: Optional[str] = None,
        llm_model: str = "gpt-4o-mini",
    ):
        self.l1_threshold = l1_threshold
        self.l2_threshold = l2_threshold
        self.llm_api_key = llm_api_key or os.environ.get("OPENAI_API_KEY", "")
        self.llm_model = llm_model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        # 简单调用计数
        self._stats = {
            "l1_calls": 0, "l1_hits": 0,
            "l2_calls": 0, "l2_hits": 0,
            "l3_calls": 0, "l3_hits": 0,
            "total": 0,
        }

    async def reason(
        self,
        signal: NeuralSignal,
        working_memory: List[dict],
        db,
    ) -> CognitionResult:
        """主入口：按 L1 → L2 → L3 递进推理。"""
        self._stats["total"] += 1

        # L1: 规则引擎
        l1 = await self._rule_reasoning(signal)
        self._stats["l1_calls"] += 1
        if l1 and l1.confidence >= self.l1_threshold:
            self._stats["l1_hits"] += 1
            l1.signal_id = signal.id
            l1.reasoning_level = 1
            return l1

        # L2: 统计推理
        l2 = await self._statistical_reasoning(signal, working_memory, db)
        self._stats["l2_calls"] += 1
        if l2 and l2.confidence >= self.l2_threshold:
            self._stats["l2_hits"] += 1
            l2.signal_id = signal.id
            l2.reasoning_level = 2
            return l2

        # L3: LLM 推理
        l3 = await self._llm_reasoning(signal, working_memory)
        self._stats["l3_calls"] += 1
        if l3:
            self._stats["l3_hits"] += 1
            l3.signal_id = signal.id
            l3.reasoning_level = 3
            return l3

        # 兜底
        return CognitionResult(
            signal_id=signal.id,
            reasoning_level=1,
            confidence=0.0,
            decision="no_action",
            reasoning="所有层级推理均无结论",
        )

    async def _rule_reasoning(self, signal: NeuralSignal) -> Optional[CognitionResult]:
        """L1：遍历所有规则，取置信度最高的匹配。"""
        best_rule = None
        best_score = 0.0

        for rule in rules_mod.list_rules(enabled_only=True):
            try:
                matched = await rules_mod._eval_condition(rule.condition, signal.payload, signal.context)
            except Exception:
                matched = False
            if matched:
                if rule.confidence > best_score:
                    best_score = rule.confidence
                    best_rule = rule

        if best_rule is None:
            return None

        return CognitionResult(
            reasoning_level=1,
            confidence=best_score,
            decision=best_rule.action,
            reasoning=f"匹配规则 {best_rule.id}: {best_rule.description}",
            actions=[Action(type=best_rule.action, reason=best_rule.description)],
        )

    async def _statistical_reasoning(
        self,
        signal: NeuralSignal,
        working_memory: List[dict],
        db,
    ) -> Optional[CognitionResult]:
        """L2：基于历史数据的统计推理。

        - 历史通过率：同类信号的过去决策分布
        - Z-score 异常检测：数值字段的异常识别
        - 组合出增强置信度的推理结果
        """
        history = []
        try:
            history = await mem.get_decisions(db, limit=50, signal_type=signal.type)
        except Exception as e:
            logger.warning("l2_history_query_failed: %s", str(e))

        if not history:
            return None

        # 1. 历史决策分布
        decisions = [h["decision"] for h in history]
        decision_counts: Dict[str, int] = {}
        for d in decisions:
            decision_counts[d] = decision_counts.get(d, 0) + 1
        total = len(decisions)
        dominant_decision = max(decision_counts, key=decision_counts.get)
        dominant_rate = decision_counts[dominant_decision] / total

        # 2. Z-score 异常检测
        anomaly_score = 0.0
        anomaly_flags = []
        numeric_fields = []
        for h in history:
            payload_raw = h.get("reasoning", "")
            # 从决策日志的 actions 字段提取数值，简化实现
            # 实际实现应扩展 schema
        # 从当前 signal 提取数值字段
        amount = signal.payload.get("amount")
        if isinstance(amount, (int, float)):
            # 与历史均值比较
            hist_amounts = [h.get("amount") for h in history if isinstance(h.get("amount"), (int, float))]
            if hist_amounts and len(hist_amounts) >= 3:
                mean = statistics.mean(hist_amounts)
                stdev = statistics.stdev(hist_amounts) if len(hist_amounts) >= 2 else 0
                if stdev > 0:
                    z = (amount - mean) / stdev
                    anomaly_score = min(1.0, abs(z) / 3.0)
                    if abs(z) > 2.5:
                        anomaly_flags.append(f"amount={amount} Z={z:.2f} 超出3σ")

        # 3. 合成结果
        if anomaly_score > 0.5:
            decision = "flag"
            confidence = min(0.9, 0.6 + anomaly_score * 0.3)
            reasoning = f"Z-score异常检测触发: {', '.join(anomaly_flags)}; 历史主导决策={dominant_decision}({dominant_rate:.0%})"
            actions = [Action(type="flag", reason="异常数值", params={"anomaly_score": anomaly_score})]
        elif dominant_rate >= 0.7 and dominant_decision in ("auto_approve", "approve"):
            decision = dominant_decision
            confidence = dominant_rate * 0.9
            reasoning = f"历史{dominant_rate:.0%}决策为 {dominant_decision}"
            actions = [Action(type=decision, reason=f"基于历史模式")]
        else:
            return None

        return CognitionResult(
            reasoning_level=2,
            confidence=confidence,
            decision=decision,
            reasoning=reasoning,
            actions=actions,
            memory_updates={"historical_pattern": {"decision": dominant_decision, "rate": dominant_rate}},
        )

    async def _llm_reasoning(
        self,
        signal: NeuralSignal,
        working_memory: List[dict],
    ) -> Optional[CognitionResult]:
        """L3：LLM 推理。需要 OPENAI_API_KEY。

        使用 OpenAI 兼容 API。无 key 时返回 None（走兜底）。
        """
        if not self.llm_api_key:
            return None

        # 构建 prompt
        prompt = self._build_llm_prompt(signal, working_memory)

        try:
            response = await self._call_llm(prompt)
            result = self._parse_llm_response(response, signal)
            # LLM 置信度上限 0.7（不完全信任）
            result.confidence = min(result.confidence, 0.7)
            return result
        except Exception as e:
            logger.error("l3_llm_failed: %s", str(e))
            return None

    def _build_llm_prompt(self, signal: NeuralSignal, working_memory: List[dict]) -> str:
        """构造 LLM prompt。"""
        signal_dict = signal.to_dict()
        recent = working_memory[-5:] if working_memory else []

        return f"""你是 ZZCC 类脑 AI 推理引擎。分析以下感知信号，给出决策建议。

# 当前信号
{json.dumps(signal_dict, ensure_ascii=False, indent=2)}

# 最近上下文（工作记忆）
{json.dumps(recent, ensure_ascii=False, indent=2) if recent else "(无)"}

# 输出要求
严格返回 JSON 格式（不要 markdown 代码块包裹）：
{{
  "decision": "auto_approve|reject|escalate|flag|need_info|no_action",
  "confidence": 0.0-1.0,
  "reasoning": "推理过程说明（中文，≤200字）",
  "actions": [{{"type": "action_type", "reason": "原因", "params": {{}}}}],
  "risks": ["风险描述"]
}}

请分析后直接返回 JSON。"""

    async def _call_llm(self, prompt: str) -> str:
        """调用 OpenAI 兼容 API（支持 OpenAI/Claude proxy/Ollama/OpenRouter 等）。"""
        import httpx

        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_llm_response(self, response: str, signal: NeuralSignal) -> Optional[CognitionResult]:
        """解析 LLM 返回的 JSON。"""
        text = response.strip()
        # 剥离可能的 markdown code fence
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("l3_parse_failed: error=%s raw=%.200s", str(e), text)
            return None

        actions = []
        for a in data.get("actions", []) or []:
            actions.append(Action(
                type=a.get("type", "flag"),
                params=a.get("params", {}) or {},
                reason=a.get("reason", ""),
            ))

        return CognitionResult(
            reasoning_level=3,
            confidence=float(data.get("confidence", 0.5)),
            decision=data.get("decision", "no_action"),
            reasoning=data.get("reasoning", ""),
            actions=actions,
            risks=data.get("risks", []) or [],
        )

    def stats(self) -> dict:
        return dict(self._stats)


# ── 单例 ──
engine = ReasoningEngine()
