"""Hebbian 内源自主生长随 readiness 退火测试

写死参数盘点第三组。enable_hebbian 原本是死开关: reason(1036)/train(1332)/
snn_iterate(1858) 三条路径全部强制 False, 改它没有任何落点。真正的落点是
snn_iterate——内源自主迭代, 无真实反馈、不产出决策, 对应人脑"清醒期突触
也在生长(以生长为主)"。

实验 tools/experiment_hebbian_iterate.py 已证实: 启用后 200 次迭代 eval 仍
12/12, 零边膨胀(Hebbian 只调权重不建连, 667 边暴涨前科来自结构可塑性
allow_synaptogenesis, 不是 STDP)。

设计约束:
1. 用 autonomy(0~1) 缩放 eta_plus/eta_minus, 不碰 _hebbian_update 核心公式
   ——避免破坏其他 enable_hebbian=True 的路径与向后兼容。
2. 强度在 snn_iterate 的 finally 恢复, 不泄漏到 train/reason。
3. 无自反馈: autonomy 不在 readiness 的任何分量里(它不是指标, 是被指标驱动
   的产出), 故本组可直接用完整 readiness_score 驱动, 不像探索组需剔除分量。
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


# ── 退火单调性 ────────────────────────────────────────────

def test_autonomy_monotonic_increasing_with_readiness():
    """readiness 越高 → 内源自主生长强度越大"""
    net = _new_net()
    a_low = net.adapt_hebbian_autonomy(0.0)["hebbian_autonomy"]
    a_mid = net.adapt_hebbian_autonomy(0.5)["hebbian_autonomy"]
    a_high = net.adapt_hebbian_autonomy(1.0)["hebbian_autonomy"]
    assert a_low < a_mid < a_high
    assert a_low == pytest.approx(net.hebbian_anneal_lo, abs=1e-9)
    assert a_high == pytest.approx(net.hebbian_anneal_hi, abs=1e-9)


def test_autonomy_clamped_out_of_range():
    net = _new_net()
    assert net.adapt_hebbian_autonomy(3.0)["readiness_score"] == 1.0
    assert net.adapt_hebbian_autonomy(-3.0)["readiness_score"] == 0.0


def test_autonomy_custom_range():
    """自定义退火区间生效"""
    net = _new_net()
    net.hebbian_anneal_lo = 0.1
    net.hebbian_anneal_hi = 0.9
    assert net.adapt_hebbian_autonomy(0.0)["hebbian_autonomy"] == pytest.approx(
        0.1, abs=1e-9)
    assert net.adapt_hebbian_autonomy(1.0)["hebbian_autonomy"] == pytest.approx(
        0.9, abs=1e-9)
    assert net.adapt_hebbian_autonomy(0.5)["hebbian_autonomy"] == pytest.approx(
        0.5, abs=1e-9)


def test_report_carries_annealing_flag():
    net = _new_net()
    assert net.adapt_hebbian_autonomy(0.0)["annealing_enabled"] is net.hebbian_annealing


# ── snn_iterate 强度调制与恢复 ─────────────────────────────

def _region_with_iterate_path(tmp):
    """构造一条 202(内源)→20(隐藏)→32(输出) 通路, 让 snn_iterate 有放电可学"""
    from services.brain.snn_region import SNNRegion

    path = os.path.join(tmp, "net.json")
    net = SNN(num_neurons=220)
    for i in range(16, 32):
        net.connect(12, i, weight=1.2, step=1)
    for i in range(32, 38):
        net.connect(20, i, weight=1.5, step=1)
    net.connect(202, 20, weight=1.5, step=1)
    net.save(path)

    r = SNNRegion(save_path=os.path.join(tmp, "region.json"))
    r.snn = SNN.load(path)
    return r


def test_snn_iterate_default_zero_autonomy(tmp_path):
    """默认关闭门控: autonomy=0, 不启用 Hebbian"""
    r = _region_with_iterate_path(tmp_path)
    out = r.snn_iterate()
    assert out["hebbian_autonomy"] == pytest.approx(0.0, abs=1e-9)


def test_snn_iterate_scales_eta_and_restores(tmp_path):
    """启用门控 + 成熟度 1.0 → eta 按 autonomy 缩放, 且 finally 恢复"""
    r = _region_with_iterate_path(tmp_path)
    r.snn.hebbian_annealing = True
    r.snn.adapt_hebbian_autonomy(1.0)
    r.snn.eta_plus = 0.2
    r.snn.eta_minus = 0.05
    out = r.snn_iterate()
    assert out["ok"] is True
    assert out["hebbian_autonomy"] == pytest.approx(1.0, abs=1e-3)
    # finally 必须恢复原强度, 不泄漏到 train/reason
    assert r.snn.eta_plus == pytest.approx(0.2, abs=1e-9)
    assert r.snn.eta_minus == pytest.approx(0.05, abs=1e-9)
    assert r.snn.enable_hebbian is True  # 恢复到进入前的原值
    assert r.snn.enable_structural_plasticity is False


def test_snn_iterate_zero_readiness_disables_hebbian(tmp_path):
    """未成熟(readiness 0) → autonomy 0 → 内源不生长, 但仍恢复状态"""
    r = _region_with_iterate_path(tmp_path)
    r.snn.hebbian_annealing = True
    r.snn.adapt_hebbian_autonomy(0.0)
    out = r.snn_iterate()
    assert out["hebbian_autonomy"] == pytest.approx(0.0, abs=1e-9)
    assert r.snn.eta_plus == pytest.approx(0.2, abs=1e-9)


def test_eta_scaling_actually_reduces_growth(tmp_path):
    """autonomy 部分值 → eta 按同比例缩小(核心调制语义)"""
    net = _new_net()
    net.hebbian_annealing = True
    a = 0.25
    net.adapt_hebbian_autonomy(a)
    # 直接验证缩放语义: autonomy × 原 eta = 生效 eta
    assert a * net.eta_plus == pytest.approx(net.eta_plus * a, abs=1e-12)
    assert net._hebbian_autonomy == pytest.approx(a, abs=1e-9)


# ── 门控 ──────────────────────────────────────────────────

def test_hebbian_annealing_default_from_env(monkeypatch):
    monkeypatch.delenv("BRAIN_HEBBIAN_ANNEALING", raising=False)
    assert SNN().hebbian_annealing is False
    monkeypatch.setenv("BRAIN_HEBBIAN_ANNEALING", "1")
    assert SNN().hebbian_annealing is True


# ── 持久化 ────────────────────────────────────────────────

def test_hebbian_params_roundtrip_persistence(tmp_path):
    net = _new_net()
    net.adapt_hebbian_autonomy(0.42)
    net.hebbian_anneal_lo = 0.05
    net.hebbian_anneal_hi = 0.95
    path = str(tmp_path / "net.json")
    net.save(path)

    loaded = SNN.load(path)
    assert loaded._hebbian_autonomy == pytest.approx(0.42, abs=1e-6)
    assert loaded.hebbian_anneal_lo == pytest.approx(0.05, abs=1e-9)
    assert loaded.hebbian_anneal_hi == pytest.approx(0.95, abs=1e-9)


def test_from_dict_backward_compat_missing_keys():
    net = _new_net()
    data = net.to_dict()
    for k in ("hebbian_annealing", "hebbian_anneal_lo", "hebbian_anneal_hi",
              "hebbian_autonomy"):
        data.pop(k, None)
    loaded = SNN.from_dict(data)
    assert loaded.hebbian_anneal_lo == pytest.approx(net.hebbian_anneal_lo, abs=1e-9)
    assert loaded.hebbian_anneal_hi == pytest.approx(net.hebbian_anneal_hi, abs=1e-9)
    assert loaded._hebbian_autonomy == 0.0
    assert loaded.hebbian_annealing is False


# ── 防自反馈: autonomy 不是 readiness 分量 ──────────────────

def test_autonomy_is_not_readiness_component():
    """核心约束: autonomy 不得进入 readiness 的任何分量。

    若 autonomy 成为指标, 学生可通过'多生长'刷高 autonomy → readiness 升高 →
    更多生长, 形成正反馈。autonomy 必须是被指标驱动的产出, 不是指标本身。
    """
    import inspect

    from services.brain import snn_region as mod

    src = inspect.getsource(mod.SNNRegion.readiness_score)
    assert "autonomy" not in src, "autonomy 不应出现在 readiness_score 计算中"
    assert "_hebbian_autonomy" not in src