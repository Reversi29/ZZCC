"""test_brain_cognitive_coder_feedback_accum.py — 真实标注数据积累测试

验证：
- learn_from_feedback 积累训练样本
- 达到批量阈值自动 train_supervised
- 积累样本含 visual/audio/text + concepts 标签
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import CognitiveCoder


class TestFeedbackAccum:
    """反馈数据积累测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_accumulate_sample(self):
        """积累单样本。"""
        r = self.coder._accumulate_feedback_sample(
            visual={"red": 0.9, "round": 0.9}, decision_concept="approval"
        )
        assert r["accumulated"] == 1
        assert len(self.coder._pending_training_samples) == 1
        sample = self.coder._pending_training_samples[0]
        assert sample["concepts"] == {"approval": 0.9}
        assert "visual" in sample

    def test_no_accumulate_without_concept(self):
        """无概念 → 不积累。"""
        r = self.coder._accumulate_feedback_sample(visual={"red": 0.9}, decision_concept="")
        assert r["accumulated"] == 0
        assert len(self.coder._pending_training_samples) == 0

    def test_batch_auto_train(self):
        """达到批量阈值自动训练。"""
        self.coder._training_batch_size = 2
        r1 = self.coder._accumulate_feedback_sample(
            visual={"red": 0.9, "round": 0.9}, decision_concept="approval"
        )
        assert r1["trained"] == 0
        r2 = self.coder._accumulate_feedback_sample(
            audio={"loudness": 0.9, "pitch": 0.8}, decision_concept="escalation"
        )
        assert r2["trained"] > 0, f"expected auto-train, got {r2}"
        # 训练后清空
        assert len(self.coder._pending_training_samples) == 0

    def test_learn_feedback_accumulates(self):
        """learn_from_feedback 积累样本。"""
        self.coder.learn_from_feedback(visual={"red": 0.9, "round": 0.9}, correct_decision="approve")
        assert len(self.coder._pending_training_samples) == 1
        sample = self.coder._pending_training_samples[0]
        assert sample["concepts"] == {"approval": 0.9}
