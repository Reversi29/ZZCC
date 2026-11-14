"""need_info 污染治理端到端测试。

构造被污染的 need_info 槽（强入边），验证：
1. rejection 完整字段信号 → reject 胜出（惩罚后不被 need_info 碾压）
2. 无概念向量正常场景不受影响
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.brain.snn_region import (  # noqa: E402
    SNNRegion, _CONCEPT_NEURON_BASE, _CONCEPT_RELAY_BASE,
)
from models.brain import NeuralSignal  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _pollute_need_info(region):
    """模拟 need_info 槽被历史反馈污染（强入边）。"""
    ni = region.output_registry.register("need_info")
    # 让多个前驱强连到 need_info（模拟污染）
    region._ensure_concept_channel("rejection")
    nid = region.concept_registry.get("rejection")
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    if ni not in region.snn.out_edges.get(relay, {}):
        region.snn.connect(relay, ni, weight=1.5, delay=1)
    # 连续中继也污染 need_info
    for src in (218, 221):
        if src < region.snn.num_neurons:
            region.snn.connect(src, ni, weight=1.8, delay=1)
    return ni


def test_rejection_full_fields_not_hijacked(tmp_path):
    """完整字段 rejection → reject（need_info 惩罚后不被碾压）。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    _pollute_need_info(region)
    # 完整字段 rejection 信号
    sig = NeuralSignal(
        id="r", type="user_request",
        payload={
            "_concept_vector": {"rejection": 0.8},
            "text": "驳回申请 APP-2024-001 因材料不全",
            "application_id": "APP-2024-001",
            "rejection_reason": "材料不全",
        },
        source="test", urgency=50,
    )
    r = _run(region.reason(sig, {}, None))
    assert r.result is not None, "SNN 无输出"
    # 预训练种子应引导 reject，need_info 惩罚后不应碾压
    assert r.result.decision == "reject", f"rejection 被 need_info 劫持: {r.result.decision}"


def test_normal_scenario_unaffected(tmp_path):
    """无概念向量正常场景（expense 500）不受 need_info 惩罚影响。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    sig = NeuralSignal(id="e", type="expense", payload={"amount": 500}, source="test", urgency=50)
    r = _run(region.reason(sig, {}, None))
    assert r.result is not None
    assert r.result.decision in ("auto_approve", "approve")
