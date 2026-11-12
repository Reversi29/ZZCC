"""test_brain_cognitive_coder_open.py — 概念空间开放集测试

验证 ConceptRegistry 动态注册：
- 初始固定概念（10 个）
- register 新概念分配新维度（banana/fire）
- 别名注册（中文"香蕉"/"火焰"→规范概念）
- 文本识别动态概念（中文别名→概念激活）
- 视觉 SNN 新概念激活（fire 红+亮）
- 隐藏层/输出层不重叠（架构修复）
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import (
    CognitiveCoder,
    ConceptRegistry,
    CONCEPT_NAMES,
)


class TestConceptRegistry:
    """概念注册表测试。"""

    def test_initial_concepts(self):
        """初始固定概念 10 个。"""
        reg = ConceptRegistry()
        assert len(reg) == 10
        assert reg.get("apple") == 0
        assert reg.get("novelty") == 9

    def test_register_new(self):
        """动态注册新概念分配新维度。"""
        reg = ConceptRegistry()
        idx = reg.register("banana")
        assert idx == 10
        assert reg.get("banana") == 10
        assert len(reg) == 11

    def test_register_existing(self):
        """注册已存在概念返回原索引。"""
        reg = ConceptRegistry()
        idx = reg.register("apple")
        assert idx == 0
        assert len(reg) == 10

    def test_aliases(self):
        """别名注册与解析。"""
        reg = ConceptRegistry()
        reg.register("banana", aliases=["香蕉"])
        assert reg.resolve("香蕉") == "banana"
        assert reg.resolve("banana") == "banana"

    def test_dynamic_concepts_multiple(self):
        """多概念动态注册。"""
        reg = ConceptRegistry()
        reg.register("banana")
        reg.register("fire")
        assert len(reg) == 12
        assert reg.get("banana") == 10
        assert reg.get("fire") == 11


class TestCognitiveCoderOpen:
    """CognitiveCoder 概念开放集测试。"""

    def setup_method(self):
        self.coder = CognitiveCoder()

    def test_register_concept(self):
        """CognitiveCoder.register_concept 分配新维度。"""
        idx = self.coder.register_concept("banana", aliases=["香蕉"])
        assert idx == 10
        assert self.coder.registry.get("banana") == 10

    def test_text_chinese_alias(self):
        """中文别名文本→概念激活。"""
        self.coder.register_concept("banana", aliases=["香蕉"])
        cv = self.coder.encode(text="我买了一个香蕉")
        assert cv.concepts.get("banana", 0) > 0.3, f"expected banana, got {cv.concepts}"

    def test_visual_new_concept(self):
        """视觉 SNN 新概念激活（fire 红+亮）。"""
        self.coder.register_concept("fire", prior_features={"visual": ["red", "bright"]})
        cv = self.coder.encode(visual={"red": 0.9, "bright": 0.9})
        assert cv.concepts.get("fire", 0) > 0.3, f"expected fire, got {cv.concepts}"

    def test_hidden_output_no_overlap(self):
        """隐藏层/输出层不重叠（架构修复）。"""
        self.coder.register_concept("banana")
        self.coder.register_concept("fire")
        vs = self.coder.visual_snn
        # 输出层起始 ≥ 隐藏层起始 + 概念数
        assert vs._output_start >= vs._hidden_start + len(self.coder.registry), \
            f"output_start={vs._output_start} < hidden_start+count={vs._hidden_start + len(self.coder.registry)}"

    def test_concept_count_grows(self):
        """概念数动态增长。"""
        self.coder.register_concept("banana")
        self.coder.register_concept("fire")
        assert len(self.coder.registry) == 12
        # 视觉 SNN 神经元扩展
        assert self.coder.visual_snn.num_neurons > 29

    def test_fixed_concepts_unchanged(self):
        """固定概念不受动态注册影响。"""
        self.coder.register_concept("banana")
        cv = self.coder.encode(text="苹果")
        assert cv.concepts.get("apple", 0) > 0.3, f"expected apple, got {cv.concepts}"
