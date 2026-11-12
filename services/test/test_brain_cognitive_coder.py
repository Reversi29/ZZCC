"""test_brain_cognitive_coder.py — 多模态认知编码器测试

验证 CognitiveCoder 的多模态对齐：
- 视觉"苹果"与文字"苹果" → 同一概念 apple
- 不同模态对同一概念激活 → 统一概念向量
- 结构化字段（金额/风险）→ 概念
- 概念向量 → 感受层输入映射
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import (
    CognitiveCoder,
    ConceptVector,
    CONCEPT_NAMES,
    CONCEPT_DIMS,
)


class TestCognitiveCoder:
    """认知编码器测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_concept_dims(self):
        """概念维度固定且命名完整。"""
        assert CONCEPT_DIMS == len(CONCEPT_NAMES)
        assert "apple" in CONCEPT_NAMES
        assert "danger" in CONCEPT_NAMES

    def test_text_apple(self):
        """文字"苹果" → apple 概念激活。"""
        cv = self.coder.encode(text="我要一个苹果")
        assert cv.concepts.get("apple", 0) > 0.5, f"expected apple, got {cv.concepts}"

    def test_visual_apple(self):
        """视觉（红+圆）→ apple 概念激活。"""
        cv = self.coder.encode(visual={"red": 0.8, "green": 0.2, "round": 0.9})
        assert cv.concepts.get("apple", 0) > 0.3, f"expected apple, got {cv.concepts}"

    def test_visual_text_alignment(self):
        """视觉苹果与文字苹果 → 同一概念 apple（多模态对齐）。

        这是认知对齐的核心：不同模态对同一概念的激活收敛到统一概念。
        """
        visual_cv = self.coder.encode(visual={"red": 0.9, "round": 0.9})
        text_cv = self.coder.encode(text="苹果")
        # 两个模态都应激活 apple
        assert visual_cv.concepts.get("apple", 0) > 0.3
        assert text_cv.concepts.get("apple", 0) > 0.5
        # 概念向量接近（对齐到同一概念维度）
        assert visual_cv.concepts.get("apple", 0) > 0
        assert text_cv.concepts.get("apple", 0) > 0
        # 模态来源都应记录 apple
        assert "apple" in visual_cv.modality_sources
        assert "apple" in text_cv.modality_sources

    def test_multi_modal_alignment_strength(self):
        """多模态同概念 → 对齐强度高。"""
        cv = self.coder.encode(
            text="危险 紧急",
            visual={"red": 0.8, "dark": 0.7},
        )
        # 视觉红+暗 → danger；文本危险 → danger。跨模态同概念。
        assert cv.concepts.get("danger", 0) > 0.3, f"expected danger, got {cv.concepts}"
        # 对齐强度 > 0（多模态对齐发生）
        assert self.coder._stats["alignment_strength"] > 0

    def test_structured_amount_concept(self):
        """结构化金额 88000 → escalation + danger 概念。"""
        cv = self.coder.encode(payload={"amount": 88000, "category": "equipment"})
        assert cv.concepts.get("escalation", 0) > 0.5, f"expected escalation, got {cv.concepts}"

    def test_structured_risk_concept(self):
        """结构化风险 critical → danger + urgency 概念。"""
        cv = self.coder.encode(payload={"amount": 5000, "risk_level": "critical"})
        assert cv.concepts.get("danger", 0) > 0.5, f"expected danger, got {cv.concepts}"
        assert cv.concepts.get("urgency", 0) > 0.5, f"expected urgency, got {cv.concepts}"

    def test_chitchat_concept(self):
        """闲聊 → chitchat 概念。"""
        cv = self.coder.encode(text="你好呀 哈哈")
        assert cv.concepts.get("chitchat", 0) > 0.3, f"expected chitchat, got {cv.concepts}"

    def test_to_sentience_input(self):
        """概念向量 → 感受输入映射。"""
        cv = self.coder.encode(text="危险 紧急")
        sent_input = self.coder.to_sentience_input(cv)
        # danger → threat, urgency → urgency
        assert sent_input.get("threat", 0) > 0.5, f"expected threat, got {sent_input}"
        assert sent_input.get("urgency", 0) > 0.5, f"expected urgency, got {sent_input}"

    def test_dominant_concepts(self):
        """主导概念提取。"""
        cv = self.coder.encode(text="苹果 危险 紧急")
        dominant = cv.dominant(top=3)
        assert len(dominant) > 0
        # 至少一个概念强度 > 0.5
        assert any(d["strength"] > 0.5 for d in dominant)

    def test_to_vector(self):
        """概念向量转固定维度。"""
        cv = self.coder.encode(text="苹果")
        vec = cv.to_vector()
        assert len(vec) == CONCEPT_DIMS
        # apple 索引激活
        assert vec[CONCEPT_NAMES.index("apple")] > 0.5

    def test_empty_input(self):
        """空输入 → 空概念。"""
        cv = self.coder.encode()
        assert cv.concepts == {} or all(v < 0.05 for v in cv.concepts.values())
