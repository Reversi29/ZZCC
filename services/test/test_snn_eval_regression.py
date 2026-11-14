"""SNN 决策 eval 回归测试

权威 12 用例（见 tools/eval_cases.py）。干净拓扑应 12/12；
生产网络漂移会掉分，此测试作为漂移红灯。

运行：
  pytest test/test_snn_eval_regression.py -v
"""
import os
import sys
import tempfile

import pytest

# 对齐既有测试：services/interface 为导入根（models/ 与 services/ 均在其下）
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

# 权威用例库
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from eval_cases import EVAL_CASES  # noqa: E402


@pytest.mark.snn_regression
def test_clean_topology_full_pass():
    """干净拓扑（create_default）必须 12/12——这是基线判据。"""
    from services.brain.snn_region import SNNRegion

    region = SNNRegion(save_path=tempfile.mkdtemp() + "/s.json")
    ok, fails = _run(region)
    assert not fails, (
        f"干净拓扑 eval 掉分：{ok}/{len(EVAL_CASES)}\n"
        f"失败：{fails}"
    )


@pytest.mark.snn_regression
def test_eval_cases_schema():
    """用例库结构稳定——防止权威定义被误改。"""
    assert len(EVAL_CASES) == 12
    for t, pl, urg, exp in EVAL_CASES:
        assert isinstance(t, str) and t
        assert isinstance(pl, dict)
        assert 0 <= urg <= 100
        assert exp in {
            "auto_approve", "reject", "escalate", "flag",
            "chat", "need_info", "no_action",
        }


@pytest.mark.snn_regression
def test_clean_topology_stability():
    """干净拓扑 eval 必须稳定——连续 3 次全 12/12（防边界翻转）。

    边界用例（如 approval_pending/30 的 escalate vs auto_approve 分数差
    仅 0.002）若权重微扰导致翻转，说明拓扑不稳健，需治理而非靠运气。
    """
    import tempfile
    from services.brain.snn_region import SNNRegion
    for i in range(3):
        region = SNNRegion(save_path=tempfile.mkdtemp() + f"/s{i}.json")
        ok, fails = _run(region)
        assert not fails, (
            f"干净拓扑 eval 第 {i + 1} 次掉分：{ok}/{len(EVAL_CASES)}\n"
            f"失败：{fails}"
        )


def test_clean_topology_stability_after_feedback():
    """方向1（边界优化）：错误反馈累积后 eval 仍 12/12（防漂移期边界平局）。

    惩罚精准化（方向2）前，错误反馈只惩罚不加强（penalized 420 vs
    strengthened 0），权重净流失导致 #8 approval_pending/30 的
    escalate vs auto_approve 差 0.002 翻转。惩罚精准化后
    penalized/strengthened=1.00，权重平衡，边界应保持。
    """
    import tempfile
    from services.brain.snn_region import SNNRegion
    from models.brain import NeuralSignal

    region = SNNRegion(save_path=tempfile.mkdtemp() + "/s.json")
    # 连续 20 次错误反馈（模拟漂移期累积训练）
    for i in range(20):
        sig = NeuralSignal(
            id=f"t{i}", type="expense", payload={"amount": 500},
            source="eval", urgency=50,
        )
        r = region._run_reason(sig) if hasattr(region, "_run_reason") else None
        # 直接用 eval_cases 内部 asyncio
        import asyncio

        async def _reason():
            return await region.reason(sig, {}, None)

        r = asyncio.run(_reason())
        wrong = r.result.decision if r.result else "auto_approve"
        region.train_from_feedback(sig, "escalate", False, wrong_decision=wrong)

    ok, fails = _run(region)
    assert not fails, (
        f"错误反馈累积后 eval 掉分：{ok}/{len(EVAL_CASES)}\n失败：{fails}\n"
        "（惩罚精准化应保持权重平衡，边界不应翻转）"
    )


def _run(region):
    """同步包装 eval_cases.run（内部已用 asyncio.run）。"""
    return _run_inner(region)


def _run_inner(region):
    from eval_cases import run
    return run(region)
