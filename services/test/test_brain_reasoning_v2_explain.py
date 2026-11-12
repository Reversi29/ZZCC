"""test_brain_reasoning_v2_explain.py — 概念向量可解释性测试

验证：
- reasoning 文本注入主导概念
- dominant(top=3) 按强度排序
- 主导概念为空时不注入（正常业务信号）
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import ConceptVector


class TestConceptExplain:
    """概念向量可解释性测试。"""

    def test_dominant_sorted(self):
        """dominant 按强度降序。"""
        cv = ConceptVector(concepts={"escalation": 0.8, "danger": 0.5, "apple": 0.2})
        dom = cv.dominant(top=3)
        assert dom[0]["concept"] == "escalation"
        assert dom[0]["strength"] == 0.8
        assert dom[1]["concept"] == "danger"

    def test_dominant_filters_low(self):
        """dominant 过滤 <0.05。"""
        cv = ConceptVector(concepts={"apple": 0.9, "novelty": 0.01})
        dom = cv.dominant(top=3)
        assert len(dom) == 1
        assert dom[0]["concept"] == "apple"

    def test_dominant_top_limit(self):
        """dominant top 限制。"""
        cv = ConceptVector(concepts={"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.6})
        dom = cv.dominant(top=2)
        assert len(dom) == 2

    def test_dominant_empty(self):
        """空概念 → 空列表。"""
        cv = ConceptVector(concepts={})
        assert cv.dominant() == []
