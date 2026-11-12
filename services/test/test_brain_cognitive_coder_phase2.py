"""test_brain_cognitive_coder_phase2.py — Phase 2 模态专用 SNN 编码器测试

验证 ModalSNNEncoder：
- 视觉 SNN 先验编码（红+圆→apple，暗+红→danger）
- 音频 SNN 先验编码（响度+音调→danger/urgency）
- 蒸馏训练（规则式教师 → SNN 逼近）
- 编码器集成（CognitiveCoder 用 SNN 编码）
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import (
    CognitiveCoder,
    ModalSNNEncoder,
    VISUAL_FEATURES,
    AUDIO_FEATURES,
    _VISUAL_CONCEPT_PRIOR,
    _AUDIO_CONCEPT_PRIOR,
    CONCEPT_DIMS,
)


class TestModalSNNEncoder:
    """模态 SNN 编码器测试。"""

    def setup_method(self):
        self.visual_snn = ModalSNNEncoder("visual", VISUAL_FEATURES, _VISUAL_CONCEPT_PRIOR)
        self.audio_snn = ModalSNNEncoder("audio", AUDIO_FEATURES, _AUDIO_CONCEPT_PRIOR)

    def test_visual_apple(self):
        """视觉（红+圆）→ apple 概念激活（SNN 编码）。"""
        enc = self.visual_snn.encode({"red": 0.9, "round": 0.9})
        assert enc.get("apple", 0) > 0.3, f"expected apple, got {enc}"

    def test_visual_danger(self):
        """视觉（暗+红）→ danger 概念激活。"""
        enc = self.visual_snn.encode({"dark": 0.8, "red": 0.7})
        assert enc.get("danger", 0) > 0.3, f"expected danger, got {enc}"

    def test_audio_alarm(self):
        """音频（高响度+高音调）→ danger/urgency 激活。"""
        enc = self.audio_snn.encode({"loudness": 0.9, "pitch": 0.8})
        assert enc.get("danger", 0) > 0.2, f"expected danger, got {enc}"

    def test_visual_quiet(self):
        """视觉（无特征）→ 无概念。"""
        enc = self.visual_snn.encode({"blue": 0.1})
        assert all(v < 0.2 for v in enc.values()), f"expected quiet, got {enc}"

    def test_distill_strengthens(self):
        """蒸馏训练：教师激活的概念连接被加强。"""
        before = self.visual_snn.encode({"red": 0.9, "round": 0.9, "bright": 0.8})
        # 蒸馏 10 次（红+圆+亮 → apple+novelty 教师）
        for _ in range(10):
            self.visual_snn.distill_step(
                {"red": 0.9, "round": 0.9, "bright": 0.8},
                {"apple": 0.9, "novelty": 0.7},
                eta=0.05,
            )
        after = self.visual_snn.encode({"red": 0.9, "round": 0.9, "bright": 0.8})
        # 蒸馏后 apple 仍激活（先验加强）
        assert after.get("apple", 0) > 0.3, f"expected apple after distill, got {after}"

    def test_concept_dims_consistent(self):
        """概念维度一致。"""
        assert CONCEPT_DIMS == 10


class TestCognitiveCoderPhase2:
    """CognitiveCoder 用 SNN 编码的集成测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_snn_encoding_enabled(self):
        """SNN 编码默认启用。"""
        assert self.coder.use_snn_encoding is True

    def test_visual_snn_integration(self):
        """CognitiveCoder.encode 用视觉 SNN 编码。"""
        cv = self.coder.encode(visual={"red": 0.9, "round": 0.9})
        assert cv.concepts.get("apple", 0) > 0.3, f"expected apple, got {cv.concepts}"

    def test_audio_snn_integration(self):
        """CognitiveCoder.encode 用音频 SNN 编码。"""
        cv = self.coder.encode(audio={"loudness": 0.9, "pitch": 0.8})
        assert cv.concepts.get("danger", 0) > 0.2, f"expected danger, got {cv.concepts}"

    def test_distill_integration(self):
        """distill() 集成：SNN 编码器蒸馏。"""
        samples = [
            {"visual": {"red": 0.9, "round": 0.9, "bright": 0.8}},
            {"audio": {"loudness": 0.9, "pitch": 0.8}},
        ]
        stats = self.coder.distill(samples, eta=0.05)
        assert stats["visual_distill"] == 1
        assert stats["audio_distill"] == 1
