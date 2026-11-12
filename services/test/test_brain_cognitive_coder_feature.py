"""test_brain_cognitive_coder_feature.py — 视觉感知特征开放集测试

验证：
- register_feature 动态注册新感知特征（yellow/curved）
- register_concept 自动注册未知特征（banana 的 yellow/curved）
- 视觉新特征识别新概念（黄+弯→banana）
- 特征开放集与概念开放集协同
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import CognitiveCoder, VISUAL_FEATURES


class TestFeatureOpenSet:
    """视觉特征开放集测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_initial_features(self):
        """初始视觉特征 9 个。"""
        assert len(self.coder.visual_snn.feature_names) == 9
        assert "red" in self.coder.visual_snn.feature_names
        assert "dark" in self.coder.visual_snn.feature_names

    def test_register_feature(self):
        """动态注册新特征。"""
        idx = self.coder.register_feature("visual", "yellow")
        assert idx == 9
        assert "yellow" in self.coder.visual_snn.feature_names
        assert self.coder.visual_snn.num_features == 10

    def test_register_existing_feature(self):
        """注册已存在特征返回原索引。"""
        idx = self.coder.register_feature("visual", "red")
        assert idx == 0

    def test_concept_auto_register_features(self):
        """register_concept 自动注册未知特征。"""
        self.coder.register_concept("banana", prior_features={"visual": ["yellow", "curved"]})
        assert "yellow" in self.coder.visual_snn.feature_names
        assert "curved" in self.coder.visual_snn.feature_names
        assert self.coder.visual_snn.num_features == 11

    def test_visual_new_feature_detects_concept(self):
        """视觉新特征识别新概念（黄+弯→banana）。"""
        self.coder.register_concept("banana", prior_features={"visual": ["yellow", "curved"]})
        cv = self.coder.encode(visual={"yellow": 0.9, "curved": 0.9})
        assert cv.concepts.get("banana", 0) > 0.3, f"expected banana, got {cv.concepts}"

    def test_feature_and_concept_open_set(self):
        """特征开放集与概念开放集协同。"""
        self.coder.register_concept("banana", prior_features={"visual": ["yellow", "curved"]})
        self.coder.register_concept("fire", prior_features={"visual": ["red", "bright"]})
        # 香蕉识别
        cv1 = self.coder.encode(visual={"yellow": 0.9, "curved": 0.9})
        assert cv1.concepts.get("banana", 0) > 0.3
        # 火识别（原有特征）
        cv2 = self.coder.encode(visual={"red": 0.9, "bright": 0.9})
        assert cv2.concepts.get("fire", 0) > 0.3

    def test_audio_feature_open_set(self):
        """音频特征开放集。"""
        self.coder.register_feature("audio", "harmony")
        assert "harmony" in self.coder.audio_snn.feature_names
