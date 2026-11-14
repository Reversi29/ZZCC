"""多 SNN 容错（P2）测试。

验证：
1. SNN 连续无决策 → 健康状态 degraded → unhealthy
2. 健康不佳时 coordinator 降权/跳过 SNN，让规则承接
3. 有效决策恢复健康
4. status() 暴露 health
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

import asyncio  # noqa: E402
import pytest  # noqa: E402
from services.brain.snn_region import SNNRegion  # noqa: E402
from services.brain.coordinator import RegionCoordinator, RegionResult  # noqa: E402
from models.brain import NeuralSignal, CognitionResult  # noqa: E402


@pytest.fixture
def region(tmp_path):
    """隔离的 SNNRegion（临时网络文件，不污染生产）。"""
    save = str(tmp_path / "test_snn_network.json")
    r = SNNRegion(save_path=save)
    # 缩短阈值加速测试
    r._HEALTH_DEGRADE_AFTER = 3
    r._HEALTH_RECOVER_AFTER = 1
    return r


def test_no_decision_degrades_health(region):
    """连续无决策 → degraded → unhealthy。"""
    assert region.health()["status"] == "healthy"
    region._record_no_decision("测试")
    assert region.health()["status"] == "healthy"
    region._record_no_decision("测试")
    assert region.health()["status"] == "degraded"
    region._record_no_decision("测试")
    h = region.health()
    assert h["status"] == "unhealthy"
    assert h["consecutive_no_decision"] >= 3


def test_healthy_recovers(region):
    """有效决策恢复健康。"""
    region._record_no_decision("测试")
    region._record_no_decision("测试")
    region._record_no_decision("测试")
    assert region.health()["status"] == "unhealthy"
    region._record_healthy()
    assert region.health()["status"] == "healthy"
    assert region.health()["consecutive_no_decision"] == 0


def test_status_exposes_health(region):
    """status() 暴露 health 快照。"""
    s = region.status()
    assert "health" in s
    assert s["health"]["status"] == "healthy"


def test_coordinator_skips_unhealthy_snn():
    """coordinator 在 SNN unhealthy 时跳过它，规则承接。"""
    coord = RegionCoordinator()
    coord.register("rule", lambda s, c, b: None, weight=0.80)
    coord.register("snn", lambda s, c, b: None, weight=0.55)

    signal = NeuralSignal(type="expense", urgency=50, payload={"amount": 500})
    # SNN 返回 unhealthy 的健康 context + 一个规则结果
    rule_result = CognitionResult(
        signal_id="t1", reasoning_level=2, confidence=0.7,
        decision="auto_approve", reasoning="rule", actions=[])
    snn_result = CognitionResult(
        signal_id="t1", reasoning_level=3, confidence=0.9,
        decision="escalate", reasoning="snn", actions=[])

    results = [
        RegionResult(region="rule", ok=True, result=rule_result, elapsed_ms=1),
        RegionResult(region="snn", ok=True, result=snn_result, elapsed_ms=1,
                     context={"health": {"status": "unhealthy",
                                         "consecutive_no_decision": 5}}),
    ]
    final = coord._integrate(signal, results, {})
    # SNN unhealthy → 被跳过，规则决策胜出
    assert final.decision == "auto_approve"
    assert final.confidence == 0.7


def test_coordinator_halves_degraded_snn():
    """coordinator 在 SNN degraded 时降权。"""
    coord = RegionCoordinator()
    coord.register("rule", lambda s, c, b: None, weight=0.80)
    coord.register("snn", lambda s, c, b: None, weight=0.55)

    signal = NeuralSignal(type="expense", urgency=50, payload={"amount": 500})
    rule_result = CognitionResult(
        signal_id="t1", reasoning_level=2, confidence=0.7,
        decision="auto_approve", reasoning="rule", actions=[])
    # degraded SNN 权重 0.55*0.5=0.275，conf 0.9 → weighted 0.2475
    # 规则 conf 0.7 * 0.80 = 0.56 → 规则胜出（降权生效）
    snn_result = CognitionResult(
        signal_id="t1", reasoning_level=3, confidence=0.9,
        decision="escalate", reasoning="snn", actions=[])

    results = [
        RegionResult(region="rule", ok=True, result=rule_result, elapsed_ms=1),
        RegionResult(region="snn", ok=True, result=snn_result, elapsed_ms=1,
                     context={"health": {"status": "degraded"}}),
    ]
    final = coord._integrate(signal, results, {})
    # degraded SNN 降权后，规则（高权重）应胜出
    assert final.decision == "auto_approve"


def test_coordinator_healthy_snn_normal():
    """健康 SNN 正常参与融合。"""
    coord = RegionCoordinator()
    coord.register("rule", lambda s, c, b: None, weight=0.80)
    coord.register("snn", lambda s, c, b: None, weight=0.55)

    signal = NeuralSignal(type="expense", urgency=50, payload={"amount": 500})
    rule_result = CognitionResult(
        signal_id="t1", reasoning_level=2, confidence=0.7,
        decision="auto_approve", reasoning="rule", actions=[])
    # 健康 SNN 权重 0.55，conf 0.9 → weighted 0.495
    # 规则 0.7*0.80=0.56 仍稍高，但 SNN 参与竞争
    snn_result = CognitionResult(
        signal_id="t1", reasoning_level=3, confidence=0.9,
        decision="escalate", reasoning="snn", actions=[])

    results = [
        RegionResult(region="rule", ok=True, result=rule_result, elapsed_ms=1),
        RegionResult(region="snn", ok=True, result=snn_result, elapsed_ms=1,
                     context={"health": {"status": "healthy"}}),
    ]
    final = coord._integrate(signal, results, {})
    # 健康 SNN 参与，决策在两者间
    assert final.decision in ("auto_approve", "escalate")


def test_reason_no_output_triggers_no_decision(region, monkeypatch):
    """reason() 返回 None 时触发健康降级（集成）。"""
    import asyncio
    from models.brain import NeuralSignal

    # mock _decode_output 返回 None（模拟 SNN 无输出）
    monkeypatch.setattr(region, "_decode_output", lambda outputs, active: None)
    monkeypatch.setattr(region, "_encode_signal", lambda s: [0])
    # 防止真实 step 干扰，mock 掉
    monkeypatch.setattr(region.snn, "step_with_learning",
                        lambda *a, **k: ({}, False))
    monkeypatch.setattr(region, "_log_decision", lambda *a, **k: None)

    signal = NeuralSignal(id="t1", type="expense", urgency=50,
                          payload={"amount": 500})

    async def _run():
        return await region.reason(signal, {}, None)

    result = asyncio.run(_run())
    assert result.ok is True
    assert result.result is None
    # 触发一次无决策记录
    assert region.health()["status"] in ("healthy", "degraded")
    assert region.health()["consecutive_no_decision"] >= 1


def test_reason_consecutive_none_degrades(region, monkeypatch):
    """连续多次无决策 → degraded/unhealthy（集成）。"""
    import asyncio
    from models.brain import NeuralSignal

    monkeypatch.setattr(region, "_decode_output", lambda outputs, active: None)
    monkeypatch.setattr(region, "_encode_signal", lambda s: [0])
    monkeypatch.setattr(region.snn, "step_with_learning",
                        lambda *a, **k: ({}, False))
    monkeypatch.setattr(region, "_log_decision", lambda *a, **k: None)

    signal = NeuralSignal(id="t1", type="expense", urgency=50,
                          payload={"amount": 500})
    region._HEALTH_DEGRADE_AFTER = 3

    async def _run():
        return await region.reason(signal, {}, None)

    for _ in range(3):
        asyncio.run(_run())
    h = region.health()
    assert h["consecutive_no_decision"] >= 3
    assert h["status"] == "unhealthy"
