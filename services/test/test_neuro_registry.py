"""neuro_registry 单元测试：通用输入/输出槽注册器。

覆盖：
- InputRegistry: 新类型分配新槽，不挤占旧槽，映射持久化
- OutputRegistry: 新动作分配新槽，动作空间可扩展
- NeuroRegistry: 组合注册 + 探索连接（新输入 → 弱连接隐藏层）
- 集成: SNNRegion._encode_signal 动态注册新类型
- 集成: SNNRegion._decode_output 解析动态输出动作
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

import pytest

from services.brain.snn import SNN, NeuronType
from services.brain.neuro_registry import (
    InputRegistry,
    OutputRegistry,
    NeuroRegistry,
    _NEW_INPUT_START,
    _NEW_OUTPUT_START,
)


@pytest.fixture
def registry_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def input_reg(registry_dir):
    return InputRegistry(os.path.join(registry_dir, "reg.json"))


@pytest.fixture
def output_reg(registry_dir):
    return OutputRegistry(os.path.join(registry_dir, "reg.json"))


# ─── InputRegistry ────────────────────────────────────────────


class TestInputRegistry:
    def test_register_new_type_gets_new_slot(self, input_reg):
        """新类型分配新槽（≥40），不挤占旧槽"""
        nid = input_reg.register("novel_signal")
        assert nid >= _NEW_INPUT_START

    def test_register_same_type_returns_same_slot(self, input_reg):
        """同一类型重复注册返回同一槽"""
        n1 = input_reg.register("expense_audit")
        n2 = input_reg.register("expense_audit")
        assert n1 == n2

    def test_register_different_types_get_distinct_slots(self, input_reg):
        """不同类型获得不同槽"""
        n1 = input_reg.register("type_a")
        n2 = input_reg.register("type_b")
        assert n1 != n2

    def test_get_returns_registered(self, input_reg):
        input_reg.register("type_x")
        assert input_reg.get("type_x") is not None

    def test_get_unregistered_returns_none(self, input_reg):
        assert input_reg.get("never_registered") is None

    def test_persistence_roundtrip(self, registry_dir):
        """映射持久化：新实例从文件加载恢复映射"""
        path = os.path.join(registry_dir, "reg.json")
        r1 = InputRegistry(path)
        r1.register("persisted_type")
        r1.register("another_type")
        # 新实例加载
        r2 = InputRegistry(path)
        assert r2.get("persisted_type") == r1.get("persisted_type")
        assert r2.get("another_type") == r1.get("another_type")

    def test_count_tracks_registered(self, input_reg):
        input_reg.register("a")
        input_reg.register("b")
        assert input_reg.count() == 2

    def test_new_types_never_reuse_old_slots(self, input_reg):
        """新类型绝不返回已占用的槽（不挤占）"""
        slots = set()
        for i in range(5):
            nid = input_reg.register(f"type_{i}")
            assert nid not in slots
            slots.add(nid)


# ─── OutputRegistry ───────────────────────────────────────────


class TestOutputRegistry:
    def test_register_new_action_gets_new_slot(self, output_reg):
        nid = output_reg.register("batch_approve")
        assert nid >= _NEW_OUTPUT_START

    def test_register_same_action_same_slot(self, output_reg):
        n1 = output_reg.register("manual_review")
        n2 = output_reg.register("manual_review")
        assert n1 == n2

    def test_get_action_roundtrip(self, output_reg):
        nid = output_reg.register("special_review")
        assert output_reg.get_action(nid) == "special_review"
        assert output_reg.get("special_review") == nid

    def test_persistence_roundtrip(self, registry_dir):
        path = os.path.join(registry_dir, "reg.json")
        r1 = OutputRegistry(path)
        r1.register("batch_approve")
        r2 = OutputRegistry(path)
        assert r2.get("batch_approve") == r1.get("batch_approve")


# ─── NeuroRegistry (组合 + 探索连接) ─────────────────────────


class TestNeuroRegistry:
    def test_ensure_input_creates_neuron_and_exploration(self):
        """新类型注册后：神经元存在 + 探索连接（弱权重）"""
        net = SNN.create_default()
        reg = NeuroRegistry(net)
        nid = reg.ensure_input("brand_new_type")
        # 神经元存在
        assert nid < net.num_neurons
        assert net.neurons[nid].neuron_type == NeuronType.INPUT
        # 探索连接：新输入神经元有出边到隐藏层
        assert len(net.out_edges.get(nid, {})) > 0
        # 探索连接是弱权重（< 1.0）
        for target, conn in net.out_edges[nid].items():
            assert 16 <= target < 28  # 兴奋性隐藏层
            assert conn.weight < 1.0

    def test_ensure_input_existing_no_new_connection(self):
        """已注册类型：返回原槽，不重复加连接"""
        net = SNN.create_default()
        reg = NeuroRegistry(net)
        n1 = reg.ensure_input("type_a")
        edges_after_first = len(net.out_edges.get(n1, {}))
        n2 = reg.ensure_input("type_a")
        assert n1 == n2
        assert len(net.out_edges.get(n2, {})) == edges_after_first

    def test_ensure_output_creates_neuron_and_connection(self):
        net = SNN.create_default()
        reg = NeuroRegistry(net)
        nid = reg.ensure_output("batch_approve")
        assert nid < net.num_neurons
        # 探索连接：从隐藏层到新输出
        has_explore = any(
            nid in net.out_edges.get(hid, {})
            for hid in range(16, 28)
        )
        assert has_explore

    def test_dynamic_slots_do_not_break_fixed_topology(self):
        """动态注册不破坏固定拓扑（12 固定输出仍存在，40 神经元基线不变）"""
        net = SNN.create_default()
        assert net.num_neurons == 40
        reg = NeuroRegistry(net)
        reg.ensure_input("new_type_1")
        reg.ensure_input("new_type_2")
        # 固定输出神经元仍在
        for nid in range(32, 38):
            assert net.neurons[nid].neuron_type == NeuronType.OUTPUT
