"""LLM 抖动治理测试：LLM 单方误判 escalate 不应覆盖 rule+SNN 共识 auto_approve。

根因：_integrate 冲突仲裁原用纯权重 `weight >= top_weight * 0.5`，
LLM（0.40）恰好达 rule（0.80）×0.5，LLM 误判 escalate（conf 0.7）
可覆盖 rule+SNN 共识 auto_approve。修复后要求安全侧加权分
（confidence×weight）达 top 的 50% 且置信度 >=0.75。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

from services.brain.coordinator import RegionCoordinator  # noqa: E402
from models.brain import CognitionResult, NeuralSignal  # noqa: E402


def _sig():
    return NeuralSignal(type="expense", payload={"amount": 500})


def _make_region(decision, confidence):
    return CognitionResult(
        decision=decision,
        confidence=confidence,
        reasoning_level=3,
        reasoning=f"{decision} reasoning",
    )


def test_llm_low_conf_escalate_not_override_consensus():
    """LLM 单方低置信 escalate 不应覆盖 rule+SNN 共识 auto_approve。"""
    coord = RegionCoordinator()

    async def rule_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.90)

    async def snn_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.90)

    async def llm_fn(signal, context, budget=None):
        # LLM 误判 escalate（conf 0.7，限流/温度抖动）
        return _make_region("escalate", 0.70)

    coord.register("rule", rule_fn, weight=0.80)
    coord.register("snn", snn_fn, weight=0.55)
    coord.register("llm", llm_fn, weight=0.40)

    import asyncio
    result = asyncio.run(coord.run(_sig(), {}))

    # LLM 低置信 escalate 不应覆盖（加权分 0.28 < 0.72×0.5）
    assert result.decision == "auto_approve", (
        f"应保持 auto_approve 共识，实际 {result.decision}"
    )


def test_high_conf_safe_override():
    """高置信度安全侧决策仍可覆盖（保留仲裁能力）。"""
    coord = RegionCoordinator()

    async def rule_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.85)

    async def snn_fn(signal, context, budget=None):
        return _make_region("auto_approve", 0.85)

    async def llm_fn(signal, context, budget=None):
        # LLM 高置信 escalate（0.9），加权分 0.36 >= 0.68×0.5=0.34
        return _make_region("escalate", 0.90)

    coord.register("rule", rule_fn, weight=0.80)
    coord.register("snn", snn_fn, weight=0.55)
    coord.register("llm", llm_fn, weight=0.40)

    import asyncio
    result = asyncio.run(coord.run(_sig(), {}))

    # LLM 高置信 escalate 加权分足够 → 应仲裁覆盖
    assert result.decision == "escalate", (
        f"高置信 escalate 应仲裁，实际 {result.decision}"
    )
