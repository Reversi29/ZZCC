"""结构可塑性专项测试：生长/修剪(通断) + 步长演化(加长/缩短)。

与 STDP 强度调节(_hebbian_update 只调 weight)区分：
- 修剪: 权重跌破 min_weight_for_keep → disconnect
- 生长: 协同放电且无连接 → connect(allow_synaptogenesis)
- 步长演化: 放电相关性 → set_step(强相关缩短,弱相关加长)

默认 enable_structural_plasticity=False, 需显式启用。
"""
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

from services.brain.snn import SNN


@pytest.fixture
def net():
    n = SNN(num_neurons=10)
    n.enable_structural_plasticity = True
    return n


class TestPrune:
    """修剪：权重跌破下限 → 断开"""

    def test_prune_when_weight_below_floor(self, net):
        net.connect(0, 1, weight=0.03, step=1)  # 低于 min_weight_for_keep=0.05
        net.step()
        assert 1 not in net.out_edges[0], "权重跌破下限应断开连接"

    def test_keep_when_weight_above_floor(self, net):
        net.connect(0, 1, weight=0.5, step=1)   # 高于下限
        net.step()
        assert 1 in net.out_edges[0], "权重正常应保留连接"

    def test_prune_only_when_enabled(self):
        """默认关闭时不修剪"""
        n = SNN(num_neurons=10)
        n.connect(0, 1, weight=0.01, step=1)
        n.step()
        assert 1 in n.out_edges[0], "默认关闭结构可塑性, 不修剪"


class TestStepEvolve:
    """步长演化：放电相关性 → 缩短/加长"""

    def test_shorten_step_when_correlated(self, net):
        net.connect(0, 1, weight=1.0, step=3)
        # 注入让 0 放电
        net.inject_input(0, 1.5)
        net.step()          # t=0: 0 放电, 1 未放电
        net.inject_input(1, 1.5)
        net.step()          # t=1: 1 放电, 与 0 在 step+2 窗口内 → 正相关
        # 源0 最近放电 t=0, 目标1 放电 t=1, gap=1 <= step+2=5 → 相关
        assert net.out_edges[0][1].step < 3, "强相关应缩短步长"

    def test_lengthen_step_when_uncorrelated(self, net):
        net.connect(0, 1, weight=1.0, step=1)
        # 只让 1 放电, 0 不放电 → 弱相关 → 加长
        for _ in range(3):
            net.inject_input(1, 1.5)
            net.step()
        assert net.out_edges[0][1].step > 1, "弱相关应加长步长"

    def test_step_clamped_to_max(self, net):
        net.connect(0, 1, weight=1.0, step=5)  # 已在上限
        for _ in range(3):
            net.inject_input(1, 1.5)
            net.step()
        assert net.out_edges[0][1].step <= 5, "步长不应超过上限"


class TestSynaptogenesis:
    """生长：协同放电 → 建连"""

    def test_create_connection_on_cofire(self, net):
        net.allow_synaptogenesis = True
        # 同时放电 0 和 1
        net.inject_input(0, 1.5)
        net.inject_input(1, 1.5)
        net.step()
        assert 1 in net.out_edges.get(0, {}), "协同放电应建连 0→1"

    def test_no_synaptogenesis_when_disabled(self, net):
        net.allow_synaptogenesis = False
        net.inject_input(0, 1.5)
        net.inject_input(1, 1.5)
        net.step()
        assert 1 not in net.out_edges.get(0, {}), "默认关闭生长"


class TestSetStepAPI:
    """set_step 通断能力：显式设置 + 夹取"""

    def test_set_step(self, net):
        net.connect(0, 1, weight=1.0, step=1)
        assert net.set_step(0, 1, 4)
        assert net.out_edges[0][1].step == 4

    def test_set_step_min_floor(self, net):
        net.connect(0, 1, weight=1.0, step=1)
        net.set_step(0, 1, 0)
        assert net.out_edges[0][1].step == 1, "步长最小夹取 1"

    def test_disconnect_removes(self, net):
        net.connect(0, 1, weight=1.0, step=1)
        assert net.disconnect(0, 1)
        assert 1 not in net.out_edges[0]
        assert 0 not in net.in_edges[1]
