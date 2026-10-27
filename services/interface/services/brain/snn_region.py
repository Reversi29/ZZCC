"""services/brain/snn_region.py — SNN 脑区适配器

将 NeuralSignal 编码为 SNN 输入模式，执行 SNN 持续学习推理，将输出解码为 CognitionResult。

架构位置：
    ReasoningEngine._register_regions()
        → snn_region(signal, context, budget) → RegionResult
            → SNN.step_with_learning() → 融合推理+微学习+探索
            → 决策日志自动记录（JSONL）
            → 解码为 CognitionResult

持续学习：
    - 每个信号既是推理输入也是训练数据（在线学习）
    - EWC 防灾难性遗忘（重要权重保护）
    - 探索机制（混乱权利：随机扰动发现边界模式）
    - 自动调节探索率（稳定性↑→探索率↓，错误→探索率↑）

概率涌现：
    - SNN 输出布尔值，不直接暴露概率
    - 决策日志累积后查询 → 事后统计概率分布
    - 相同模式多次决策 → 准确率自然形成概率

反馈学习：
    /brain/learn → 反馈标注 → 微学习（不是批量训练）

持久化：
    SNN.save()/load() → JSON 文件（brain_config_dir/snn_network.json）
    决策日志 → JSONL 文件（brain_config_dir/snn_decision_log.jsonl）
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from models.brain import Action, CognitionResult, NeuralSignal
from services.brain.snn import SNN, NeuronType

logger = logging.getLogger("brain.snn_region")

def _default_brain_config_dir() -> str:
    configured = os.environ.get("BRAIN_CONFIG_DIR", "/app/config_data")
    if os.path.isdir(configured) or os.path.abspath(configured) == "/app/config_data":
        return configured
    local_data = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data"))
    if os.path.isdir(local_data):
        return local_data
    return configured


# ── 信号类型 → 输入神经元 ID 映射 ─────────────────────────────
_SIGNAL_TO_NEURON = {
    "expense": 0,
    "invoice": 0,           # 费用类归并
    "payment": 0,
    "reimbursement": 0,
    "approval_pending": 1,
    "threshold_breach": 2,
    "user_request": 3,
    "cron_alert": 4,
    "external_event": 5,
    "plugin_event": 5,      # 插件事件归并到外部事件
    "error": 6,
    "query": 7,
    "chitchat": 8,
    "system": 9,
    "noise": 10,
}

# ── 输出神经元 ID → 决策类型映射 ──────────────────────────────
_OUTPUT_DECISION = {
    32: "auto_approve",
    33: "reject",
    34: "escalate",
    35: "flag",
    36: "no_action",
    37: "chat",
}

# ── 紧急度 → 输入神经元映射 ─────────────────────────────────
def _urgency_neuron(urgency: int) -> Optional[int]:
    """紧急度 0-100 → 输入神经元 11（高位标记）"""
    if urgency >= 70:
        return 11
    return None


# ── payload 特征 → 输入神经元映射（v2） ─────────────────────
_AMOUNT_LOW_MAX = 1000.0       # 金额 ≤ 此值 → amount_low (neuron 12)
_AMOUNT_HIGH_MIN = 100000.0    # 金额 > 此值 → amount_high (neuron 14)
_DETAIL_KEYS = (
    "description", "desc", "title", "text", "note",
    "content", "remark", "summary", "reason", "question",
)


def _payload_features(payload: Any) -> tuple:
    """从 payload 提取 (金额分桶神经元 ID, 是否有详情字段)。

    Returns:
        (amount_neuron_id | None, has_detail: bool)
    """
    if not isinstance(payload, dict):
        return None, False

    # 金额提取：兼容 amount / price / value / total
    amount = payload.get("amount")
    if amount is None:
        amount = payload.get("price") or payload.get("value") or payload.get("total")

    amount_neuron = None
    if isinstance(amount, (int, float)) and amount >= 0:
        if amount <= _AMOUNT_LOW_MAX:
            amount_neuron = 12       # amount_low
        elif amount <= _AMOUNT_HIGH_MIN:
            amount_neuron = 13       # amount_medium
        else:
            amount_neuron = 14       # amount_high

    has_detail = any(k in payload for k in _DETAIL_KEYS)
    return amount_neuron, has_detail


class SNNRegion:
    """SNN 脑区：脉冲神经网络推理。

    特性：
    - 步进式计算（非真实时间延迟）
    - 奖励调制 Hebbian 学习（从反馈标注中学习）
    - 状态持久化（JSON 文件）
    - 结构可塑（增删神经元/连接）
    """

    _OUTPUT_NEURONS = [32, 33, 34, 35, 36, 37]

    # 推理步数：SNN 运行的最大时间步数
    INFERENCE_STEPS = 10

    def __init__(self, save_path: Optional[str] = None):
        config_dir = _default_brain_config_dir()
        self.save_path = save_path or os.path.join(config_dir, "snn_network.json")

        self._stats_path = self.save_path.replace(".json", "_stats.json")

        # 加载或创建默认网络
        self.snn = SNN.load(self.save_path)
        if self.snn is None:
            logger.info("snn: creating default topology")
            self.snn = SNN.create_default()
            self._auto_save()

        self._stats = {
            "reason_calls": 0,
            "reason_hits": 0,
            "total_fires": 0,
            "last_decision": "",
            "last_confidence": 0.0,
            "training_count": 0,
            "edges_added": 0,
            "edges_strengthened": 0,
            "edges_penalized": 0,
            # 持续学习统计
            "exploration_rate": 0.1,
            "boundary_detected_count": 0,
            "ewc_protected_edges": 0,
            "micro_learn_steps": 0,
        }
        self._load_stats()

        # 决策日志路径
        self._decision_log_path = self.save_path.replace(".json", "_decision_log.jsonl")

    # ── 编码/解码 ────────────────────────────────────────────

    def _encode_signal(self, signal: NeuralSignal) -> List[int]:
        """将 NeuralSignal 编码为 SNN 输入神经元列表（v2：含 payload 特征）。

        编码维度：
        - 信号类型 → neuron 0-10
        - 紧急度高 → neuron 11
        - 金额分桶 → neuron 12 (low) / 13 (medium) / 14 (high)
        - 有详情字段 → neuron 15

        同类型信号可通过 payload 特征区分（如 approval_pending 小额→flag / 大额→escalate）。
        """
        neurons: List[int] = []
        sig_type = (signal.type or "").lower()
        nid = _SIGNAL_TO_NEURON.get(sig_type)
        if nid is not None:
            neurons.append(nid)

        # 紧急度编码
        u_neuron = _urgency_neuron(signal.urgency)
        if u_neuron is not None:
            neurons.append(u_neuron)

        # payload 特征编码（v2）
        payload = signal.payload or {}
        amount_neuron, has_detail = _payload_features(payload)
        if amount_neuron is not None:
            neurons.append(amount_neuron)
        if has_detail:
            neurons.append(15)

        # 如果信号类型未映射，用 hash 分桶到输入神经元
        if not neurons:
            if sig_type:
                bucket = hash(sig_type) % 11
                neurons.append(bucket)

        return neurons or [10]  # 默认 noise

    def _decode_output(self, outputs: Dict[int, bool],
                        active: List[int]) -> Optional[CognitionResult]:
        """将 SNN 输出解码为 CognitionResult。

        多输出时不直接全部采信：按当前激活/膜势强的前驱连接强度排序，
        选择最强输出，并把竞争输出写入 memory_updates 供调试。
        """
        # 检查输出神经元是否在推理期间放电过（last_fire_time >= 0）
        # 注意：放电后 membrane 会重置为 0，不能用 membrane > 0 判断
        fired_outputs = [nid for nid, v in outputs.items() if v]
        if not fired_outputs:
            # 兜底：检查 last_fire_time（某些 step 可能 outputs 没捕获到）
            fired_outputs = [
                nid for nid in self._OUTPUT_NEURONS
                if self.snn.neurons[nid].last_fire_time >= 0
            ]
        if not fired_outputs:
            return None

        strengths: Dict[int, float] = {}
        hidden_source_ids = set(
            n.id for n in self.snn.neurons
            if 16 <= n.id < 32 and n.last_fire_time >= 0
        )
        for out_nid in fired_outputs:
            n = self.snn.neurons[out_nid]
            score = max(0.1, float(n.membrane or 0.0))
            for src_nid in hidden_source_ids:
                conn = self.snn.out_edges.get(src_nid, {}).get(out_nid)
                if conn is not None:
                    score += conn.weight * 2.0
            if score <= 0.1:
                for src in self.snn.neurons:
                    if src.last_fire_time >= 0 and src.id < 16:
                        conn = self.snn.out_edges.get(src.id, {}).get(out_nid)
                        if conn is not None:
                            score += conn.weight
            strengths[out_nid] = score

        sorted_outputs = sorted(strengths.items(), key=lambda item: item[1], reverse=True)
        top_nid, top_score = sorted_outputs[0]
        decision = _OUTPUT_DECISION.get(top_nid)
        if decision is None:
            return None

        total_score = sum(max(0.0, score) for _, score in sorted_outputs)
        confidence = 0.35
        if total_score > 0:
            confidence += min(0.45, top_score / total_score * 0.65)
        if len(sorted_outputs) == 1:
            confidence += 0.1
        confidence = round(min(1.0, max(0.0, confidence)), 3)

        competition = [
            {"output_neuron": nid, "decision": _OUTPUT_DECISION.get(nid), "score": round(score, 3)}
            for nid, score in sorted_outputs
        ]
        fired_outputs_serializable = [
            {"output_neuron": nid, "decision": _OUTPUT_DECISION.get(nid), "score": round(score, 3)}
            for nid, score in sorted_outputs
        ]

        return CognitionResult(
            reasoning_level=3,  # 类 L3 级别
            confidence=confidence,
            decision=decision,
            reasoning=f"SNN 脉冲推理: 激活神经元={active[:10]}, 输出={fired_outputs_serializable}",
            actions=[Action(type=decision, reason="SNN 脉冲神经网络推理")],
            memory_updates={
                "snn_active": active,
                "snn_outputs": outputs,
                "snn_competition": competition,
                "snn_selected": top_nid,
            },
        )

    # ── 推理入口（供协调器调用）────────────────────────────

    async def reason(
        self,
        signal: NeuralSignal,
        context: Dict[str, Any],
        budget: Any = None,
    ) -> Any:
        """SNN 推理入口。返回 RegionResult。

        从 coordinator 调用的标准签名。
        使用 step_with_learning() 融合推理+微学习+探索。

        持续学习流程：
        1. 编码信号为输入神经元
        2. step_with_learning() → 推理 + 微学习 + 探索
        3. 记录决策日志（JSONL）
        4. 解码输出为 CognitionResult

        注意：不在推理前 reset_learning_state()，保留学习历史。
        这样连续信号之间可以共享学习状态，实现真正的在线学习。
        """
        from services.brain.coordinator import RegionResult

        start = time.time()
        self._stats["reason_calls"] += 1

        try:
            # 编码输入
            input_neurons = self._encode_signal(signal)
            strength = 2.0 + (signal.urgency / 100.0) * 3.0  # 0.0-3.0

            # 持续学习推理：融合推理+微学习+探索
            # 不传 expected_decision，因为推理时没有反馈
            outputs, boundary_detected = self.snn.step_with_learning(
                input_neurons, strength
            )

            # 记录探索结果
            if boundary_detected:
                self._stats["boundary_detected_count"] += 1

            # 记录探索率
            self._stats["exploration_rate"] = self.snn._exploration_rate

            active = self.snn.get_active_neurons()
            result = self._decode_output(outputs, active)

            elapsed = (time.time() - start) * 1000

            # 记录决策日志
            self._log_decision(
                signal,
                input_neurons,
                outputs,
                result.decision if result else None,
                result.confidence if result else 0.0,
                elapsed,
                boundary_detected,
            )

            if result and result.confidence >= 0.3:
                result.signal_id = signal.id
                self._stats["reason_hits"] += 1
                self._stats["last_decision"] = result.decision
                self._stats["last_confidence"] = result.confidence
                self._stats["total_fires"] = self.snn.stats()["total_fires"]

                return RegionResult(
                    region="snn", ok=True,
                    result=result,
                    context={
                        "input_neurons": input_neurons,
                        "steps_run": self.snn.time,
                        "boundary_detected": boundary_detected,
                        "exploration_rate": self._stats["exploration_rate"],
                    },
                    elapsed_ms=elapsed,
                )

            # 未产生有效结果
            return RegionResult(
                region="snn", ok=True, result=None,
                context={
                    "input_neurons": input_neurons,
                    "reason": "SNN 输出未达阈值",
                    "stats": self.snn.stats(),
                    "exploration_rate": self._stats["exploration_rate"],
                },
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return RegionResult(
                region="snn", ok=False,
                error=str(e), elapsed_ms=elapsed,
            )

    # ── 决策日志 ────────────────────────────────────────────

    def _log_decision(
        self,
        signal: NeuralSignal,
        input_neurons: List[int],
        outputs: Dict[int, bool],
        decision: Optional[str],
        confidence: float,
        elapsed_ms: float,
        boundary_detected: bool,
    ):
        """记录决策日志（JSONL 格式）。

        每条记录包含：
        - signal_id, signal_type, urgency
        - input_neurons, outputs
        - decision, confidence
        - timestamp, elapsed_ms
        - boundary_detected
        - exploration_rate

        用途：
        1. 事后查询概率分布（相同模式多次决策的准确率）
        2. 训练数据回放（选择高置信度样本）
        3. 决策审计（谁在什么时候做了什么决策）
        """
        import datetime

        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "signal_id": signal.id,
            "signal_type": signal.type,
            "urgency": signal.urgency,
            "input_neurons": input_neurons,
            "outputs": {str(k): v for k, v in outputs.items()},
            "decision": decision,
            "confidence": confidence,
            "elapsed_ms": round(elapsed_ms, 2),
            "boundary_detected": boundary_detected,
            "exploration_rate": self._stats.get("exploration_rate", 0.1),
        }

        try:
            with open(self._decision_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("snn: decision log failed: %s", str(e))

    def query_decision_probability(
        self,
        signal_type: str,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """查询决策概率分布（事后统计）。

        从决策日志中统计相同信号类型的决策分布。

        Args:
            signal_type: 信号类型（如 "expense", "approval_pending"）
            limit: 查询最近 N 条记录

        Returns:
            {
                "signal_type": "expense",
                "total": 50,
                "distribution": {"auto_approve": 0.6, "escalate": 0.3, ...},
                "recent": [...]  # 最近 10 条记录
            }
        """
        if not os.path.exists(self._decision_log_path):
            return {"signal_type": signal_type, "total": 0, "distribution": {}}

        try:
            entries = []
            with open(self._decision_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("signal_type") == signal_type:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue

            # 取最近 limit 条
            entries = entries[-limit:]

            if not entries:
                return {"signal_type": signal_type, "total": 0, "distribution": {}}

            # 统计决策分布
            decision_counts: Dict[str, int] = {}
            for e in entries:
                dec = e.get("decision")
                if dec:
                    decision_counts[dec] = decision_counts.get(dec, 0) + 1

            total = len(entries)
            distribution = {
                k: round(v / total, 3)
                for k, v in sorted(decision_counts.items(), key=lambda x: -x[1])
            }

            # 最近 10 条
            recent = [
                {
                    "timestamp": e.get("timestamp"),
                    "decision": e.get("decision"),
                    "confidence": e.get("confidence"),
                    "boundary_detected": e.get("boundary_detected"),
                }
                for e in entries[-10:]
            ]

            return {
                "signal_type": signal_type,
                "total": total,
                "distribution": distribution,
                "recent": recent,
            }

        except Exception as e:
            logger.warning("snn: probability query failed: %s", str(e))
            return {"signal_type": signal_type, "total": 0, "distribution": {}, "error": str(e)}

    # ── 反馈学习 ────────────────────────────────────────────

    def train_from_feedback(
        self,
        signal: NeuralSignal,
        correct_decision: str,
        was_correct: bool,
        wrong_decision: Optional[str] = None,
        eta: float = 0.02,
        inject_strength: float = 2.0,
    ) -> dict:
        """从反馈标注中学习。

        Args:
            signal: 原始信号（重放输入模式）
            correct_decision: 正确决策（如 "auto_approve"）
            was_correct: 原始推理是否正确
            wrong_decision: 错误决策（was_correct=False 时用于惩罚；默认读 last_decision）

        Returns:
            学习结果摘要
        """
        input_neurons = self._encode_signal(signal)
        target_output = self._decision_to_output_neuron(correct_decision)

        if target_output is None:
            return {"ok": False, "reason": f"未知决策类型: {correct_decision}"}

        self._stats["training_count"] += 1
        self._stats["micro_learn_steps"] += 1

        # 三阶段训练：输入 → 传播 → 奖励 → STDP
        # 关键：注入输入后先 step 让隐藏层放电，再注入输出
        # 这样 hidden.last_fire_time < output.last_fire_time，STDP 才能生效
        strength = 2.0 + (signal.urgency / 100.0) * 3.0
        eta = 0.02  # 微学习步长
        auto_create = False  # auto_create 会导致非选择性直连，LTD 实验结论：禁用

        if was_correct:
            # 正确决策 → 加强到正确输出的连接
            for _ in range(5):
                self.snn.inject_pattern(input_neurons, strength)
                self.snn.step()  # t=N:   输入放电，传播到隐藏层
                self.snn.step()  # t=N+1: 隐藏层放电（事件到达）
                self.snn.inject_input(target_output, inject_strength)
                outputs = self.snn.step()  # t=N+2: 输出放电
                if outputs.get(target_output, False):
                    before = sum(
                        1 for src in self.snn.out_edges
                        for c in self.snn.out_edges[src].values()
                        if c.weight > 0.1
                    )
                    strengthened = self.snn._reward_modulated_strengthen(
                        target_output, eta=eta,
                        auto_create=auto_create,
                        auto_create_weight=0.15,
                    )
                    after = sum(
                        1 for src in self.snn.out_edges
                        for c in self.snn.out_edges[src].values()
                        if c.weight > 0.1
                    )
                    self._stats["edges_added"] += max(0, after - before)
                    self._stats["edges_strengthened"] += strengthened
        else:
            # 错误决策 → 惩罚原始输出，同时轻微加强正确输出
            original_decision = wrong_decision or self._stats.get("last_decision", "")
            penalty_output = self._decision_to_output_neuron(original_decision)
            if penalty_output is not None:
                for src in list(self.snn.out_edges.keys()):
                    if penalty_output in self.snn.out_edges[src]:
                        conn = self.snn.out_edges[src][penalty_output]
                        conn.weight = max(0, conn.weight * 0.8)
                        self._stats["edges_penalized"] += 1
            # 少量加强正确输出（让下次推理偏向正确决策）
            for _ in range(2):
                self.snn.inject_pattern(input_neurons, strength)
                self.snn.step()
                self.snn.step()
                self.snn.inject_input(target_output, inject_strength * 0.5)  # 较弱注入
                outputs = self.snn.step()
                if outputs.get(target_output, False):
                    strengthened = self.snn._reward_modulated_strengthen(
                        target_output, eta=eta * 0.5,
                        auto_create=False,
                        auto_create_weight=0.10,
                    )
                    self._stats["edges_strengthened"] += strengthened

        self._auto_save()

        return {
            "ok": True,
            "signal_type": signal.type,
            "correct_decision": correct_decision,
            "was_correct": was_correct,
            "input_neurons": input_neurons,
            "target_output": target_output,
            "snn_stats": self.snn.stats(),
        }

    def _decision_to_output_neuron(self, decision: str) -> Optional[int]:
        """决策类型 → 输出神经元 ID。"""
        for nid, dec in _OUTPUT_DECISION.items():
            if dec == decision:
                return nid
        return None

    # ── 持久化 ──────────────────────────────────────────────

    def _auto_save(self):
        """自动保存网络状态和统计。"""
        try:
            self.snn.save(self.save_path)
            self._save_stats()
        except Exception as e:
            logger.warning("snn_auto_save_failed: %s", str(e))

    def save(self) -> bool:
        """手动保存。"""
        return self.snn.save(self.save_path)

    # ── 管理接口 ────────────────────────────────────────────

    def reset(self):
        """重置推理状态（不重置权重）。"""
        self.snn.reset()

    def reset_network(self):
        """重置为默认网络（清除所有学习）。"""
        self.snn = SNN.create_default()
        self._stats = {
            "reason_calls": 0, "reason_hits": 0,
            "total_fires": 0, "last_decision": "",
            "last_confidence": 0.0, "training_count": 0,
            "edges_added": 0, "edges_strengthened": 0, "edges_penalized": 0,
        }
        self._auto_save()

    def _load_stats(self):
        import json
        if not os.path.exists(self._stats_path):
            return
        try:
            with open(self._stats_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._stats.update(data)
        except Exception as e:
            logger.warning("snn: stats load failed: %s", str(e))

    def _save_stats(self):
        import json
        try:
            with open(self._stats_path, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("snn: stats save failed: %s", str(e))

    def status(self) -> dict:
        """网络状态快照。"""
        return {
            "ok": True,
            "save_path": self.save_path,
            "stats": self._stats,
            "network": self.snn.stats(),
        }

    def connection_graph(self) -> dict:
        """连接图（供前端可视化）。"""
        nodes = []
        for n in self.snn.neurons:
            nodes.append({
                "id": n.id,
                "type": n.neuron_type.value,
                "fire_count": n.fire_count,
            })
        edges = []
        for src in self.snn.out_edges:
            for tgt, conn in self.snn.out_edges[src].items():
                edges.append({
                    "source": src,
                    "target": tgt,
                    "weight": round(conn.weight, 4),
                    "delay": conn.delay,
                })
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": self.snn.stats(),
        }

    # 全局单例
    global_instance: Optional["SNNRegion"] = None


class ShadowSNNRegion(SNNRegion):
    """辅助 SNN shadow 脑区。

    MVP 最小闭环：
    - 复用 SNNRegion 的编码/解码逻辑
    - 只观察主 SNN 结果，不参与最终融合
    - 结果写入 context["shadow:snn_aux"] 供后续评估/回放
    """

    def __init__(self, save_path: Optional[str] = None):
        config_dir = _default_brain_config_dir()
        save_path = save_path or os.path.join(config_dir, "snn_shadow_network.json")
        super().__init__(save_path=save_path)
        self._stats_path = self.save_path.replace(".json", "_stats.json")
        self._stats.update({
            "shadow_calls": 0,
            "shadow_hits": 0,
            "agreement": 0,
            "disagreement": 0,
            "replay_count": 0,
            "null_shadow_calls": 0,
            "last_shadow_decision": "",
            "last_main_decision": "",
        })
        self._load_stats()
        # 决策对比日志路径（shadow 专用）
        self._shadow_log_path = self.save_path.replace(".json", "_shadow_compare.jsonl")
        # 扰动标记文件（确保只扰动一次）
        self._perturbed_flag_path = self.save_path.replace(".json", "_perturbed.flag")
        # Shadow 必须是主 SNN 的“异质变体”：初始化时对所有权重加扰动，
        # 否则从同一 create_default() 出发、未训练时输出完全一致，永远 agreement，无观测价值。
        # 扰动只影响 shadow 自身网络，不触碰主 SNN。
        self._perturb_network()
        self._save_stats()  # 确保统计文件存在

    def _perturb_network(self, amplitude: float = 0.35, n_extra_edges: int = 8):
        """对 shadow 网络进行异质化：权重扰动 + 随机新增连接。

        仅第一次执行（标记文件不存在时）。

        异质化策略：
        1. 权重扰动：对现有边加 ±amplitude 的随机扰动
        2. 结构扰动：随机新增若干条 input→hidden 或 hidden→output 的边
           这些新边在主 SNN 中不存在，为 shadow 提供替代路径，
           从而在某些输入下产生不同的输出（真正的 disagreement）。
        """
        try:
            if os.path.exists(self._perturbed_flag_path):
                return
            import random
            rng = random.Random()

            # Phase 1: 权重扰动
            changed = 0
            for src, targets in self.snn.out_edges.items():
                for tgt, conn in list(targets.items()):
                    if conn is None:
                        continue
                    factor = 1.0 + rng.uniform(-amplitude, amplitude)
                    conn.weight = max(0.05, min(self.snn.max_weight, conn.weight * factor))
                    changed += 1

            # Phase 2: 结构扰动 — 随机新增边
            # 输入层 (0-15) → 隐藏层 (16-27 exc, 28-31 inh)
            # 隐藏层 → 输出层 (32-37)
            added = 0
            input_range = list(range(0, 16))
            exc_range = list(range(16, 28))
            inh_range = list(range(28, 32))
            output_range = list(range(32, 38))
            attempts = n_extra_edges * 3  # 尝试更多次以避开已存在的边
            for _ in range(attempts):
                if added >= n_extra_edges:
                    break
                # 随机选择边类型
                if rng.random() < 0.5:
                    src = rng.choice(input_range)
                    tgt_pool = exc_range if rng.random() < 0.85 else inh_range
                    tgt = rng.choice(tgt_pool)
                    w = round(rng.uniform(0.5, 1.5), 3)
                else:
                    src = rng.choice(exc_range + inh_range)
                    tgt = rng.choice(output_range)
                    w = round(rng.uniform(0.8, 2.0), 3)
                # 跳过已存在的边
                if tgt in self.snn.out_edges.get(src, {}):
                    continue
                self.snn.connect(src, tgt, weight=w, delay=1)
                added += 1

            logger.info(
                "shadow: perturbed %d edges + added %d structural edges (heterogenous topology)",
                changed, added,
            )

            # 持久化扰动后的网络
            try:
                self.snn.save(self.save_path)
            except Exception as e:
                logger.warning("shadow: perturb save failed: %s", str(e))

            # 写入标记
            with open(self._perturbed_flag_path, "w", encoding="utf-8") as f:
                f.write("ok")
        except Exception as e:
            logger.warning("shadow: perturb failed: %s", str(e))

    async def reason(self, signal: NeuralSignal, context: Dict[str, Any], budget: Any = None):
        from services.brain.coordinator import RegionResult
        from services.brain.compute_budget import RegionBudget

        start = time.time()
        self._stats["shadow_calls"] = self._stats.get("shadow_calls", 0) + 1
        try:
            budget = budget or RegionBudget(time_ms=300, tokens=0, allowed=True)
            if not getattr(budget, "allowed", True):
                return RegionResult(region="shadow:snn_aux", ok=True, result=None,
                                    context={"reason": "shadow disabled by budget"}, elapsed_ms=0)

            input_neurons = self._encode_signal(signal)
            outputs, _ = self.snn.step_with_learning(input_neurons, 2.0)
            result = self._decode_output(outputs, self.snn.get_active_neurons())
            main_decision = context.get("main_snn_result")
            if main_decision is not None and not isinstance(main_decision, str):
                main_decision = getattr(main_decision, "decision", None)
            shadow_decision = result.decision if result else None

            # 对比统计：
            # - agreement: shadow 与主决策都非空且相同
            # - disagreement: 两者都非空但不同，或一方为 null 另一方非 null（真实差异）
            #   null 差异是 shadow 异质化的核心价值——它在主 SNN 无法决策或决策不同的场景中提供不同视角
            if shadow_decision and main_decision:
                if shadow_decision == main_decision:
                    self._stats["agreement"] = self._stats.get("agreement", 0) + 1
                    self._stats["shadow_hits"] = self._stats.get("shadow_hits", 0) + 1
                else:
                    self._stats["disagreement"] = self._stats.get("disagreement", 0) + 1
            elif (shadow_decision and not main_decision) or (not shadow_decision and main_decision):
                # 一方有输出另一方无——记录为 disagreement（带类型区分）
                self._stats["disagreement"] = self._stats.get("disagreement", 0) + 1
                if shadow_decision and not main_decision:
                    self._stats["null_shadow_calls"] = self._stats.get("null_shadow_calls", 0) + 1
                else:
                    self._stats["null_shadow_calls"] = self._stats.get("null_shadow_calls", 0) + 1
            if shadow_decision:
                self._stats["last_shadow_decision"] = shadow_decision
            elif main_decision:
                # shadow 无输出时，记录主决策供回放/审计
                self._stats["last_shadow_decision"] = "<null>"
            if main_decision:
                self._stats["last_main_decision"] = main_decision

            # 写入 shadow 对比日志（JSONL），供回放/审计
            try:
                import datetime
                import json
                cmp_entry = {
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "signal_id": signal.id,
                    "signal_type": signal.type,
                    "input_neurons": input_neurons,
                    "main_decision": main_decision,
                    "shadow_decision": shadow_decision,
                    "payload": signal.payload or {},
                    "urgency": signal.urgency,
                    "agreement": self._stats.get("agreement", 0),
                    "disagreement": self._stats.get("disagreement", 0),
                }
                with open(self._shadow_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(cmp_entry, ensure_ascii=False) + "\n")
            except Exception:
                pass

            # 立即落盘 shadow 统计，避免重启丢失
            try:
                self._save_stats()
            except Exception:
                pass

            if result:
                result.signal_id = signal.id
            elapsed = (time.time() - start) * 1000
            return RegionResult(
                region="shadow:snn_aux",
                ok=True,
                result=result,
                context={
                    "shadow": True,
                    "input_neurons": input_neurons,
                    "main_decision": main_decision,
                    "shadow_decision": shadow_decision,
                    "agreement": self._stats.get("agreement", 0),
                    "disagreement": self._stats.get("disagreement", 0),
                },
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return RegionResult(region="shadow:snn_aux", ok=False, error=str(e), elapsed_ms=elapsed)

    def replay_disagreements(self, limit: int = 50, dry_run: bool = True) -> dict:
        """从对比日志回放 disagreement 样本，训练 shadow 向主决策收敛。

        读取 snn_shadow_network_shadow_compare.jsonl，筛选 main_decision != shadow_decision 的样本，
        用 train_from_feedback() 以主决策为正确目标进行微学习。

        Args:
            limit: 最多回放的样本数
            dry_run: True 时只统计不训练；False 时实际训练并保存

        Returns:
            摘要：{ok, samples, matched, trained, strengthened, disagreement_before, disagreement_after}
        """
        import json
        import os

        if not os.path.exists(self._shadow_log_path):
            return {"ok": True, "samples": 0, "matched": 0, "trained": 0,
                    "reason": "no compare log", "disagreement_before": self._stats.get("disagreement", 0)}

        samples = []
        try:
            with open(self._shadow_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        s = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    main_d = s.get("main_decision")
                    shadow_d = s.get("shadow_decision")
                    # 只采样真实差异：两者都非空且不同，或一方 null 另一方非 null
                    if main_d is None and shadow_d is None:
                        continue
                    if main_d == shadow_d:
                        continue
                    samples.append(s)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        if not samples:
            return {"ok": True, "samples": 0, "matched": 0, "trained": 0,
                    "reason": "no disagreement samples", "disagreement_before": self._stats.get("disagreement", 0)}

        samples = samples[-limit:]
        matched = 0
        trained = 0
        strengthened_before = self._stats.get("edges_strengthened", 0)
        strengthened_penalty_before = self._stats.get("edges_penalized", 0)
        for s in samples:
            sig_id = s.get("signal_id")
            main_d = s.get("main_decision")
            shadow_d = s.get("shadow_decision")
            payload = s.get("payload") or {}
            urgency = s.get("urgency", 50)
            sig_type = s.get("signal_type", "user_request")
            # 目标决策：主决策优先；主无输出则用 shadow 自身决策
            target_decision = main_d if main_d else shadow_d
            # 错误决策：shadow 原本输出（需被惩罚）
            wrong_d = shadow_d if (main_d and shadow_d and main_d != shadow_d) else None
            # 构造回放信号
            signal = NeuralSignal(
                id=sig_id or f"replay-{matched}",
                type=sig_type,
                payload=payload,
                source="shadow_replay",
                urgency=urgency,
            )
            if dry_run:
                matched += 1
                continue
            try:
                res = self.train_from_feedback(
                    signal=signal,
                    correct_decision=target_decision,
                    was_correct=False,
                    wrong_decision=wrong_d,
                    eta=0.16,
                    inject_strength=3.0,
                )
                if res.get("ok"):
                    matched += 1
                    trained += 1
            except Exception:
                continue

        if not dry_run:
            self._stats["replay_count"] = self._stats.get("replay_count", 0) + 1
            try:
                self._save_stats()
            except Exception:
                pass

        return {
            "ok": True,
            "samples": len(samples),
            "matched": matched,
            "trained": trained,
            "strengthened": self._stats.get("edges_strengthened", 0) - strengthened_before,
            "penalized": self._stats.get("edges_penalized", 0) - strengthened_penalty_before,
            "replay_count": self._stats.get("replay_count", 0),
            "dry_run": dry_run,
            "disagreement_before": self._stats.get("disagreement", 0),
        }


shadow_snn_region = ShadowSNNRegion(save_path=os.path.join(_default_brain_config_dir(), "snn_shadow_network.json"))
snn_region = SNNRegion()
