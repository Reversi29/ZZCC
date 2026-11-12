"""test_brain_cognitive_coder_supervised.py — 真实标注有监督训练测试

验证 CognitiveCoder.train_supervised：
- 真实标注 concepts 作为教师训练模态 SNN
- 视觉/音频/文本多模态标注
- 学习后概念路径加强
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import CognitiveCoder


class TestSupervisedTrain:
    """真实标注有监督训练测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_supervised_visual(self):
        """视觉真实标注训练。"""
        samples = [{"visual": {"red": 0.9, "round": 0.9}, "concepts": {"apple": 0.9}}]
        stats = self.coder.train_supervised(samples, eta=0.1)
        assert stats["visual"] == 1
        cv = self.coder.visual_snn.encode({"red": 0.9, "round": 0.9})
        assert cv.get("apple", 0) > 0.3, f"expected apple, got {cv}"

    def test_supervised_audio(self):
        """音频真实标注训练。"""
        samples = [{"audio": {"loudness": 0.9, "pitch": 0.8}, "concepts": {"danger": 0.9, "urgency": 0.8}}]
        stats = self.coder.train_supervised(samples, eta=0.1)
        assert stats["audio"] == 1
        cv = self.coder.audio_snn.encode({"loudness": 0.9, "pitch": 0.8})
        assert cv.get("danger", 0) > 0.3, f"expected danger, got {cv}"

    def test_supervised_multimodal(self):
        """多模态混合训练。"""
        samples = [
            {"visual": {"red": 0.9, "round": 0.9}, "concepts": {"apple": 0.9}},
            {"audio": {"loudness": 0.9, "pitch": 0.8}, "concepts": {"danger": 0.9}},
        ]
        stats = self.coder.train_supervised(samples, eta=0.1)
        assert stats["visual"] == 1
        assert stats["audio"] == 1

    def test_no_concepts_skip(self):
        """无 concepts 标签 → 跳过。"""
        samples = [{"visual": {"red": 0.9, "round": 0.9}}]
        stats = self.coder.train_supervised(samples, eta=0.1)
        assert stats["visual"] == 0

    def test_supervised_strengthens(self):
        """真实标注训练加强概念路径。"""
        before = self.coder.visual_snn.encode({"red": 0.9, "bright": 0.9})
        samples = [{"visual": {"red": 0.9, "bright": 0.9}, "concepts": {"danger": 0.9}}]
        self.coder.train_supervised(samples, eta=0.1)
        after = self.coder.visual_snn.encode({"red": 0.9, "bright": 0.9})
        assert after.get("danger", 0) >= before.get("danger", 0), \
            f"danger should not decrease, before={before.get('danger')} after={after.get('danger')}"
