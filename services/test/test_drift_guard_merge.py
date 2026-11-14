"""SNN 漂移护栏软恢复合并逻辑测试（方向 A：软恢复保留 EWC）。

验证 merge_ewc_for_restore：软恢复时基线拓扑 + 漂移网络 EWC 合并，
被固化知识不因回退基线而丢失。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import json  # noqa: E402
import pytest  # noqa: E402
from snn_drift_guard import merge_ewc_for_restore  # noqa: E402


def _baseline():
    return json.dumps({
        "num_neurons": 40,
        "edges": [{"source": 17, "target": 34, "weight": 2.0}],
        "ewc_importance": {"17->34": 5.0, "18->34": 3.0},
    })


def _drift():
    return json.dumps({
        "num_neurons": 233,
        "edges": [{"source": 17, "target": 34, "weight": 3.0}],
        "ewc_importance": {"17->34": 8.0, "20->34": 2.0},
    })


def test_merge_keeps_higher_drift_value():
    """漂移网络的 EWC 值应优先（更高），不被基线覆盖。"""
    merged, n = merge_ewc_for_restore(_baseline(), _drift())
    m = json.loads(merged)
    assert m["ewc_importance"]["17->34"] == 8.0
    assert n == 3  # 17->34, 18->34, 20->34 并集


def test_merge_includes_baseline_only():
    """基线独有但漂移没有的 EWC 应补进来。"""
    merged, n = merge_ewc_for_restore(_baseline(), _drift())
    m = json.loads(merged)
    assert "18->34" in m["ewc_importance"]
    assert "20->34" in m["ewc_importance"]


def test_merge_no_drift_ewc():
    """漂移无 EWC 时，保留基线 EWC。"""
    drift = json.dumps({"num_neurons": 233, "edges": []})
    merged, n = merge_ewc_for_restore(_baseline(), drift)
    m = json.loads(merged)
    assert m["ewc_importance"] == {"17->34": 5.0, "18->34": 3.0}
    assert n == 2


def test_merge_both_empty():
    """双方都无 EWC，返回基线原样。"""
    b = json.dumps({"num_neurons": 40, "edges": []})
    d = json.dumps({"num_neurons": 233, "edges": []})
    merged, n = merge_ewc_for_restore(b, d)
    assert merged == b
    assert n == 0


def test_merge_malformed():
    """JSON 解析失败回退基线原样。"""
    merged, n = merge_ewc_for_restore("not json", _drift())
    assert merged == "not json"
    assert n == 0
