"""test_brain_cognitive_coder_stdp.py — 方向2 STDP/Hebbian 脉冲学习测试

验证：
- distill_step 脉冲前向启用 Hebbian（STDP 时序因果）
- 教师激活概念路径 LTP 加强（特征先激活→概念检测跟随）
- 推理 encode 时 enable_hebbian=False（防意外 LTD）
- 蒸馏后教师概念保持高激活
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import (
    ModalSNNEncoder, _VISUAL_CONCEPT_PRIOR, VISUAL_FEATURES,
)


class TestSTDP:
    """STDP 脉冲学习测试。"""

    def setup_method(self):
        self.enc = ModalSNNEncoder("visual", VISUAL_FEATURES, _VISUAL_CONCEPT_PRIOR)

    def test_stdp_ltp_strengthens(self):
        """STDP LTP：教师激活概念路径加强。"""
        apple_hid = self.enc._hidden_start + self.enc.registry.get("apple")
        red_idx = VISUAL_FEATURES.index("red")
        before = self.enc._get_weight(red_idx, apple_hid)
        for _ in range(10):
            self.enc.distill_step({"red": 0.9, "round": 0.9}, {"apple": 0.9}, eta=0.05)
        after = self.enc._get_weight(red_idx, apple_hid)
        assert after > before, f"STDP LTP expected, before={before} after={after}"

    def test_inference_hebbian_disabled(self):
        """推理时 enable_hebbian=False（防意外 LTD）。"""
        self.enc.encode({"red": 0.9, "round": 0.9})
        assert self.enc.snn.enable_hebbian is False

    def test_distill_keeps_teacher_active(self):
        """蒸馏后教师概念保持高激活。"""
        for _ in range(5):
            self.enc.distill_step({"red": 0.9, "round": 0.9}, {"apple": 0.9}, eta=0.05)
        cv = self.enc.encode({"red": 0.9, "round": 0.9})
        assert cv.get("apple", 0) > 0.3, f"apple should stay active, got {cv}"
