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
from services.brain import snn_region as snn_mod
from services.brain.coordinator import RegionCoordinator, RegionResult, coordinator as global_coordinator
from services.brain.compute_budget import ComputeBudget, Intent
from services.brain.semantic import SemanticMemory
from services.brain.broker import broker as broker_mod

logger = logging.getLogger("brain.reasoning")

# 意图提示词：注入 LLM prompt，让 LLM 知道当前信号类型
_INTENT_HINTS = {
    "business": "# 场景：业务请求（审批/报销/采购）。请分析信号内容，判断是否合理，给出审批决策。",
    "alert": '# 场景：告警/异常。信号表示系统错误或风险事件。请评估严重程度，决定是否升级人工处理。',
    "query": '# 场景：知识查询。用户提出问题，请基于上下文回答。decision 用 "no_action"，action type 用 "reply"，reason 填写回答内容。',
    "chitchat": '# 场景：闲聊/问候。用户在进行非业务对话。请友好回复。decision 用 "chat"，action type 用 "chat_reply"，reason 填写你的回复文本。',
    "system": "# 场景：系统内部事件。请评估是否需要处理，通常 no_action 即可。",
    "noise": "# 场景：噪声信号。通常 no_action 即可。",
}


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
        self.llm_api_key = llm_api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("QCLAW_LLM_API_KEY", "")
        self.llm_model = llm_model or os.environ.get("OPENAI_MODEL") or os.environ.get("QCLAW_LLM_MODEL") or "qwen/qwen3.8-flash"
        # API 协议类型：openai | anthropic | gemini，决定 endpoint 路径和请求/响应结构
        self.llm_protocol = (
            os.environ.get("QCLAW_LLM_PROTOCOL")
            or os.environ.get("OPENAI_PROTOCOL")
            or "openai"
        ).lower().strip()
        if self.llm_protocol not in ("openai", "anthropic", "gemini"):
            self.llm_protocol = "openai"
        # LLM 端点/温度：默认从环境变量取，可被 update_llm_config 覆盖
        self.llm_api_base = (
            os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("QCLAW_LLM_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        try:
            self.llm_temperature = float(
                os.environ.get("OPENAI_TEMPERATURE")
                or os.environ.get("QCLAW_LLM_TEMPERATURE")
                or 0.3
            )
        except (TypeError, ValueError):
            self.llm_temperature = 0.3
        # 简单调用计数
        self._stats = {
            "l1_calls": 0, "l1_hits": 0,
            "l2_calls": 0, "l2_hits": 0,
            "l3_calls": 0, "l3_hits": 0,
            "snn_calls": 0, "snn_hits": 0,
            "total": 0,
        }
        # 新架构：脑区协调器 + 算力预算
        self.coordinator = RegionCoordinator()
        self.compute_budget = ComputeBudget()
        self.semantic_memory = SemanticMemory()
        self._register_regions()

    def update_llm_config(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: Optional[float] = None,
        protocol: Optional[str] = None,
    ) -> dict:
        """动态更新 L3 LLM 配置（不重启进程，立即对后续推理生效）。

        传 None 的字段保持不变；api_key 传空串表示清除。
        """
        if api_key is not None:
            self.llm_api_key = api_key
        if model is not None:
            self.llm_model = model
        if api_base is not None:
            self.llm_api_base = api_base.rstrip("/")
        if protocol is not None:
            p = protocol.lower().strip()
            if p in ("openai", "anthropic", "gemini"):
                self.llm_protocol = p
        if temperature is not None:
            try:
                self.llm_temperature = float(temperature)
            except (TypeError, ValueError):
                self.llm_temperature = 0.3
        logger.info(
            "llm_config_updated model=%s base=%s temp=%s key_set=%s protocol=%s",
            self.llm_model,
            self.llm_api_base,
            self.llm_temperature,
            bool(self.llm_api_key),
            self.llm_protocol,
        )
        return {
            "ok": True,
            "model": self.llm_model,
            "api_base": self.llm_api_base,
            "temperature": self.llm_temperature,
            "has_api_key": bool(self.llm_api_key),
            "protocol": self.llm_protocol,
        }

    async def test_llm_connection(self) -> dict:
        """测试 L3 LLM 连通性：发一次最小请求，成功返回内容片段。"""
        if not self.llm_api_key:
            return {"ok": False, "error": "api_key 未配置"}
        try:
            content = await self._call_llm("ping", timeout=15.0)
            return {"ok": True, "model": self.llm_model, "reply": content[:200]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def reason(
        self,
        signal: NeuralSignal,
        working_memory: List[dict],
        db,
        memory_context: Optional[Dict[str, Any]] = None,
    ) -> CognitionResult:
        """主入口：新架构——并行脑区 + 融合。

        流程：
        1. 丘脑分类信号意图（business/alert/query/chitchat/system/noise）
        2. 算力预算按意图分配（决定哪些脑区激活）
        3. 预取：query 意图时先调 web_search（供 LLM prompt 增强）
        4. 各脑区并行执行（rule/statistical/llm/semantic/episodic/web_search）
        5. 融合：加权投票 + 冲突仲裁 + 共识增强
        """
        self._stats["total"] += 1
        memory_context = memory_context or {}

        # 1. 分类
        intent = self._classify_signal(signal)
        # 2. 预算分配
        plan = self.compute_budget.allocate(intent, urgency=signal.urgency)
        # 3. 预取：query 意图时先调 web_search，结果放入 context 供 LLM 使用
        #    其他意图 web_search_region 会直接跳过，但 coordinator 仍会把 region 注册进去
        pre_web_search = None
        if intent == Intent.QUERY and plan.get("web_search") and plan["web_search"].allowed:
            try:
                import services.brain.web_search as ws
                payload = signal.payload or {}
                query = (payload.get("question") or payload.get("text") or payload.get("message") or "").strip()
                if query and len(query) >= 2:
                    print(f"[brain] pre_web_search START query={query[:60]!r}", flush=True)
                    pre_web_search = await ws.search(query=query, max_results=5)
                    if pre_web_search.ok:
                        print(f"[brain] pre_web_search OK results={len(pre_web_search.results)} provider={pre_web_search.provider} elapsed={pre_web_search.elapsed_ms}ms", flush=True)
                        for r in pre_web_search.results[:3]:
                            print(f"  - {r.title[:70]} | {r.url[:70]}", flush=True)
                    else:
                        print(f"[brain] pre_web_search FAILED error={pre_web_search.error}", flush=True)
            except Exception as e:
                print(f"[brain] pre_web_search EXCEPTION {type(e).__name__}: {e}", flush=True)
                logger.warning("pre_web_search failed: %s", str(e))
        # 4. 并行执行 + 融合
        context = {
            "working_memory": working_memory,
            "memory_context": memory_context,
            "db": db,
            "intent": intent.value,
            "pre_web_search": pre_web_search.to_text(max_results=5) if pre_web_search and pre_web_search.ok else None,
        }
        result = await self.coordinator.run(signal, context, plan=plan)

        # 统计
        self._stats["l1_calls"] += 1
        self._stats["l2_calls"] += 1
        self._stats["l3_calls"] += 1
        # 命中判定（任一脑区产出了 result）
        if result.confidence > 0:
            self._stats["l1_hits"] += 1
            self._stats["l2_hits"] += 1
            self._stats["l3_hits"] += 1

        # 记录预算使用
        self.compute_budget.record("rule", time_ms=0, tokens=0)
        self.compute_budget.record("llm", time_ms=0, tokens=0)
        report = self.compute_budget.report(intent, urgency=signal.urgency)
        result.memory_updates["_budget_report"] = report.to_dict()

        return result

    def _classify_signal(self, signal: NeuralSignal) -> Intent:
        """基于信号内容分类意图。

        优先级：type 字段 > payload 关键词 > 默认 business
        """
        sig_type = (signal.type or "").lower()
        payload = signal.payload or {}
        text = " ".join([
            str(payload.get("question", "")),
            str(payload.get("text", "")),
            str(payload.get("message", "")),
        ]).strip().lower()

        # 按 signal.type 分类
        if sig_type in ("alert", "alarm", "anomaly", "threshold_breach", "error", "failed"):
            return Intent.ALERT
        if sig_type in ("noise", "heartbeat", "ping"):
            return Intent.NOISE
        if sig_type in ("system", "healthcheck", "internal"):
            return Intent.SYSTEM
        if sig_type in ("query", "knowledge", "search", "lookup"):
            return Intent.QUERY

        # 按文本关键词分类
        if not text or len(text) < 2:
            return Intent.NOISE

        # 告警关键词
        alert_kw = ("告警", "告警", "异常", "失败", "错误", "超时", "error", "failed", "timeout", "crash")
        if any(k in text for k in alert_kw):
            return Intent.ALERT

        # 闲聊关键词（短且无业务意图）
        chat_kw = ("你好", "hello", "hi", "哈喽", "早上好", "下午好", "晚上好", "早安", "晚安", "在吗", "谢谢", "好的")
        if any(text.startswith(k) or text == k for k in chat_kw):
            return Intent.CHITCHAT

        # 查询关键词（中英文）
        query_kw = (
            "是什么", "什么", "怎么", "如何", "为什么", "什么是", "是谁", "哪", "哪里", "哪个", "何时", "何时", "多少钱",
            "why", "what", "how", "who", "where", "when", "which", "whose", "whose", "what is", "what's", "what do",
            "who is", "who won", "who are", "where is", "where are", "when is", "when was", "when did",
            "tell me", "search", "find", "look up",
        )
        if any(text.startswith(k) or text.lower().startswith(k) for k in query_kw):
            return Intent.QUERY

        # 业务关键词
        biz_kw = ("审批", "报销", "采购", "申请", "合同", "预算", "invoice", "purchase", "approval", "申请", "报销")
        if any(k in text for k in biz_kw):
            return Intent.BUSINESS

        # 短文本默认闲聊，长文本默认业务
        if len(text) <= 10 and not any(c.isalnum() for c in text if c not in " "):
            return Intent.CHITCHAT

        return Intent.BUSINESS

    def _register_regions(self) -> None:
        """注册各脑区到协调器。"""
        # Rule 脑区（L1 规则）
        async def rule_region(signal, context, budget):
            self._stats["l1_calls"] += 1
            result = await self._rule_reasoning(signal, context.get("memory_context"))
            if result and result.confidence >= self.l1_threshold:
                result.signal_id = signal.id
                result.reasoning_level = 1
                return result
            return RegionResult(region="rule", ok=True, result=None,
                                context={"rules_checked": len(rules_mod.list_rules(enabled_only=True))})

        # Statistical 脑区（L2 统计）
        async def statistical_region(signal, context, budget):
            self._stats["l2_calls"] += 1
            result = await self._statistical_reasoning(
                signal, context.get("working_memory", []),
                context.get("db"), context.get("memory_context"),
            )
            if result and result.confidence >= self.l2_threshold:
                result.signal_id = signal.id
                result.reasoning_level = 2
                return result
            return RegionResult(region="statistical", ok=True, result=None)

        # LLM 脑区（L3）
        async def llm_region(signal, context, budget):
            self._stats["l3_calls"] += 1
            intent_val = context.get("intent", "business")
            # CHITCHAT/NOISE 时裁剪 memory_context，避免历史决策数据污染 LLM 判断
            mc = context.get("memory_context", {})
            if intent_val in ("chitchat", "noise"):
                mc = {k: v for k, v in mc.items()
                      if k not in ("history", "decisions", "skills", "memory")}
                if "counts" in mc:
                    mc["counts"] = {k: v for k, v in mc["counts"].items()
                                    if k not in ("history", "memory", "decisions")}
            # QUERY 意图时注入预取 web_search 结果作为 prompt 增强
            web_search_text = context.get("pre_web_search")
            result = await self._llm_reasoning(
                signal, context.get("working_memory", []), mc,
                intent=intent_val,
                web_search_text=web_search_text,
            )
            if result:
                result.signal_id = signal.id
                result.reasoning_level = 3
                return result
            return RegionResult(region="llm", ok=True, result=None)

        # Semantic 脑区（语义记忆检索，enrichment）
        async def semantic_region(signal, context, budget):
            try:
                result = await self.semantic_memory.retrieve(signal.to_dict())
                return RegionResult(
                    region="semantic", ok=True, result=None,
                    context={"semantic": result},
                    elapsed_ms=0,
                )
            except Exception as e:
                return RegionResult(region="semantic", ok=False, error=str(e))

        # Web search 脑区：仅作为 pre-enrichment 在 reason() 里预先调用，不注册为并行脑区
        # （否则会与预取重复，浪费时间/成本）

        # Episodic 脑区（情景记忆检索，enrichment）
        async def episodic_region(signal, context, budget):
            try:
                db = context.get("db")
                if db is None:
                    return RegionResult(region="episodic", ok=False, error="no db")
                entries = await mem.retrieve_for_signal(db, signal.to_dict())
                return RegionResult(
                    region="episodic", ok=True, result=None,
                    context={"episodic": entries},
                    elapsed_ms=0,
                )
            except Exception as e:
                return RegionResult(region="episodic", ok=False, error=str(e))

        # SNN 脑区（脉冲神经网络推理）
        async def snn_region_fn(signal, context, budget):
            self._stats["snn_calls"] = self._stats.get("snn_calls", 0) + 1
            return await snn_mod.snn_region.reason(signal, context, budget)

        self.coordinator.register("rule", rule_region, weight=0.80)
        self.coordinator.register("statistical", statistical_region, weight=0.60)
        self.coordinator.register("llm", llm_region, weight=0.50)
        self.coordinator.register("snn", snn_region_fn, weight=0.40)
        self.coordinator.register("semantic", semantic_region, weight=0.20)
        self.coordinator.register("episodic", episodic_region, weight=0.20)
        # web_search 不注册为并行脑区——已在 reason() 中作为 pre-enrichment 预先调用

    def _memory_summary(self, memory_context: Dict[str, Any]) -> str:
        counts = memory_context.get("counts", {}) if memory_context else {}
        return f"memory={counts.get('memory', 0)}, history={counts.get('history', 0)}, semantic_v={counts.get('semantic_vertices', 0)}, semantic_e={counts.get('semantic_edges', 0)}"

    async def _rule_reasoning(self, signal: NeuralSignal, memory_context: Optional[Dict[str, Any]] = None) -> Optional[CognitionResult]:
        """L1：遍历所有规则，取置信度最高的匹配。"""
        best_rule = None
        best_score = 0.0
        memory_context = memory_context or {}

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
            reasoning=f"匹配规则 {best_rule.id}: {best_rule.description}；记忆命中={self._memory_summary(memory_context)}",
            actions=[Action(type=best_rule.action, reason=best_rule.description)],
            memory_updates={"memory_context_counts": memory_context.get("counts", {})},
        )

    async def _statistical_reasoning(
        self,
        signal: NeuralSignal,
        working_memory: List[dict],
        db,
        memory_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[CognitionResult]:
        """L2：基于历史数据的统计推理。

        - 历史通过率：同类信号的过去决策分布
        - Z-score 异常检测：数值字段的异常识别
        - 组合出增强置信度的推理结果
        """
        memory_context = memory_context or {}
        history = []
        try:
            history = memory_context.get("history") or []
        except Exception:
            history = []
        if not history:
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
            memory_updates={"historical_pattern": {"decision": dominant_decision, "rate": dominant_rate}, "memory_context_counts": memory_context.get("counts", {})},
        )

    async def _llm_reasoning(
        self,
        signal: NeuralSignal,
        working_memory: List[dict],
        memory_context: Optional[Dict[str, Any]] = None,
        intent: str = "business",
        web_search_text: Optional[str] = None,
    ) -> Optional[CognitionResult]:
        """L3：LLM 推理。需要 OPENAI_API_KEY。

        使用 OpenAI 兼容 API。无 key 时返回 None（走兜底）。
        intent: 丘脑分类的意图类型，影响 prompt 构建。
        web_search_text: 预取的联网搜索结果文本（QUERY 意图时注入 prompt）。
        """
        if not self.llm_api_key:
            return None

        # 构建 prompt
        prompt = self._build_llm_prompt(signal, working_memory, memory_context or {},
                                         intent=intent, web_search_text=web_search_text)

        try:
            response = await self._call_llm(prompt)
            result = self._parse_llm_response(response, signal)
            # LLM 置信度上限 0.7（不完全信任）
            result.confidence = min(result.confidence, 0.7)
            return result
        except Exception as e:
            logger.error("l3_llm_failed: %s", str(e))
            return None

    def _build_llm_prompt(self, signal: NeuralSignal, working_memory: List[dict],
                          memory_context: Optional[Dict[str, Any]] = None, intent: str = "business",
                          web_search_text: Optional[str] = None) -> str:
        """构造 LLM prompt。intent 决定提示词策略。

        web_search_text: 联网搜索结果（QUERY 意图时使用），作为外部知识注入。
        """
        signal_dict = signal.to_dict()
        recent = working_memory[-5:] if working_memory else []
        memory_context = memory_context or {}
        memory_summary = {
            "counts": memory_context.get("counts", {}),
            "history": memory_context.get("history", [])[-3:],
            "semantic_counts": {
                "vertices": memory_context.get("semantic", {}).get("vertices", []),
                "edges": memory_context.get("semantic", {}).get("edges", []),
            },
        }

        intent_hint = _INTENT_HINTS.get(intent, _INTENT_HINTS["business"])
        history_json = json.dumps(memory_summary.get("history", []), ensure_ascii=False, indent=2)
        if intent in ("chitchat", "noise"):
            history_json = "(闲聊模式：不查历史决策)"

        # 联网搜索结果区块（仅 QUERY 意图时注入）
        web_search_block = ""
        if intent == "query" and web_search_text:
            web_search_block = f"""

# 联网搜索结果（外部知识参考，供回答使用）
{web_search_text}
"""

        return f"""你是 ZZCC 类脑 AI 推理引擎。分析以下感知信号，给出决策建议。

{intent_hint}

# 当前信号
{json.dumps(signal_dict, ensure_ascii=False, indent=2)}

# 最近上下文（工作记忆）
{json.dumps(recent, ensure_ascii=False, indent=2) if recent else "(无)"}
{web_search_block}
# 记忆上下文
{json.dumps(memory_summary, ensure_ascii=False, indent=2)}

# 历史决策记录
{history_json}

# 输出要求
严格返回 JSON 格式（不要 markdown 代码块包裹）：
{{
  "decision": "auto_approve|reject|escalate|flag|need_info|no_action|chat",
  "confidence": 0.0-1.0,
  "reasoning": "推理过程说明（中文，≤200字）",
  "actions": [{{"type": "action_type", "reason": "原因", "params": {{}}}}],
  "risks": ["风险描述"]
}}

对于闲聊/问候类信号，decision 用 "chat"，action type 用 "chat_reply"，reason 填写你的回复文本。
对于知识查询类信号，decision 用 "no_action"，action type 用 "reply"，reason 填写你基于联网搜索结果的回答文本（中文，引用关键信息）。
对于业务请求，按审批流程给出决策。
请分析后直接返回 JSON。"""

    async def _call_llm(self, prompt: str, timeout: float = 30.0) -> str:
        """调用 LLM（支持 openai / anthropic / gemini 三种协议）。

        端点、模型、温度、协议均取自实例字段，可通过 update_llm_config() 动态覆盖。
        api_base 可以是：
          - 完整端点（如 https://api.openai.com/v1/chat/completions）
          - 前缀（如 https://api.openai.com/v1），系统按协议自动补全
        """
        import httpx

        base_url = self.llm_api_base.rstrip("/")
        proto = getattr(self, "llm_protocol", "openai") or "openai"

        if proto == "anthropic":
            return await self._call_anthropic(prompt, base_url, timeout)
        if proto == "gemini":
            return await self._call_gemini(prompt, base_url, timeout)
        return await self._call_openai(prompt, base_url, timeout)

    async def _call_openai(self, prompt: str, base_url: str, timeout: float) -> str:
        """OpenAI 兼容协议（OpenAI / OpenRouter / Ollama / DeepSeek / Qwen 等）。"""
        import httpx

        # 自动补全：若用户已填 /chat/completions 则不重复
        url = base_url
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": self.llm_temperature,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _call_anthropic(self, prompt: str, base_url: str, timeout: float) -> str:
        """Anthropic Messages API（Claude 原生，默认 https://api.anthropic.com/v1）。"""
        import httpx

        # 默认端点：/v1/messages；若 base_url 已以 /messages 结尾则不再追加
        if base_url.endswith("/messages"):
            url = base_url
        else:
            url = f"{base_url}/messages"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={
                    "x-api-key": self.llm_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.llm_model,
                    "max_tokens": 1024,
                    "temperature": self.llm_temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            parts = data.get("content", [])
            if parts and isinstance(parts, list) and isinstance(parts[0], dict):
                return parts[0].get("text", "")
            return ""

    async def _call_gemini(self, prompt: str, base_url: str, timeout: float) -> str:
        """Google Gemini generateContent API。

        默认 base_url: https://generativelanguage.googleapis.com
        系统自动拼成 /v1beta/models/{model}:generateContent
        """
        import httpx

        # 自动拼完整端点
        if base_url.endswith(":generateContent"):
            url = base_url
        elif base_url.endswith("/v1beta") or base_url.endswith("/v1"):
            url = f"{base_url}/models/{self.llm_model}:generateContent"
        else:
            url = f"{base_url}/v1beta/models/{self.llm_model}:generateContent"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={
                    "x-goog-api-key": self.llm_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": self.llm_temperature},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            for cand in data.get("candidates", []):
                for p in cand.get("content", {}).get("parts", []):
                    if isinstance(p, dict) and "text" in p:
                        return p["text"]
            return ""

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
