"""test_brain_cognitive_coder_contrastive.py — 对比学习对齐测试

验证 CognitiveCoder.contrastive_align（InfoNCE 风格跨模态对齐）：
- 正对：跨模态同概念 → 加强该概念路径（拉近）
- 负对：跨模态不同概念 → 削弱误激活路径（推远）
- 纯视觉 SNN 净效应（无文本干扰）
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import (
    CognitiveCoder,
    ModalSNNEncoder,
    VISUAL_FEATURES,
    _VISUAL_CONCEPT_PRIOR,
)


class TestContrastiveAlign:
    """对比学习对齐测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_positive_align_strengthens(self):
        """正对（视觉苹果+文本苹果）→ 视觉 apple 路径加强、danger 抑制。"""
        # 纯视觉 SNN 净效应
        vs = ModalSNNEncoder("visual", VISUAL_FEATURES, _VISUAL_CONCEPT_PRIOR)
        before = vs.encode({"red": 0.9, "round": 0.9})
        # 正对教师：apple 强、danger 弱
        for _ in range(15):
            vs.distill_step({"red": 0.9, "round": 0.9}, {"apple": 0.9, "danger": 0.0}, eta=0.05)
        after = vs.encode({"red": 0.9, "round": 0.9})
        # apple 保持高，danger 被抑制（正对拉近 apple、推远 danger）
        assert after.get("apple", 0) > 0.3, f"apple should stay high, got {after}"
        assert after.get("danger", 0) < before.get("danger", 0), \
            f"danger should be suppressed, before={before.get('danger')} after={after.get('danger')}"

    def test_negative_align_strengthens(self):
        """负对（视觉苹果 vs 文本危险）→ 视觉 danger 路径加强。"""
        vs = ModalSNNEncoder("visual", VISUAL_FEATURES, _VISUAL_CONCEPT_PRIOR)
        before = vs.encode({"red": 0.9, "round": 0.9})
        # 负对教师：danger 强
        for _ in range(15):
            vs.distill_step({"red": 0.9, "round": 0.9}, {"apple": 0.0, "danger": 0.9}, eta=0.05)
        after = vs.encode({"red": 0.9, "round": 0.9})
        assert after.get("danger", 0) > before.get("danger", 0), \
            f"danger should strengthen, before={before.get('danger')} after={after.get('danger')}"

    def test_contrastive_align_integration(self):
        """contrastive_align() 集成：正对样本更新视觉/音频 SNN。"""
        samples_pos = [{"visual": {"red": 0.9, "round": 0.9}, "text": "苹果"}]
        stats = self.coder.contrastive_align(samples_pos, eta=0.05)
        assert stats["visual"] == 1, f"expected visual align, got {stats}"
        assert self.coder._stats.get("contrastive_calls", 0) == 1

    def test_contrastive_no_modal_skip(self):
        """无多模态 → 对比学习跳过（无软教师）。"""
        samples = [{"text": "苹果"}]
        stats = self.coder.contrastive_align(samples, eta=0.05)
        assert stats["visual"] == 0
        assert stats["audio"] == 0

    def test_cross_modal_consistency(self):
        """跨模态一致性：视觉+文本同概念 → 对齐强度提升。"""
        cv = self.coder.encode(
            visual={"red": 0.9, "round": 0.9},
            text="苹果",
        )
        assert cv.concepts.get("apple", 0) > 0.3, f"expected apple, got {cv.concepts}"
        # 模态来源应含 visual + text
        sources = cv.modality_sources.get("apple", [])
        assert "visual" in sources and "text" in sources, f"expected visual+text, got {sources}"
