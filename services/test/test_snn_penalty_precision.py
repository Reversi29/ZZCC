"""漂移根因治理：惩罚逻辑精准化测试（方向2）

验证：错误反馈时惩罚只作用于实际放电路径，不全局惩罚。
原逻辑遍历所有 out_edges 惩罚所有指向 penalty_output 的边，
导致 edges_penalized 远超 edges_strengthened，权重净流失。
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

from models.brain import NeuralSignal  # noqa: E402
from services.brain.snn_region import SNNRegion  # noqa: E402


def _make_region():
    return SNNRegion(save_path=tempfile.mkdtemp() + "/s.json")


def _signal():
    return NeuralSignal(
        id="t1", type="expense",
        payload={"amount": 500, "category": "office", "invoice_status": "complete"},
        source="eval", urgency=50,
    )


def test_penalty_only_fires_on_active_path():
    """错误反馈惩罚只作用于放电路径，不惩罚所有指向 penalty_output 的边。"""
    region = _make_region()
    sig = _signal()
    # 先推理建立 last_decision
    import asyncio
    r = asyncio.run(region.reason(sig, {}, None))
    wrong = r.result.decision if r.result else "auto_approve"

    # 记录惩罚前的边数
    penalty_output = region._decision_to_output_neuron(wrong)
    in_edges_before = sum(
        1 for src in region.snn.out_edges
        if penalty_output in region.snn.out_edges[src]
    )

    # 错误反馈：正确决策应为 escalate（纠正）
    res = region.train_from_feedback(sig, "escalate", False, wrong_decision=wrong)

    # 惩罚只统计放电路径，应 ≤ 总入边数（不全局惩罚）
    penalized = res.get("edges_penalized", 0)
    assert penalized <= in_edges_before, (
        f"惩罚数 {penalized} 超过总入边数 {in_edges_before}（不应全局惩罚）"
    )
    # 惩罚应 > 0（有放电路径命中）
    assert penalized > 0, "惩罚应为正（错误反馈应削弱错误路径）"


def test_penalty_preserves_min_weight():
    """惩罚保留最小权重 0.5，不磨没关键路径。"""
    region = _make_region()
    sig = _signal()
    import asyncio
    r = asyncio.run(region.reason(sig, {}, None))
    wrong = r.result.decision if r.result else "auto_approve"
    penalty_output = region._decision_to_output_neuron(wrong)

    # 记录惩罚前各边权重
    before = {
        (src, tgt): c.weight
        for src, conns in region.snn.out_edges.items()
        for tgt, c in conns.items()
        if tgt == penalty_output
    }

    region.train_from_feedback(sig, "escalate", False, wrong_decision=wrong)
    for (src, tgt), old_w in before.items():
        conn = region.snn.out_edges[src][tgt]
        if old_w > 0:
            # 兴奋性边：惩罚后不应低于 0.5
            assert conn.weight >= 0.5, (
                f"兴奋性边 {src}→{tgt} 权重低于 0.5 下限: {conn.weight}"
            )
        else:
            # 抑制性边（负权重）：惩罚不应碰（保持负值）
            assert conn.weight < 0, (
                f"抑制性边 {src}→{tgt} 被错误提升为兴奋: {conn.weight}"
            )


def test_penalty_count_matches_fired_path():
    """惩罚计数等于实际放电路径数（非全局边数）。"""
    region = _make_region()
    sig = _signal()
    import asyncio
    r = asyncio.run(region.reason(sig, {}, None))
    wrong = r.result.decision if r.result else "auto_approve"
    penalty_output = region._decision_to_output_neuron(wrong)

    # 手动模拟放电路径的源数
    region.snn.reset_learning_state()
    input_neurons = region._encode_signal(sig)
    strength = 2.0 + (sig.urgency / 100.0) * 3.0
    region.snn.inject_pattern(input_neurons, strength)
    region.snn.step()
    region.snn.step()
    fired_sources = {
        n.id for n in region.snn.neurons
        if n.last_fire_time >= 0 and n.id != penalty_output
    }
    expected = sum(
        1 for src in fired_sources
        if penalty_output in region.snn.out_edges.get(src, {})
    )

    res = region.train_from_feedback(sig, "escalate", False, wrong_decision=wrong)
    penalized = res.get("edges_penalized", 0)
    # 惩罚数应等于放电路径命中数（或回退到直接入边，此时 ≤ 总入边）
    if expected > 0:
        assert penalized == expected, (
            f"惩罚数 {penalized} 应等于放电路径命中数 {expected}"
        )
