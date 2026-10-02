"""services/brain/snn_region.py — SNN 脑区适配器

将 NeuralSignal 编码为 SNN 输入模式，执行 SNN 推理，将输出解码为 CognitionResult。

架构位置：
    ReasoningEngine._register_regions()
        → snn_region(signal, context, budget) → RegionResult
            → SNN.inject_pattern(...) → SNN.step() × N → SNN.get_outputs()
            → 解码为 CognitionResult

学习闭环：
    /brain/learn → 反馈标注 → SNN.train_by_association() → 权重更新

持久化：
    SNN.save()/load() → JSON 文件（brain_config_dir/snn_network.json）
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

# ── 信号类型 → 输入神经元 ID 映射 ─────────────────────────────
_SIGNAL_TO_NEURON = {
    "approval_pending": 0,
    "threshold_breach": 1,
    "plugin_event": 2,
    "user_request": 3,
    "cron_alert": 4,
    "external_event": 5,
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

    # 推理步数：SNN 运行的最大时间步数
    INFERENCE_STEPS = 10

    def __init__(self, save_path: Optional[str] = None):
        config_dir = os.environ.get("BRAIN_CONFIG_DIR", "/app/config_data")
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
        }
        self._load_stats()

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
        fired_outputs = [nid for nid, v in outputs.items() if v]
        if not fired_outputs:
            return None

        strengths: Dict[int, float] = {}
        source_ids = set(active)
        for out_nid in fired_outputs:
            score = float(self.snn.neurons[out_nid].membrane or 0.0)
            for src_nid in source_ids:
                conn = self.snn.out_edges.get(src_nid, {}).get(out_nid)
                if conn is not None:
                    score += conn.weight
            # 至少给激活输出一个基础分，避免膜电位/前驱记录缺失导致无法解码
            strengths[out_nid] = max(0.1, score)

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
        每次推理前 reset 网络状态，避免训练残留污染。
        """
        from services.brain.coordinator import RegionResult

        start = time.time()
        self._stats["reason_calls"] += 1
        self.snn.reset()

        try:
            # 编码输入
            input_neurons = self._encode_signal(signal)
            strength = 1.0 + (signal.urgency / 100.0) * 2.0  # 0.0-3.0

            # 注入输入
            self.snn.inject_pattern(input_neurons, strength)

            # 运行推理步
            best_result: Optional[CognitionResult] = None
            best_confidence = 0.0

            for _ in range(self.INFERENCE_STEPS):
                outputs = self.snn.step()
                active = self.snn.get_active_neurons()
                result = self._decode_output(outputs, active)

                if result and result.confidence > best_confidence:
                    best_confidence = result.confidence
                    best_result = result

                # 早期退出：输出已激活且置信度足够
                if best_result and best_confidence >= 0.5:
                    break

            elapsed = (time.time() - start) * 1000

            if best_result and best_confidence >= 0.3:
                best_result.signal_id = signal.id
                self._stats["reason_hits"] += 1
                self._stats["last_decision"] = best_result.decision
                self._stats["last_confidence"] = best_result.confidence
                self._stats["total_fires"] = self.snn.stats()["total_fires"]

                return RegionResult(
                    region="snn", ok=True,
                    result=best_result,
                    context={
                        "input_neurons": input_neurons,
                        "steps_run": self.snn.time,
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
                },
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return RegionResult(
                region="snn", ok=False,
                error=str(e), elapsed_ms=elapsed,
            )

    # ── 反馈学习 ────────────────────────────────────────────

    def train_from_feedback(
        self,
        signal: NeuralSignal,
        correct_decision: str,
        was_correct: bool,
    ) -> dict:
        """从反馈标注中学习。

        Args:
            signal: 原始信号（重放输入模式）
            correct_decision: 正确决策（如 "auto_approve"）
            was_correct: 原始推理是否正确

        Returns:
            学习结果摘要
        """
        input_neurons = self._encode_signal(signal)
        target_output = self._decision_to_output_neuron(correct_decision)

        if target_output is None:
            return {"ok": False, "reason": f"未知决策类型: {correct_decision}"}

        self._stats["training_count"] += 1

        # 无论正确与否都训练，但权重不同
        eta = 0.05 if was_correct else 0.02
        auto_create = was_correct  # 正确时允许突触发生

        # 两阶段训练：输入 → 奖励 → STDP
        for _ in range(5):
            self.snn.inject_pattern(input_neurons, 1.5)
            self.snn.step()
            self.snn.inject_input(target_output, 2.0)
            outputs = self.snn.step()
            if outputs.get(target_output, False):
                before = sum(
                    1 for src in self.snn.out_edges
                    for c in self.snn.out_edges[src].values()
                    if c.weight > 0.1
                )
                self.snn._reward_modulated_strengthen(
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
                break

        # 反向惩罚：错误决策的输出神经元被抑制
        if not was_correct:
            original_decision = self._stats.get("last_decision", "")
            penalty_output = self._decision_to_output_neuron(original_decision)
            if penalty_output is not None and penalty_output != target_output:
                # 衰减连接到错误输出的权重
                for src in list(self.snn.out_edges.keys()):
                    if penalty_output in self.snn.out_edges[src]:
                        conn = self.snn.out_edges[src][penalty_output]
                        conn.weight = max(0, conn.weight * 0.8)
                        self._stats["edges_strengthened"] += 1

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
            "edges_added": 0, "edges_strengthened": 0,
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

snn_region = SNNRegion()
