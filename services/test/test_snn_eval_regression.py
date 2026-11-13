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


def _run(region):
    """同步包装 eval_cases.run（内部已用 asyncio.run）。"""
    return _run_inner(region)


def _run_inner(region):
    from eval_cases import run
    return run(region)
