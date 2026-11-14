"""EWC 持久化 + 衰减测试（方向 B：EWC 固化）。

背景：EWC 重要性此前只存在内存，重启/漂移恢复即清零，固化知识全部丢失。
EWC_IMPORTANCE_DECAY 定义了但从未调用，importance 只增不减最终饱和冻结。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

import pytest  # noqa: E402
from services.brain.snn import SNN, NeuronType  # noqa: E402


def _net():
    n = SNN(num_neurons=10)
    n.add_neuron(0, NeuronType.INPUT)
    n.add_neuron(1, NeuronType.EXCITATORY)
    n.add_neuron(2, NeuronType.OUTPUT, threshold=0.5)
    n.connect(0, 1, weight=1.0, delay=1)
    n.connect(1, 2, weight=1.0, delay=1)
    return n


def test_ewc_importance_tracks_fired():
    """被激活神经元的出边重要性应递增。"""
    n = _net()
    n._update_ewc_importance({0})
    assert n._ewc_importance[(0, 1)] > 0


def test_ewc_persistence_roundtrip():
    """to_dict/from_dict 应保留 EWC 重要性（此前重启清零）。"""
    n = _net()
    n._update_ewc_importance({0})
    n._update_ewc_importance({0})
    data = n.to_dict()
    assert "ewc_importance" in data
    assert len(data["ewc_importance"]) > 0

    n2 = SNN.from_dict(data)
    assert n2._ewc_importance[(0, 1)] == pytest.approx(n._ewc_importance[(0, 1)])


def test_ewc_decay_applied():
    """importance 应随时间衰减（此前 EWC_IMPORTANCE_DECAY 是死代码）。"""
    n = _net()
    n._update_ewc_importance({0})
    v0 = n._ewc_importance[(0, 1)]
    # 连续多次衰减（不激活），值应下降
    for _ in range(10):
        n._update_ewc_importance(set())
    assert n._ewc_importance[(0, 1)] < v0


def test_ewc_decay_cleans_small():
    """低于阈值的重要性应被清理，防止稀疏表膨胀。"""
    n = _net()
    n._ewc_importance[(0, 1)] = 0.0005  # 低于清理阈值 0.001
    n._update_ewc_importance(set())
    assert (0, 1) not in n._ewc_importance


def test_ewc_multiplier_protects():
    """重要性高的连接学习率应显著降低。"""
    n = _net()
    assert n._get_ewc_multiplier(0, 1) == pytest.approx(1.0)
    n._ewc_importance[(0, 1)] = 10.0  # 饱和
    assert n._get_ewc_multiplier(0, 1) < 0.1
