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

    # ── 编码/解码 ────────────────────────────────────────────

    def _encode_signal(self, signal: NeuralSignal) -> List[int]:
        """将 NeuralSignal 编码为 SNN 输入神经元列表。"""
        neurons: List[int] = []
        sig_type = (signal.type or "").lower()
        nid = _SIGNAL_TO_NEURON.get(sig_type)
        if nid is not None:
            neurons.append(nid)

        # 紧急度编码
        u_neuron = _urgency_neuron(signal.urgency)
        if u_neuron is not None:
            neurons.append(u_neuron)

        # 如果信号类型未映射，用 hash 分桶到输入神经元
        if not neurons:
            if sig_type:
                bucket = hash(sig_type) % 11
                neurons.append(bucket)

        return neurons or [10]  # 默认 noise

    def _decode_output(self, outputs: Dict[int, bool],
                        active: List[int]) -> Optional[CognitionResult]:
        """将 SNN 输出解码为 CognitionResult。"""
        # 找出激活的输出神经元，按权重选最强
        fired_outputs = [(nid, True) for nid, v in outputs.items() if v]
        if not fired_outputs:
            return None

        # 取激活的输出对应决策（如有多个，取第一个——后续可加权）
        for nid, _ in fired_outputs:
            decision = _OUTPUT_DECISION.get(nid)
            if decision:
                break

        # 置信度 = 输出强度归一化
        confidence = min(1.0, len(fired_outputs) * 0.4 + 0.3)

        return CognitionResult(
            reasoning_level=3,  # 类 L3 级别
            confidence=confidence,
            decision=decision,
            reasoning=f"SNN 脉冲推理: 激活神经元={active[:10]}, 输出={fired_outputs}",
            actions=[Action(type=decision, reason="SNN 脉冲神经网络推理")],
            memory_updates={"snn_active": active, "snn_outputs": outputs},
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
        """
        from services.brain.coordinator import RegionResult

        start = time.time()
        self._stats["reason_calls"] += 1

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
                self._stats["total_fires"] += self.snn.stats()["total_fires"]

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
        """自动保存网络状态。"""
        try:
            self.snn.save(self.save_path)
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
