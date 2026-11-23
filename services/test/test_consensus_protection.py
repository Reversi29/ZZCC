"""意识容量槽 + 共识保护测试。

场景 1：rule+SNN 共识 auto_approve，单个 LLM 带真推理 need_info（补信息请求）
不应覆盖多脑区共识（共识保护）。
场景 2：无共识（agreement_count=1）时，need_info 按原 weight 条件可覆盖。
场景 3：意识容量槽截断低加权分脑区（shadow 被截，核心三脑区保留）。
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

from services.brain.coordinator import RegionCoordinator  # noqa: E402
from models.brain import CognitionResult, NeuralSignal  # noqa: E402


def _sig():
    return NeuralSignal(type="expense", payload={"amount": 500})


def _make_region(decision, confidence, reasoning="reasoning"):
    return CognitionResult(
        decision=decision,
        confidence=confidence,
        reasoning_level=3,
        reasoning=reasoning,
    )


def test_need_info_not_override_consensus():
    """LLM 带真推理 need_info 不应覆盖 rule+SNN 共识 auto_approve。"""
    coord = RegionCoordinator()

    async def rule_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.90, "expense.small_auto_approve")

    async def snn_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.90, "SNN auto_approve")

    async def llm_fn(signal, context, budget=None):
        # LLM 带完整推理的 need_info（要求补字段），weight 0.40
        return _make_region(
            "need_info", 0.70,
            "缺少申请人、部门、用途等字段，无法核验真实性，应先补全信息")

    coord.register("rule", rule_fn, weight=0.80)
    coord.register("snn", snn_fn, weight=0.55)
    coord.register("llm", llm_fn, weight=0.40)

    result = asyncio.run(coord.run(_sig(), {}))

    # 共识保护：rule+SNN 共识（agreement=2）应保持 auto_approve
    assert result.decision == "auto_approve", (
        f"共识保护应保持 auto_approve，实际 {result.decision}"
    )


def test_need_info_override_when_no_consensus():
    """无共识（仅单个脑区）时，need_info 仍按原 weight 条件可覆盖。"""
    coord = RegionCoordinator()

    async def rule_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.90, "expense.small_auto_approve")

    async def llm_fn(signal, context, budget=None):
        return _make_region(
            "need_info", 0.70,
            "缺少申请人、部门等字段，应先补全信息")

    coord.register("rule", rule_fn, weight=0.80)
    coord.register("llm", llm_fn, weight=0.40)

    result = asyncio.run(coord.run(_sig(), {}))

    # 无共识：need_info（0.40 >= 0.8*0.5=0.40）可覆盖单个 rule
    assert result.decision == "need_info", (
        f"无共识时 need_info 应可覆盖，实际 {result.decision}"
    )


def test_focus_slot_truncates_low_weight_shadow():
    """意识容量槽 FOCUS_SLOT_K=3：截断低加权分 shadow，保留核心三脑区。"""
    coord = RegionCoordinator()

    async def rule_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.90)

    async def snn_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.90)

    async def llm_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.85)

    async def shadow_fn(signal, context, budget=None):
        # shadow 低加权分（0.30），会被截断
        return _make_region("escalate", 0.535)

    coord.register("rule", rule_fn, weight=0.80)
    coord.register("snn", snn_fn, weight=0.55)
    coord.register("llm", llm_fn, weight=0.40)
    coord.register("shadow:snn_aux", shadow_fn, weight=0.30)

    result = asyncio.run(coord.run(_sig(), {}))

    # 截断后核心三脑区一致 auto_approve，shadow 不参与
    assert result.decision == "auto_approve", (
        f"截断 shadow 后应保持 auto_approve，实际 {result.decision}"
    )
