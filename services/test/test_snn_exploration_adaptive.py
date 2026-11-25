"""探索元参数随成熟度自适应测试

写死参数盘点第二组。EXPLORATION_DECAY(0.95) / EXPLORATION_BOOST(0.3) 原为
类属性, _adjust_exploration_rate 内 0.02/0.5 上下限原为硬编码字面量——
连 to_dict 都没持久化, 是真正的'写死'。

关键设计约束: 防自反馈。explore_converged 本身就是 readiness 的分量(权重 0.15),
若用完整 readiness 驱动探索率, 会形成"降探索→探索收敛分变高→readiness 变高→
进一步压探索"的正反馈——学生刷自己的指标。故本组的驱动信号(成熟度)由调用方
显式提供, 必须排除探索分量; 本测试直接验证该方法对 maturity 的单调性,
不依赖 readiness 合成。
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
    return SNN(num_neurons=20)


# ── 单调性: 成熟度越高, 探索越收敛 ─────────────────────────

def test_floor_monotonic_decreasing_with_maturity():
    """成熟度越高 → 探索下限越低(竞争收敛彻底)"""
    net = _new_net()
    f_low = net.adapt_exploration_by_maturity(0.0)["exploration_floor"]
    f_mid = net.adapt_exploration_by_maturity(0.5)["exploration_floor"]
    f_high = net.adapt_exploration_by_maturity(1.0)["exploration_floor"]
    assert f_low > f_mid > f_high
    assert f_low == pytest.approx(net.exploration_floor_hi, abs=1e-9)
    assert f_high == pytest.approx(net.exploration_floor_lo, abs=1e-9)


def test_decay_monotonic_increasing_with_maturity():
    """成熟度越高 → decay 系数越大(收敛越快, 稳定性不被小幅波动反复重置)"""
    net = _new_net()
    d_low = net.adapt_exploration_by_maturity(0.0)["exploration_decay"]
    d_high = net.adapt_exploration_by_maturity(1.0)["exploration_decay"]
    assert d_low < d_high
    assert d_low == pytest.approx(net.exploration_decay_hi, abs=1e-9)
    assert d_high == pytest.approx(net.exploration_decay_lo, abs=1e-9)


def test_boost_monotonic_decreasing_with_maturity():
    """成熟度越高 → 边界探测强度越小(精准探测, 避免单次错误大幅扰动)"""
    net = _new_net()
    b_low = net.adapt_exploration_by_maturity(0.0)["exploration_boost"]
    b_high = net.adapt_exploration_by_maturity(1.0)["exploration_boost"]
    assert b_low > b_high
    assert b_low == pytest.approx(net.exploration_boost_hi, abs=1e-9)
    assert b_high == pytest.approx(net.exploration_boost_lo, abs=1e-9)


# ── 边界与鲁棒 ────────────────────────────────────────────

def test_maturity_clamped_out_of_range():
    net = _new_net()
    assert net.adapt_exploration_by_maturity(9.0)["maturity"] == 1.0
    assert net.adapt_exploration_by_maturity(-1.0)["maturity"] == 0.0


def test_defaults_match_class_attributes():
    """类属性保留为默认值, 实例属性初始等于它(向后兼容)"""
    net = _new_net()
    assert net.exploration_decay == pytest.approx(net.EXPLORATION_DECAY, abs=1e-9)
    assert net.exploration_boost == pytest.approx(net.EXPLORATION_BOOST, abs=1e-9)
    # 上下限原为硬编码字面量, 现在实例属性, 值保持一致
    assert net.exploration_floor == 0.02
    assert net.exploration_ceil == 0.5


# ── 实例属性真正参与调节(防退化为死代码) ──────────────────

def test_adapted_params_actually_used_in_adjust():
    """验证自适应后的参数真的驱动 _adjust_exploration_rate 行为"""
    net = _new_net()
    net._exploration_rate = 0.20

    # 成熟端: decay=0.98 → 收敛快, 单次正确后探索率降幅小
    net.adapt_exploration_by_maturity(1.0)
    net._adjust_exploration_rate(decision_was_correct=True)
    mature_after = net._exploration_rate

    # 未成熟端: decay=0.90 → 单次正确后降幅大
    net2 = _new_net()
    net2._exploration_rate = 0.20
    net2.adapt_exploration_by_maturity(0.0)
    net2._adjust_exploration_rate(decision_was_correct=True)
    immature_after = net2._exploration_rate

    assert mature_after > immature_after  # 成熟端收敛快, 保留更多探索率


def test_boost_actually_used_on_error():
    """成熟端探测强度小, 错误回升幅度小"""
    net = _new_net()
    net._exploration_rate = 0.02
    net.adapt_exploration_by_maturity(1.0)
    net._adjust_exploration_rate(decision_was_correct=False)
    mature_after = net._exploration_rate

    net2 = _new_net()
    net2._exploration_rate = 0.02
    net2.adapt_exploration_by_maturity(0.0)
    net2._adjust_exploration_rate(decision_was_correct=False)
    immature_after = net2._exploration_rate

    assert mature_after < immature_after  # 成熟端错误恢复更克制


def test_ceil_respected_after_adaptation():
    """上限(实例属性)仍生效, 不被自适应破坏"""
    net = _new_net()
    net.adapt_exploration_by_maturity(0.0)
    net._exploration_rate = 0.49
    net._adjust_exploration_rate(decision_was_correct=False)
    assert net._exploration_rate <= net.exploration_ceil + 1e-9


# ── 持久化 ────────────────────────────────────────────────

def test_exploration_params_roundtrip_persistence():
    td = tempfile.mkdtemp()
    path = os.path.join(td, "net.json")

    net = _new_net()
    net.adapt_exploration_by_maturity(0.6)
    net.exploration_floor_hi = 0.08
    net.exploration_floor_lo = 0.01
    net.exploration_decay_lo = 0.99
    net.exploration_boost_lo = 0.10
    net.save(path)

    loaded = SNN.load(path)
    assert loaded.exploration_decay == pytest.approx(net.exploration_decay, abs=1e-9)
    assert loaded.exploration_boost == pytest.approx(net.exploration_boost, abs=1e-9)
    assert loaded.exploration_floor == pytest.approx(net.exploration_floor, abs=1e-9)
    assert loaded.exploration_ceil == pytest.approx(net.exploration_ceil, abs=1e-9)
    assert loaded.exploration_floor_hi == pytest.approx(net.exploration_floor_hi, abs=1e-9)
    assert loaded.exploration_floor_lo == pytest.approx(net.exploration_floor_lo, abs=1e-9)
    assert loaded.exploration_decay_lo == pytest.approx(net.exploration_decay_lo, abs=1e-9)
    assert loaded.exploration_boost_lo == pytest.approx(net.exploration_boost_lo, abs=1e-9)


def test_from_dict_backward_compat_missing_keys():
    net = _new_net()
    data = net.to_dict()
    for k in ("exploration_decay", "exploration_boost", "exploration_floor",
              "exploration_ceil", "exploration_adaptive", "exploration_floor_hi",
              "exploration_floor_lo", "exploration_decay_hi",
              "exploration_decay_lo", "exploration_boost_hi",
              "exploration_boost_lo"):
        data.pop(k, None)
    loaded = SNN.from_dict(data)
    assert loaded.exploration_decay == pytest.approx(net.EXPLORATION_DECAY, abs=1e-9)
    assert loaded.exploration_boost == pytest.approx(net.EXPLORATION_BOOST, abs=1e-9)
    assert loaded.exploration_floor == 0.02
    assert loaded.exploration_ceil == 0.5


# ── 门控 ──────────────────────────────────────────────────

def test_exploration_adaptive_default_from_env(monkeypatch):
    monkeypatch.delenv("BRAIN_EXPLORATION_ADAPTIVE", raising=False)
    assert SNN().exploration_adaptive is False
    monkeypatch.setenv("BRAIN_EXPLORATION_ADAPTIVE", "1")
    assert SNN().exploration_adaptive is True


# ── 防自反馈: 驱动信号不得含探索分量 ───────────────────────

def test_maturity_formula_excludes_explore_component():
    """核心约束: 成熟度信号排除 explore_converged。

    直接断言 snn_region 训练挂钩里构造 maturity 的代码不引用
    explore_converged——防'降探索→探索分变高→readiness 变高→进一步压探索'
    的正反馈(学生刷自己的指标)。
    """
    import inspect
    from services.brain import snn_region as mod
    src = inspect.getsource(mod.SNNRegion.train_from_feedback)
    maturity_block = src[src.index("maturity = ("):src.index(")", src.index("maturity = (") + 500)]
    assert "explore_converged" not in maturity_block
    assert "teacher_aligned" in maturity_block
    assert "self_consistent" in maturity_block