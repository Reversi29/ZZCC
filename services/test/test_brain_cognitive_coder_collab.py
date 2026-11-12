"""test_brain_cognitive_coder_collab.py — 方向3 多 SNN 协同推理测试

验证：
- 多模态交叉验证：同概念 2+ 模态激活 → 共识提升
- 模态来源记录（sources 含各模态）
- 冲突仲裁：不同模态不同概念 → 保留两概念（取高，不压制）
- 单模态不提升（n=1 无系数）
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import CognitiveCoder


class TestCollab:
    """多 SNN 协同推理测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_multi_modal_sources(self):
        """多模态来源记录。"""
        cv = self.coder.encode(visual={"red": 0.9, "round": 0.9}, text="苹果")
        assert cv.modality_sources.get("apple", []) == ["text", "visual"]

    def test_single_modal_no_boost(self):
        """单模态无提升系数（n=1）。"""
        cv = self.coder.encode(text="苹果")
        assert len(cv.modality_sources.get("apple", [])) == 1

    def test_conflict_keeps_both(self):
        """冲突：视觉苹果 + 文本危险 → 保留两概念。"""
        cv = self.coder.encode(visual={"red": 0.9, "round": 0.9}, text="危险")
        assert cv.concepts.get("apple", 0) > 0.3
        assert cv.concepts.get("danger", 0) > 0.3

    def test_alignment_strength_tracks(self):
        """对齐强度：多模态同概念提升。"""
        cv = self.coder.encode(visual={"red": 0.9, "round": 0.9}, text="苹果")
        assert self.coder._stats.get("alignment_strength", 0) > 0
