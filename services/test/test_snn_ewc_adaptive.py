"""EWC 固化参数随 readiness 自适应测试

对应设计:学生未成熟 → 强固化(保护教师蒸馏成果,遗忘慢);
学生成熟 → 弱固化(保留可塑,遗忘快)。readiness 高 → alpha 低/decay 快,反之相反。

只测 snn.py 的 adapt_ewc_by_readiness + 单调性 + 持久化;
train_from_feedback 的挂钩不测(需完整网络与训练链路)。
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

# 隔离配置目录，不碰生产
os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

import pytest

from services.brain.snn import SNN


def _new_net() -> SNN:
    net = SNN(num_neurons=20)
    return net


# ── 单调性 ────────────────────────────────────────────────

def test_alpha_monotonic_decreasing_with_readiness():
    """readiness 越高 → ewc_alpha 越低(弱固化,保留可塑)"""
    net = _new_net()
    a_low = net.adapt_ewc_by_readiness(0.0)["ewc_alpha"]
    a_mid = net.adapt_ewc_by_readiness(0.5)["ewc_alpha"]
    a_high = net.adapt_ewc_by_readiness(1.0)["ewc_alpha"]
    assert a_low > a_mid > a_high
    assert a_low == pytest.approx(net.ewc_alpha_hi, abs=1e-6)
    assert a_high == pytest.approx(net.ewc_alpha_lo, abs=1e-6)


def test_decay_monotonic_decreasing_with_readiness():
    """readiness 越高 → decay 系数越小(遗忘越快,稳态重要性低)"""
    net = _new_net()
    d_low = net.adapt_ewc_by_readiness(0.0)["ewc_importance_decay"]
    d_mid = net.adapt_ewc_by_readiness(0.5)["ewc_importance_decay"]
    d_high = net.adapt_ewc_by_readiness(1.0)["ewc_importance_decay"]
    # decay 系数越大 = 遗忘越慢; 未成熟端(强固化)0.998 > 成熟端(弱固化)0.990
    assert d_low > d_mid > d_high
    assert d_low == pytest.approx(net.ewc_decay_slow, abs=1e-9)
    assert d_high == pytest.approx(net.ewc_decay_fast, abs=1e-9)


def test_steady_state_importance_low_at_high_readiness():
    """成熟(高 readiness)稳态重要性应低于未成熟(强遗忘)"""
    # 稳态 = 每次 +0.01, 乘 decay → 平衡点 = 0.01/(1-decay)
    net = _new_net()
    net.adapt_ewc_by_readiness(1.0)
    steady_fast = 0.01 / (1.0 - net.ewc_importance_decay)
    net.adapt_ewc_by_readiness(0.0)
    steady_slow = 0.01 / (1.0 - net.ewc_importance_decay)
    assert steady_fast < steady_slow


# ── 边界与鲁棒 ────────────────────────────────────────────

def test_score_clamped_out_of_range():
    """超范围 readiness 截断到 [0,1]"""
    net = _new_net()
    r_over = net.adapt_ewc_by_readiness(5.0)
    assert r_over["readiness_score"] == 1.0
    assert r_over["ewc_alpha"] == pytest.approx(net.ewc_alpha_lo, abs=1e-6)
    r_under = net.adapt_ewc_by_readiness(-2.0)
    assert r_under["readiness_score"] == 0.0
    assert r_under["ewc_alpha"] == pytest.approx(net.ewc_alpha_hi, abs=1e-6)


def test_default_alpha_is_instance_attr_and_matches_class():
    """EWC_ALPHA 类属性保留为默认,实例属性 ewc_alpha 初始等于它"""
    net = _new_net()
    assert isinstance(net.ewc_alpha, float)
    assert net.ewc_alpha == pytest.approx(net.EWC_ALPHA, abs=1e-9)
    assert net.ewc_importance_decay == pytest.approx(net.EWC_IMPORTANCE_DECAY, abs=1e-9)


# ── 对学习乘数的实际影响 ──────────────────────────────────

def test_multiplier_differs_by_readiness():
    """同一重要性下,未成熟保护强(乘数小),成熟保护弱(乘数大)"""
    net = _new_net()
    net._ewc_importance[(0, 1)] = 1.0

    net.adapt_ewc_by_readiness(0.0)   # 未成熟: alpha=100
    mult_unmature = net._get_ewc_multiplier(0, 1)

    net.adapt_ewc_by_readiness(1.0)   # 成熟: alpha=10
    mult_mature = net._get_ewc_multiplier(0, 1)

    assert mult_unmature < mult_mature  # 未成熟学得更慢(强保护)


# ── 持久化 ────────────────────────────────────────────────

def test_ewc_params_roundtrip_persistence():
    """EWC 参数持久化后 from_dict 完整恢复"""
    td = tempfile.mkdtemp()
    path = os.path.join(td, "net.json")

    net = _new_net()
    net.adapt_ewc_by_readiness(0.7)
    net.ewc_importance_cap = 8.0
    net.ewc_alpha_hi = 90.0
    net.ewc_alpha_lo = 20.0
    net.ewc_decay_slow = 0.995
    net.ewc_decay_fast = 0.985
    net.save(path)

    loaded = SNN.load(path)
    assert loaded.ewc_alpha == pytest.approx(net.ewc_alpha, abs=1e-6)
    assert loaded.ewc_importance_decay == pytest.approx(net.ewc_importance_decay, abs=1e-9)
    assert loaded.ewc_importance_cap == pytest.approx(net.ewc_importance_cap, abs=1e-9)
    assert loaded.ewc_alpha_hi == pytest.approx(net.ewc_alpha_hi, abs=1e-9)
    assert loaded.ewc_alpha_lo == pytest.approx(net.ewc_alpha_lo, abs=1e-9)
    assert loaded.ewc_decay_slow == pytest.approx(net.ewc_decay_slow, abs=1e-9)
    assert loaded.ewc_decay_fast == pytest.approx(net.ewc_decay_fast, abs=1e-9)


def test_from_dict_backward_compat_missing_keys():
    """旧文件无 EWC 参数键时回落到默认值,不抛异常"""
    net = _new_net()
    data = net.to_dict()
    for k in ("ewc_alpha", "ewc_importance_decay", "ewc_importance_cap",
              "ewc_adaptive", "ewc_alpha_hi", "ewc_alpha_lo",
              "ewc_decay_slow", "ewc_decay_fast"):
        data.pop(k, None)
    loaded = SNN.from_dict(data)
    assert loaded.ewc_alpha == pytest.approx(net.EWC_ALPHA, abs=1e-9)
    assert loaded.ewc_importance_decay == pytest.approx(net.EWC_IMPORTANCE_DECAY, abs=1e-9)
    assert loaded.ewc_alpha_hi == pytest.approx(net.ewc_alpha_hi, abs=1e-9)


# ── 门控 ──────────────────────────────────────────────────

def test_ewc_adaptive_default_from_env(monkeypatch):
    """BRAIN_EWC_ADAPTIVE 控制门控,默认关闭"""
    monkeypatch.delenv("BRAIN_EWC_ADAPTIVE", raising=False)
    assert SNN().ewc_adaptive is False
    monkeypatch.setenv("BRAIN_EWC_ADAPTIVE", "1")
    assert SNN().ewc_adaptive is True