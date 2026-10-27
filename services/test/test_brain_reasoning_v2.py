"""test_brain_reasoning_v2.py — 认知层 v2 单元测试

验证感知→感受→认知→决策链路与诚意检查。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

import tempfile

from models.brain import CognitionResult, NeuralSignal
from services.brain.perception import Perception
from services.brain.sentience import SentienceNet, SentienceDrivenBudget
from services.brain.reasoning_v2 import ReasoningEngineV2


class TestReasoningV2:
    """v2 认知层测试。"""

    def test_perception_sentience_chain(self):
        """感知→感受链路：高风险审批→高威胁。"""
        perception = Perception()
        tmpdir = tempfile.mkdtemp()
        sentience = SentienceNet(path=os.path.join(tmpdir, "sent.json"))
        per = perception.text_channel.perceive("审批一笔88000元的设备采购费用，供应商风险高")
        st = sentience.sense(per)
        assert st.get("threat") > 0.5, "高风险应产生高威胁"
        assert st.get("urgency") > 0.5, "高风险应产生高紧迫感"

    def test_sentience_budget_high_threat(self):
        """高威胁预算：激活 rule/llm/snn。"""
        budget = SentienceDrivenBudget(None)
        plan = budget.allocate({"threat": 0.9, "urgency": 0.8})
        assert "snn" in plan
        assert plan["snn"].allowed, "高威胁应激活 SNN"
        assert plan["llm"].allowed, "高威胁应激活 LLM"

    def test_sentience_budget_chitchat(self):
        """闲聊感受：禁 SNN（避免误审批）。"""
        budget = SentienceDrivenBudget(None)
        plan = budget.allocate({"safety": 0.7, "threat": 0.0})
        assert "snn" in plan
        assert not plan["snn"].allowed, "闲聊应禁 SNN"

    def test_validate_consistency_threat_but_approved(self):
        """诚意检查：threat 高但 auto_approve → 标记不一致。"""
        v2 = ReasoningEngineV2.__new__(ReasoningEngineV2)
        v2._stats = {"v2_calls": 0, "consistency_flags": 0}
        result = CognitionResult(
            reasoning_level=3,
            confidence=0.9,
            decision="auto_approve",
            reasoning="test",
        )
        sentiments = {"threat": 0.9, "safety": 0.0, "confusion": 0.0, "urgency": 0.8}
        out = v2._validate_consistency(result, sentiments, NeuralSignal(type="expense"))
        assert "consistency" in out.memory_updates
        assert "threat_but_approved" in out.memory_updates["consistency"]["flags"]
        assert out.confidence < 0.9, "不一致应降低置信度"

    def test_validate_consistency_consistent(self):
        """诚意检查：threat 高且 escalate → 无标记。"""
        v2 = ReasoningEngineV2.__new__(ReasoningEngineV2)
        v2._stats = {"v2_calls": 0, "consistency_flags": 0}
        result = CognitionResult(
            reasoning_level=3,
            confidence=0.9,
            decision="escalate",
            reasoning="test",
        )
        sentiments = {"threat": 0.9, "safety": 0.0, "confusion": 0.0, "urgency": 0.8}
        out = v2._validate_consistency(result, sentiments, NeuralSignal(type="threshold_breach"))
        assert "consistency" not in out.memory_updates, "一致决策不应标记"

    def test_has_significant_sentiment(self):
        """感受显著判断。"""
        v2 = ReasoningEngineV2.__new__(ReasoningEngineV2)
        assert v2._has_significant_sentiment({"threat": 0.5}) is True
        assert v2._has_significant_sentiment({"threat": 0.1}) is False
        assert v2._has_significant_sentiment({}) is False
