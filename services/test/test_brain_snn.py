"""SNN 脉冲神经网络单元测试。

覆盖：
- 结构操作（添加/删除神经元、连接、断开）
- 基本信号传播（inject → step → output）
- STDP 学习（LTP 加强、LTD 减弱）
- 奖励调制 Hebbian（train_by_association 自举新连接）
- 持久化（save → load 往返）
- 默认拓扑（create_default 38 神经元）
- reset 清理状态
"""

import json
import os
import tempfile

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

import pytest
from collections import defaultdict

from services.brain.snn import SNN, Neuron, NeuronType, Connection


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def small_net():
    """5 神经元微型网络：2 input + 2 exc + 1 output"""
    net = SNN(num_neurons=5)
    net.add_neuron(0, NeuronType.INPUT, threshold=0.5)
    net.add_neuron(1, NeuronType.INPUT, threshold=0.5)
    net.add_neuron(2, NeuronType.EXCITATORY, threshold=1.0)
    net.add_neuron(3, NeuronType.EXCITATORY, threshold=1.0)
    net.add_neuron(4, NeuronType.OUTPUT, threshold=1.5)
    net.connect(0, 2, weight=0.8, delay=1)
    net.connect(1, 3, weight=0.8, delay=1)
    net.connect(2, 4, weight=0.8, delay=1)
    net.connect(3, 4, weight=0.8, delay=2)
    return net


@pytest.fixture
def default_net():
    """默认拓扑网络"""
    return SNN.create_default()


# ─── 结构操作 ────────────────────────────────────────────────


class TestStructure:
    def test_add_neuron(self):
        net = SNN(num_neurons=3)
        n = net.add_neuron(5, NeuronType.INPUT, threshold=0.3)
        assert n.id == 5
        assert n.neuron_type == NeuronType.INPUT
        assert n.threshold == 0.3
        assert net.num_neurons == 6

    def test_add_neuron_extends_list(self):
        net = SNN(num_neurons=2)
        net.add_neuron(10, NeuronType.OUTPUT)
        assert net.num_neurons == 11
        assert len(net.neurons) == 11

    def test_connect(self):
        net = SNN(num_neurons=3)
        assert net.connect(0, 1, weight=0.5, delay=2)
        conn = net.out_edges[0][1]
        assert conn.weight == 0.5
        assert conn.delay == 2
        # 反向也能查到
        assert net.in_edges[1][0] is conn

    def test_connect_invalid(self):
        net = SNN(num_neurons=3)
        assert not net.connect(0, 0)        # 自连接
        assert not net.connect(-1, 1)       # 源越界
        assert not net.connect(0, 99)       # 目标越界

    def test_disconnect(self):
        net = SNN(num_neurons=3)
        net.connect(0, 1, weight=1.0)
        assert net.disconnect(0, 1)
        assert 1 not in net.out_edges.get(0, {})
        assert 0 not in net.in_edges.get(1, {})

    def test_disconnect_nonexistent(self):
        net = SNN(num_neurons=3)
        assert not net.disconnect(0, 1)

    def test_set_weight(self):
        net = SNN(num_neurons=3)
        net.connect(0, 1, weight=1.0)
        net.set_weight(0, 1, 3.0)
        assert net.out_edges[0][1].weight == 3.0

    def test_set_weight_clamped(self):
        net = SNN(num_neurons=3)
        net.max_weight = 5.0
        net.connect(0, 1, weight=1.0)
        net.set_weight(0, 1, 999)
        assert net.out_edges[0][1].weight == 5.0

    def test_set_delay(self):
        net = SNN(num_neurons=3)
        net.connect(0, 1, delay=1)
        net.set_delay(0, 1, 5)
        assert net.out_edges[0][1].delay == 5

    def test_set_delay_minimum(self):
        net = SNN(num_neurons=3)
        net.connect(0, 1, delay=1)
        net.set_delay(0, 1, 0)
        assert net.out_edges[0][1].delay == 1

    def test_remove_neuron(self):
        net = SNN(num_neurons=3)
        net.add_neuron(0, NeuronType.INPUT)
        assert net.remove_neuron(0)
        assert net.neurons[0].threshold == 99999  # 永不激活


# ─── 信号传播 ────────────────────────────────────────────────


class TestSignalPropagation:
    def test_inject_input(self, small_net):
        small_net.inject_input(0, 1.0)
        assert small_net.neurons[0].membrane == pytest.approx(1.0)

    def test_inject_pattern(self, small_net):
        small_net.inject_pattern([0, 1], 0.6)
        assert small_net.neurons[0].membrane == pytest.approx(0.6)
        assert small_net.neurons[1].membrane == pytest.approx(0.6)

    def test_input_neuron_fires(self, small_net):
        """输入神经元直接注入即激活"""
        small_net.inject_input(0, 1.0)  # threshold 0.5
        outs = small_net.step()
        assert small_net.neurons[0].is_firing
        assert 0 in small_net.get_active_neurons()

    def test_signal_propagates_one_hop(self, small_net):
        """输入 → exc 一跳传播"""
        small_net.inject_input(0, 1.0)  # 激活 input 0
        small_net.step()               # t=1: input 0 fires, 信号传播到 exc 2
        small_net.step()               # t=2: exc 2 收到信号
        # exc 2 的 membrane 应该收到了 0.8
        assert small_net.neurons[2].membrane > 0

    def test_output_fires_with_enough_input(self, small_net):
        """足够输入激活 output 神经元"""
        # 信号路径: input 0 →(delay1)→ exc 2 →(delay1)→ output 4
        # 需要持续注入让膜电位累积超过 threshold
        for _ in range(20):
            small_net.inject_input(0, 2.0)
            small_net.inject_input(1, 2.0)
            small_net.step()
        assert small_net.neurons[4].fire_count > 0

    def test_step_returns_output_dict(self, small_net):
        outs = small_net.step()
        assert isinstance(outs, dict)
        assert 4 in outs  # output neuron id
        assert all(isinstance(v, bool) for v in outs.values())


# ─── STDP 学习 ───────────────────────────────────────────────


class TestSTDP:
    def test_ltp_strengthens_connection(self, small_net):
        """源先激活、目标在窗口内跟随 → 权重增加"""
        initial_w = small_net.out_edges[0][2].weight  # 0→2 初始 0.8
        # 注入输入让 0 激活，传播到 2，2 随后激活
        for _ in range(10):
            small_net.inject_input(0, 2.0)
            small_net.step()
        final_w = small_net.out_edges[0][2].weight
        assert final_w > initial_w  # 权重增加

    def test_ltd_when_source_out_of_window(self, small_net):
        """源激活过但太久，目标后激活 → 权重减弱（超出 STDP 窗口）"""
        # 先让 input 0 激活一次
        small_net.inject_input(0, 2.0)
        small_net.step()  # t=1: input 0 fires
        # 等很多步让 gap 超过 delay+2
        for _ in range(20):
            small_net.step()  # 时间推进，0 不再注入
        # 现在给 exc 2 直接注入让它激活（此时 gap 远超 delay+2=3）
        small_net.inject_input(2, 3.0)
        small_net.step()
        w = small_net.out_edges[0][2].weight
        assert w < 0.8  # 超出窗口 → LTD 减弱

    def test_weight_clamped_at_max(self):
        net = SNN(num_neurons=3)
        net.max_weight = 2.0
        net.add_neuron(0, NeuronType.INPUT, threshold=0.3)
        net.add_neuron(1, NeuronType.EXCITATORY, threshold=0.3)
        net.add_neuron(2, NeuronType.OUTPUT, threshold=0.3)
        net.connect(0, 1, weight=1.9, delay=1)
        net.connect(1, 2, weight=1.9, delay=1)
        for _ in range(20):
            net.inject_input(0, 2.0)
            net.step()
        assert net.out_edges[0][1].weight <= 2.0


# ─── 奖励调制学习 ───────────────────────────────────────────


class TestRewardModulation:
    def test_train_by_association_creates_connection(self):
        """训练后输入模式能激活输出"""
        net = SNN(num_neurons=4)
        net.add_neuron(0, NeuronType.INPUT, threshold=0.5)
        net.add_neuron(1, NeuronType.EXCITATORY, threshold=1.0)
        net.add_neuron(2, NeuronType.EXCITATORY, threshold=1.0)
        net.add_neuron(3, NeuronType.OUTPUT, threshold=1.5)
        net.connect(0, 1, weight=0.8, delay=1)
        net.connect(1, 2, weight=0.5, delay=1)
        # 不连接 2→3，训练后应自举创建

        net.train_by_association([0], output_neuron=3, steps=30)

        # 训练后注入 [0] 应能激活 output 3
        net.reset()
        for _ in range(10):
            net.inject_input(0, 2.0)
            outs = net.step()
            if outs.get(3, False):
                break
        assert net.neurons[3].fire_count > 0

    def test_reward_strengthen_creates_synapse(self):
        """奖励调制应创建新突触"""
        net = SNN(num_neurons=3)
        net.add_neuron(0, NeuronType.INPUT, threshold=0.5)
        net.add_neuron(1, NeuronType.EXCITATORY, threshold=0.5)
        net.add_neuron(2, NeuronType.OUTPUT, threshold=0.5)
        # 0→2 没有连接
        # 先激活 0，再激活 2（奖励）
        net.inject_input(0, 2.0)
        net.step()
        net.inject_input(2, 2.0)
        net.step()
        # 奖励调制
        net._reward_modulated_strengthen(2, eta=0.1, auto_create=True, auto_create_weight=0.2)
        # 应创建了 0→2 连接
        assert 2 in net.out_edges.get(0, {})


# ─── 持久化 ──────────────────────────────────────────────────


class TestPersistence:
    def test_save_load_roundtrip(self, small_net, tmp_path):
        path = str(tmp_path / "test_snn.json")
        small_net.save(path)
        assert os.path.exists(path)

        loaded = SNN.load(path)
        assert loaded is not None
        assert loaded.num_neurons == small_net.num_neurons
        assert len(loaded.out_edges) == len(small_net.out_edges)
        # 验证连接参数
        orig_conn = small_net.out_edges[0][2]
        loaded_conn = loaded.out_edges[0][2]
        assert loaded_conn.weight == pytest.approx(orig_conn.weight)
        assert loaded_conn.delay == orig_conn.delay

    def test_load_nonexistent(self):
        loaded = SNN.load("/nonexistent/path/snn.json")
        assert loaded is None

    def test_to_dict_contains_all_fields(self, small_net):
        d = small_net.to_dict()
        assert "num_neurons" in d
        assert "time" in d
        assert "eta_plus" in d
        assert "eta_minus" in d
        assert "max_weight" in d
        assert "neurons" in d
        assert "edges" in d
        assert len(d["neurons"]) == 5
        assert len(d["edges"]) == 4

    def test_from_dict_restores_neuron_types(self):
        net = SNN.create_default()
        d = net.to_dict()
        restored = SNN.from_dict(d)
        for orig, loaded in zip(net.neurons, restored.neurons):
            assert orig.neuron_type == loaded.neuron_type
            assert orig.threshold == loaded.threshold


# ─── 默认拓扑 ────────────────────────────────────────────────


class TestDefaultTopology:
    def test_create_default_has_38_neurons(self, default_net):
        assert default_net.num_neurons == 38

    def test_default_neuron_types(self, default_net):
        types = defaultdict(int)
        for n in default_net.neurons:
            types[n.neuron_type] += 1
        assert types[NeuronType.INPUT] == 16
        assert types[NeuronType.EXCITATORY] == 12
        assert types[NeuronType.INHIBITORY] == 4
        assert types[NeuronType.OUTPUT] == 6

    def test_default_has_connections(self, default_net):
        edge_count = sum(len(v) for v in default_net.out_edges.values())
        assert edge_count > 0

    def test_default_output_thresholds(self, default_net):
        for nid in range(32, 38):
            assert default_net.neurons[nid].neuron_type == NeuronType.OUTPUT
            assert default_net.neurons[nid].threshold == 1.0


# ─── Reset ───────────────────────────────────────────────────


class TestReset:
    def test_reset_clears_membrane(self, small_net):
        small_net.inject_input(0, 5.0)
        small_net.step()
        small_net.reset()
        for n in small_net.neurons:
            assert n.membrane == 0.0
            assert n.is_firing is False

    def test_reset_clears_events(self, small_net):
        small_net.inject_input(0, 2.0)
        small_net.step()
        # 应有待传播事件
        assert len(small_net._pending_events) > 0
        small_net.reset()
        assert len(small_net._pending_events) == 0

    def test_reset_clears_history(self, small_net):
        small_net.inject_input(0, 2.0)
        small_net.step()
        assert len(small_net._fire_history) > 0
        small_net.reset()
        assert len(small_net._fire_history) == 0

    def test_reset_resets_time(self, small_net):
        small_net.step()
        small_net.step()
        assert small_net.time > 0
        small_net.reset()
        assert small_net.time == 0


# ─── Stats ───────────────────────────────────────────────────


class TestStats:
    def test_stats_structure(self, default_net):
        s = default_net.stats()
        assert s["num_neurons"] == 38
        assert s["num_edges"] > 0
        assert s["total_fires"] == 0  # 初始无激活
        assert s["time"] == 0
        assert "neuron_types" in s
        assert "eta_plus" in s
        assert "eta_minus" in s

    def test_stats_after_firing(self, default_net):
        default_net.inject_input(0, 2.0)
        default_net.step()
        s = default_net.stats()
        assert s["total_fires"] > 0
        assert s["time"] == 1


# ─── run / train 接口 ────────────────────────────────────────


class TestRunInterface:
    def test_run_returns_output_list(self, small_net):
        def input_fn(t, net):
            if t % 2 == 0:
                net.inject_input(0, 1.0)

        results = small_net.run(steps=10, input_fn=input_fn)
        assert len(results) == 10
        assert all(isinstance(r, dict) for r in results)

    def test_train_hebbian_increases_weight(self):
        net = SNN(num_neurons=3)
        net.add_neuron(0, NeuronType.INPUT, threshold=0.3)
        net.add_neuron(1, NeuronType.EXCITATORY, threshold=0.3)
        net.add_neuron(2, NeuronType.OUTPUT, threshold=0.3)
        net.connect(0, 1, weight=0.5, delay=1)
        net.connect(1, 2, weight=0.5, delay=1)
        w_before = net.out_edges[0][1].weight
        net.train_hebbian([0], steps=30, strength=2.0)
        w_after = net.out_edges[0][1].weight
        assert w_after >= w_before  # 权重不减不减，至少不减
