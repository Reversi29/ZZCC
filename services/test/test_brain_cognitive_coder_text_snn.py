"""test_brain_cognitive_coder_text_snn.py — 文本模态 SNN（三模态对称）测试

验证：
- text_snn 三模态对称（visual/audio/text 各有 SNN）
- _text_to_features 低层语义特征提取
- text_snn.encode 低层特征→概念（SNN 学习）
- 跨模态对齐：文本苹果 vs 视觉苹果同概念
- text 蒸馏训练（_text_to_concepts 教师）
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import (
    CognitiveCoder, _text_to_features, TEXT_FEATURES,
)


class TestTextSNN:
    """文本模态 SNN 测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_three_modal_symmetric(self):
        """三模态对称：visual/audio/text 各有 SNN。"""
        assert hasattr(self.coder, "visual_snn")
        assert hasattr(self.coder, "audio_snn")
        assert hasattr(self.coder, "text_snn")
        assert self.coder.text_snn.num_features == len(TEXT_FEATURES)

    def test_text_features(self):
        """文本低层特征提取。"""
        feats = _text_to_features("紧急审批 5000元")
        assert feats.get("urgent_marker", 0) > 0.5
        assert feats.get("approval_marker", 0) > 0.5
        assert feats.get("has_number", 0) > 0.5

    def test_text_snn_encodes(self):
        """text_snn 低层特征→概念。"""
        feats = _text_to_features("紧急加急")
        cv = self.coder.text_snn.encode(feats)
        assert cv.get("urgency", 0) > 0.1, f"expected urgency, got {cv}"

    def test_cross_modal_apple_alignment(self):
        """跨模态对齐：文本苹果 vs 视觉苹果同概念。"""
        text_cv = self.coder.encode(text="苹果")
        vis_cv = self.coder.encode(visual={"red": 0.9, "round": 0.9})
        assert text_cv.concepts.get("apple", 0) > 0.3
        assert vis_cv.concepts.get("apple", 0) > 0.3

    def test_text_distill(self):
        """文本蒸馏训练（_text_to_concepts 教师）。"""
        samples = [{"text": "紧急审批设备", "concepts": {"urgency": 0.9}}]
        stats = self.coder.train_supervised(samples, eta=0.1)
        assert stats["text"] == 1

    def test_text_snn_learns(self):
        """文本 SNN 蒸馏学习加强概念路径。"""
        feats = _text_to_features("紧急设备采购")
        before = self.coder.text_snn.encode(feats)
        samples = [{"text": "紧急设备采购", "concepts": {"urgency": 0.9}}]
        self.coder.train_supervised(samples, eta=0.1)
        after = self.coder.text_snn.encode(feats)
        assert after.get("urgency", 0) >= before.get("urgency", 0), \
            f"urgency should not decrease, before={before.get('urgency')} after={after.get('urgency')}"
