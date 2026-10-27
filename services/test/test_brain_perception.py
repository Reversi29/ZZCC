"""test_brain_perception.py — 感知层单元测试

验证 TextPerceptionChannel 特征提取正确性。
"""
import sys
import os

# 确保能导入 services 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.perception import Perception, TextPerceptionChannel, CHANNELS


class TestPerception:
    """感知层特征提取测试。"""

    def setup_method(self):
        self.perception = Perception()
        self.channel = TextPerceptionChannel()

    def test_channel_dimensions(self):
        """通道维度总数应为 28（感知输入神经元）。"""
        total = sum(ch.dim for ch in CHANNELS.values())
        assert total == 28, f"expected 28, got {total}"

    def test_empty_input(self):
        """空输入应返回全零特征。"""
        r = self.channel.perceive("")
        assert r.token_count == 0
        assert len(r.to_flat_vector()) == 28
        assert all(v == 0.0 for v in r.to_flat_vector())

    def test_high_amount_risk(self):
        """88000元设备采购高风险：高金额幅度 + 负面情感 + 正式度。"""
        r = self.channel.perceive("审批一笔88000元的设备采购费用，供应商风险高")
        numeric = r.features["numeric"]
        sentiment = r.features["sentiment"]
        formality = r.features["formality"]
        # 金额幅度高
        assert numeric[1] > 0.7, f"expected high magnitude, got {numeric[1]}"
        # 有货币符号
        assert numeric[2] > 0.5, "expected currency present"
        # 负面情感（"风险"）
        assert sentiment[1] > 0.0, f"expected neg polarity, got {sentiment[1]}"
        # 正式度（"审批""采购"）
        assert formality[0] > 0.0, f"expected formality, got {formality[0]}"

    def test_low_amount(self):
        """500元办公用品：金额幅度低于88000元。"""
        r = self.channel.perceive("审批一笔500元的办公室用品采购费用")
        numeric = r.features["numeric"]
        high_r = self.channel.perceive("审批一笔88000元的设备采购费用，供应商风险高")
        high_numeric = high_r.features["numeric"]
        # 500元幅度 < 88000元幅度
        assert numeric[1] < high_numeric[1], f"expected {numeric[1]} < {high_numeric[1]}"

    def test_chitchat(self):
        """闲聊：低负面 + 低金额。"""
        r = self.channel.perceive("你好")
        sentiment = r.features["sentiment"]
        numeric = r.features["numeric"]
        # 正面情感（"好"）
        assert sentiment[0] > 0.0, f"expected pos polarity, got {sentiment[0]}"
        # 无金额
        assert numeric[0] == 0.0, "expected no number"

    def test_imperative(self):
        """取消订单：命令式（帮我开头）。"""
        r = self.channel.perceive("帮我取消订单#12345")
        formality = r.features["formality"]
        assert formality[3] > 0.5, f"expected imperative, got {formality[3]}"

    def test_flat_vector_length(self):
        """扁平向量长度应为 28。"""
        r = self.channel.perceive("测试")
        assert len(r.to_flat_vector()) == 28

    def test_payload_extraction(self):
        """Perception.perceive 应从 payload 提取文本。"""
        r = self.perception.perceive({"question": "审批一笔500元的办公用品费用"})
        assert r.token_count > 0, "expected tokens from payload"
        assert r.raw_text != "", "expected raw text"


class TestTemporalPerception:
    """时序感知测试。"""

    def test_empty_history(self):
        """空历史应返回零特征。"""
        from services.brain.perception import TemporalPerceptionChannel
        channel = TemporalPerceptionChannel()
        r = channel.perceive([])
        assert "cadence" in r.features
        assert len(r.features["cadence"]) == 4
