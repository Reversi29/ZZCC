"""test_brain_cognitive_coder_learn.py — 概念层持续学习测试

验证 CognitiveCoder.learn_from_feedback：
- 决策反馈→概念教师映射（approve→approval, escalate→escalation）
- 突触发生：无先验特征概念建立特征→概念连接
- 反馈驱动视觉/音频 SNN 概念路径加强
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import CognitiveCoder


class TestLearnFromFeedback:
    """概念层持续学习测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_escalate_feedback_strengthens(self):
        """escalate 反馈 → 视觉 escalation 概念加强（突触发生）。"""
        before = self.coder.visual_snn.encode({"red": 0.9, "bright": 0.9})
        for _ in range(5):
            self.coder.learn_from_feedback(
                visual={"red": 0.9, "bright": 0.9}, correct_decision="escalate", eta=0.1
            )
        after = self.coder.visual_snn.encode({"red": 0.9, "bright": 0.9})
        assert after.get("escalation", 0) > before.get("escalation", 0), \
            f"escalation should strengthen, before={before.get('escalation')} after={after.get('escalation')}"

    def test_approve_feedback_strengthens(self):
        """auto_approve 反馈 → 视觉 approval 概念加强。"""
        before = self.coder.visual_snn.encode({"red": 0.9, "round": 0.9})
        for _ in range(5):
            self.coder.learn_from_feedback(
                visual={"red": 0.9, "round": 0.9}, correct_decision="auto_approve", eta=0.1
            )
        after = self.coder.visual_snn.encode({"red": 0.9, "round": 0.9})
        assert after.get("approval", 0) > before.get("approval", 0), \
            f"approval should strengthen, before={before.get('approval')} after={after.get('approval')}"

    def test_audio_feedback(self):
        """音频反馈 → 音频概念加强。"""
        before = self.coder.audio_snn.encode({"loudness": 0.9, "pitch": 0.8})
        for _ in range(5):
            self.coder.learn_from_feedback(
                audio={"loudness": 0.9, "pitch": 0.8}, correct_decision="escalate", eta=0.1
            )
        after = self.coder.audio_snn.encode({"loudness": 0.9, "pitch": 0.8})
        assert after.get("escalation", 0) > 0.1, f"expected escalation, got {after}"

    def test_no_decision_skip(self):
        """无决策反馈 → 跳过。"""
        stats = self.coder.learn_from_feedback(
            visual={"red": 0.9, "round": 0.9}, correct_decision="", eta=0.1
        )
        assert stats["visual"] == 0
        assert stats["audio"] == 0

    def test_unknown_decision_skip(self):
        """未知决策 → 跳过。"""
        stats = self.coder.learn_from_feedback(
            visual={"red": 0.9, "round": 0.9}, correct_decision="weird_decision", eta=0.1
        )
        assert stats["visual"] == 0

    def test_synaptogenesis(self):
        """突触发生：无先验特征概念建立特征→概念连接。"""
        vs = self.coder.visual_snn
        esc_cidx = self.coder.registry.get("escalation")
        esc_hid = vs._hidden_start + esc_cidx
        # 反馈前 escalation 无输入连接
        self.coder.learn_from_feedback(
            visual={"red": 0.9, "bright": 0.9}, correct_decision="escalate", eta=0.1
        )
        # 反馈后 red/bright→escalation 连接存在
        red_idx = vs.feature_names.index("red")
        assert vs._get_weight(red_idx, esc_hid) > 0, "red→escalation should exist"
