"""连续调制通道（v4）单元测试。

覆盖：
1. inject_weighted 独立强度注入 + nid=0 边界（经典 `not 0` 陷阱）
2. gain 传播增益：连续强度真正传导到下游
3. 档位槽 gain 中性：AND 门算术不被扰动
4. _normalize_magnitude 对数归一化单调性
5. _continuous_weights 连续强度提取
6. 12 eval 硬约束无回归
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

import pytest

from services.brain.snn import SNN, NeuronType
from services.brain.snn_region import (
    SNNRegion,
    _MAG_NEURON,
    _URGENCY_CONT_NEURON,
    _normalize_magnitude,
)
from models.brain import NeuralSignal


# ── 1. inject_weighted 边界 ────────────────────────────────────
def test_inject_weighted_includes_neuron_zero():
    """nid=0 必须参与注入（`not 0` 陷阱）。"""
    snn = SNN(num_neurons=10)
    snn.inject_weighted({0: 2.0, 5: 1.5})
    assert snn.neurons[0].membrane == 2.0
    assert snn.neurons[5].membrane == 1.5


def test_inject_weighted_skips_nonpositive():
    """负值/零强度跳过（视为抑制或无效）。"""
    snn = SNN(num_neurons=10)
    snn.inject_weighted({0: 0.0, 3: -1.0, 7: 1.0})
    assert snn.neurons[0].membrane == 0.0
    assert snn.neurons[3].membrane == 0.0
    assert snn.neurons[7].membrane == 1.0


def test_inject_weighted_out_of_range_safe():
    """越界神经元安全跳过，不抛异常。"""
    snn = SNN(num_neurons=10)
    snn.inject_weighted({-1: 1.0, 999: 1.0, 4: 1.0})
    assert snn.neurons[4].membrane == 1.0


# ── 2. gain 传播增益 ────────────────────────────────────────────
def test_inject_weighted_sets_gain():
    """连续注入设置传播增益 >1。"""
    snn = SNN(num_neurons=10)
    snn.inject_weighted({0: 2.0})
    assert snn.neurons[0].gain > 1.0


def test_inject_pattern_gain_neutral():
    """档位槽注入保持 gain=1.0（不扰动 AND 门）。"""
    snn = SNN(num_neurons=10)
    snn.inject_pattern([0, 1], 3.0)
    assert snn.neurons[0].gain == 1.0
    assert snn.neurons[1].gain == 1.0


def test_gain_modulates_downstream():
    """核心验证：高注入强度的下游膜电位高于低强度。

    这是"连续调制真正生效"的判据——没有 gain 时两者相同。
    """
    def _propagate(strength: float) -> float:
        snn = SNN(num_neurons=5)
        snn.add_neuron(0, NeuronType.INPUT, threshold=0.5)
        # 阈值 9.9：下游永不放电，膜电位可累计（否则放电即重置）
        snn.add_neuron(1, NeuronType.INPUT, threshold=9.9)
        snn.connect(0, 1, weight=0.4, delay=1)
        snn.inject_weighted({0: strength})
        # delay=1：事件在 t+1 到达，需两步 step（t=1 放电并排队，t=2 事件到达）
        snn.step()
        snn.step()
        return snn.neurons[1].membrane

    low = _propagate(1.0)
    high = _propagate(3.0)
    assert high > low, f"gain 未生效：low={low} high={high}"


def test_reset_state_clears_gain():
    """reset_state 必须重置 gain，防跨推理污染。"""
    snn = SNN(num_neurons=5)
    snn.add_neuron(0, NeuronType.INPUT, threshold=0.5)
    snn.inject_weighted({0: 3.0})
    assert snn.neurons[0].gain > 1.0
    snn.neurons[0].reset_state()
    assert snn.neurons[0].gain == 1.0


# ── 3. 归一化单调性 ─────────────────────────────────────────────
@pytest.mark.parametrize("low,high", [
    (0, 100), (100, 1000), (1000, 10000), (10000, 100000), (100000, 200000),
])
def test_normalize_magnitude_monotonic(low, high):
    """对数归一化严格单调递增。"""
    assert _normalize_magnitude(low) < _normalize_magnitude(high)


def test_normalize_magnitude_bounds():
    """饱和值处应为 1.0，负值/零应为 0.0。"""
    assert _normalize_magnitude(0.0) == 0.0
    assert _normalize_magnitude(-500.0) == 0.0
    assert _normalize_magnitude(1e9) == 1.0  # 饱和


# ── 4. 连续强度提取 ────────────────────────────────────────────
def test_continuous_weights_amount(tmp_path):
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    sig = NeuralSignal(id="1", type="expense",
                       payload={"amount": 80000}, source="test", urgency=50)
    w = region._continuous_weights(sig)
    assert _MAG_NEURON in w and w[_MAG_NEURON] > 0.0


def test_continuous_weights_no_amount(tmp_path):
    """无金额 → mag 通道静默（不伪造连续特征）。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    sig = NeuralSignal(id="2", type="query",
                       payload={"question": "今天天气"}, source="test", urgency=20)
    w = region._continuous_weights(sig)
    assert _MAG_NEURON not in w


def test_continuous_weights_urgency(tmp_path):
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    sig = NeuralSignal(id="3", type="expense", payload={"amount": 500},
                       source="test", urgency=95)
    w = region._continuous_weights(sig)
    assert _URGENCY_CONT_NEURON in w
    assert w[_URGENCY_CONT_NEURON] > 1.0


# ── 5. 12 eval 硬约束 ─────────────────────────────────────────
CASES = [
    ("expense", {"amount": 88000, "category": "equipment"}, 90, "escalate"),
    ("expense", {"amount": 500, "category": "office"}, 50, "auto_approve"),
    ("expense", {"amount": 35000, "category": "travel"}, 70, "escalate"),
    ("expense", {"amount": 800, "category": "meals"}, 40, "auto_approve"),
    ("user_request", {"question": "hello"}, 30, "chat"),
    ("user_request", {"question": "cancel order #12345"}, 60, "escalate"),
    ("approval_pending", {"amount": 15000, "category": "services"}, 80, "escalate"),
    ("approval_pending", {"amount": 500, "category": "consumables"}, 30, "auto_approve"),
    ("threshold_breach", {"risk_level": "critical"}, 95, "escalate"),
    ("threshold_breach", {"risk_level": "low"}, 20, "auto_approve"),
    ("approval_pending", {"amount": 300, "status": "pending"}, 60, "flag"),
    ("approval_pending", {"amount": 80000, "status": "pending"}, 90, "escalate"),
]


def test_twelve_eval_no_regression(tmp_path):
    """连续通道启用后，12 场景硬约束必须保持 12/12。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    async def _run():
        correct = 0
        for i, (st, pl, ug, exp) in enumerate(CASES):
            sig = NeuralSignal(id=str(i), type=st, payload=pl, source="eval", urgency=ug)
            r = await region.reason(sig, {}, None)
            dec = r.result.decision if r.result else None
            if dec == exp:
                correct += 1
        return correct

    import asyncio
    correct = asyncio.run(_run())
    assert correct == 12, f"回归失败：{correct}/12"


# ── 6. 档位内连续差异可观测 ────────────────────────────────────
def test_continuous_modulation_observable(tmp_path):
    """同档位不同金额，中继层膜电位必须单调递增。

    若此处恒等，说明连续强度在传播中被丢弃（二元退化）。
    """
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    peaks = []
    for amt in (100, 500, 900):
        sig = NeuralSignal(id=str(amt), type="expense",
                            payload={"amount": amt}, source="eval", urgency=40)
        inps = region._encode_signal(sig)
        cw = region._continuous_weights(sig)
        region.snn.enable_hebbian = False
        region.snn.reset_learning_state()
        for nid in inps:
            region.snn.neurons[nid].membrane += 3.2
            region.snn.neurons[nid].gain = 1.0
        region.snn.inject_weighted(cw)
        peak = 0.0
        for _ in range(3):
            region.snn.step()
            for i in range(6):
                peak = max(peak, region.snn.neurons[210 + i].membrane)
        peaks.append(peak)
    assert peaks[0] < peaks[2], (
        f"连续调制未传导：{peaks}（应单调递增，否则脉冲模型退化为二元）"
    )
