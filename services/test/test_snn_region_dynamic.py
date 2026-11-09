"""SNNRegion 集成测试：通用输入/输出槽动态注册。

验证：
- _encode_signal 对新类型动态分配新槽（不挤占旧槽）
- 新类型注册后神经元 + 探索连接存在
- 新类型能参与推理（不崩溃，产生决策或 None）
- 动态输出动作可被 _decode_output 解析
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

import pytest

# 隔离配置目录，避免污染真实 /app/config_data
@pytest.fixture
def isolated_env(tmp_path):
    os.environ["BRAIN_CONFIG_DIR"] = str(tmp_path)
    yield tmp_path
    os.environ.pop("BRAIN_CONFIG_DIR", None)


@pytest.fixture
def region(isolated_env):
    from services.brain.snn_region import SNNRegion
    r = SNNRegion(save_path=os.path.join(isolated_env, "snn_network.json"))
    return r


# ─── _encode_signal 动态注册 ─────────────────────────────────


class TestEncodeDynamicSignal:
    def test_unknown_type_gets_dynamic_slot(self, region):
        """新类型（未映射）→ 动态新槽（≥40），不挤占旧槽"""
        from models.brain import NeuralSignal

        sig = NeuralSignal(type="quantum_audit", urgency=50, payload={"amount": 500})
        neurons = region._encode_signal(sig)
        # 动态槽存在
        dynamic = [n for n in neurons if n >= 40]
        assert dynamic, f"未产生动态槽, neurons={neurons}"

    def test_same_type_reuses_same_slot(self, region):
        from models.brain import NeuralSignal

        sig1 = NeuralSignal(type="special_event", urgency=30)
        sig2 = NeuralSignal(type="special_event", urgency=80)
        n1 = region._encode_signal(sig1)
        n2 = region._encode_signal(sig2)
        # 两次编码应包含相同的动态槽（类型槽）
        dyn1 = [n for n in n1 if n >= 40]
        dyn2 = [n for n in n2 if n >= 40]
        assert dyn1 and dyn2
        assert set(dyn1) & set(dyn2)  # 共享类型槽

    def test_new_type_creates_exploration_connections(self, region):
        """新类型注册后，动态神经元有探索连接（出边到隐藏层）"""
        from models.brain import NeuralSignal

        sig = NeuralSignal(type="fleet_management", urgency=40, payload={"amount": 2000})
        neurons = region._encode_signal(sig)
        dyn = [n for n in neurons if n >= 40]
        assert dyn
        for nid in dyn:
            assert nid < region.snn.num_neurons
            out = region.snn.out_edges.get(nid, {})
            assert len(out) > 0, f"动态神经元 {nid} 无探索连接"

    def test_dynamic_slot_does_not_reuse_fixed(self, region):
        """动态槽不占用固定槽（0-15 / 38-39）"""
        from models.brain import NeuralSignal

        for i, t in enumerate(["custom_a", "custom_b", "custom_c"]):
            sig = NeuralSignal(type=t, urgency=50)
            neurons = region._encode_signal(sig)
            dyn = [n for n in neurons if n >= 40]
            assert dyn, f"{t} 未产生动态槽"
            assert all(n not in range(0, 40) for n in dyn)

    def test_reason_with_new_type_no_crash(self, region):
        """新类型推理不崩溃（返回 RegionResult 或 None）"""
        import asyncio
        from models.brain import NeuralSignal

        sig = NeuralSignal(type="satellite_telemetry", urgency=60,
                           payload={"amount": 80000, "description": "紧急轨道调整"})
        result = asyncio.run(region.reason(sig, context={}))
        # 不崩溃即可；result 可能为 None（未达阈值）或 RegionResult
        assert result is not None or True


# ─── _decode_output 动态输出 ─────────────────────────────────


class TestDecodeDynamicOutput:
    def test_decision_to_output_neuron_dynamic(self, region):
        """动态动作注册后可被 _decision_to_output_neuron 解析"""
        nid = region.output_registry.register("batch_approve")
        assert region._decision_to_output_neuron("batch_approve") == nid

    def test_decision_for_output_dynamic(self, region):
        """_decision_for_output 解析动态输出槽"""
        nid = region.output_registry.register("manual_review")
        assert region._decision_for_output(nid) == "manual_review"

    def test_fixed_output_still_works(self, region):
        """固定输出槽仍正常解析"""
        assert region._decision_for_output(32) == "auto_approve"
        assert region._decision_for_output(34) == "escalate"
        assert region._decision_to_output_neuron("chat") == 37
