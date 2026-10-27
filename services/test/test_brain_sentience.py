"""test_brain_sentience.py — 感受层单元测试

验证 SentienceNet 从感知特征产生合理感受方向。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

import tempfile

from services.brain.perception import Perception
from services.brain.sentience import SentienceNet, SENTIENCE_DIMS


class TestSentience:
    """感受层测试。"""

    def setup_method(self):
        self.perception = Perception()
        # 用临时路径避免污染容器路径
        tmpdir = tempfile.mkdtemp()
        self.sentience = SentienceNet(path=os.path.join(tmpdir, "sentience_test.json"))

    def test_sentience_dims(self):
        """感受维度应为 6 个。"""
        assert len(SENTIENCE_DIMS) == 6
        assert "threat" in SENTIENCE_DIMS
        assert "safety" in SENTIENCE_DIMS
        assert "urgency" in SENTIENCE_DIMS

    def test_high_risk_threat(self):
        """88000元设备采购高风险：threat 高。"""
        per = self.perception.text_channel.perceive(
            "审批一笔88000元的设备采购费用，供应商风险高"
        )
        st = self.sentience.sense(per)
        assert st.get("threat") > 0.5, f"expected high threat, got {st.get('threat')}"
        assert st.get("urgency") > 0.5, f"expected high urgency, got {st.get('urgency')}"

    def test_low_risk_threat(self):
        """500元办公用品：threat 低（低于88000元）。"""
        per = self.perception.text_channel.perceive("审批一笔500元的办公室用品采购费用")
        st = self.sentience.sense(per)
        assert st.get("threat") < 0.5, f"expected low threat, got {st.get('threat')}"

    def test_chitchat_safety(self):
        """闲聊：safety 高 + threat 低。"""
        per = self.perception.text_channel.perceive("你好")
        st = self.sentience.sense(per)
        assert st.get("safety") > 0.5, f"expected high safety, got {st.get('safety')}"
        assert st.get("threat") < 0.3, f"expected low threat, got {st.get('threat')}"

    def test_empty_input(self):
        """空输入：全零感受。"""
        per = self.perception.text_channel.perceive("")
        st = self.sentience.sense(per)
        assert st.get("threat") == 0.0
        assert st.get("safety") == 0.0

    def test_sentiment_state_to_dict(self):
        """感受状态可序列化。"""
        per = self.perception.text_channel.perceive("审批一笔500元的费用")
        st = self.sentience.sense(per)
        d = st.to_dict()
        assert "sentiments" in d
        assert "firing_neurons" in d
        assert isinstance(d["sentiments"], dict)
