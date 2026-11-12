"""test_brain_cognitive_coder_snn_instance.py — ModalSNNEncoder 完整 SNN 实例测试

验证（升级：轻量脉冲模型 → 完整 snn.py SNN 实例）：
- 真正脉冲动力学：inject → step 传播 → get_outputs
- AND 门：多特征概念需≥2 特征放电（单特征不误激活）
- 单特征概念（novelty）权重 1.5 可放电
- 蒸馏：无先验特征概念突触发生（新连接）
- 开放集：register_concept 扩展完整 SNN 拓扑
- 推理时 enable_hebbian=False（防意外 LTD）
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import (
    ModalSNNEncoder, _VISUAL_CONCEPT_PRIOR, VISUAL_FEATURES,
)


class TestSNNInstance:
    """ModalSNNEncoder 完整 SNN 实例测试。"""

    def setup_method(self):
        self.enc = ModalSNNEncoder("visual", VISUAL_FEATURES, _VISUAL_CONCEPT_PRIOR)

    def test_has_snn_instance(self):
        """编码器持有完整 SNN 实例。"""
        assert hasattr(self.enc, "snn")
        assert len(self.enc.snn.neurons) == self.enc.num_neurons

    def test_pulse_propagation(self):
        """脉冲动力学：特征放电 → 概念检测 → 输出。"""
        self.enc.snn.enable_hebbian = False
        self.enc.snn.inject_input(VISUAL_FEATURES.index("red"), 0.9)
        self.enc.snn.inject_input(VISUAL_FEATURES.index("round"), 0.9)
        # 应有多步传播（非单步直接映射）
        fired_steps = []
        for _ in range(5):
            self.enc.snn.step()
            fired_steps.append(len(self.enc.snn.get_active_neurons()))
        assert sum(fired_steps) > 2, f"expected multi-step propagation, got {fired_steps}"

    def test_and_gate(self):
        """AND 门：多特征概念需≥2 特征放电。"""
        # 红+圆 → apple（2 特征）
        assert self.enc.encode({"red": 0.9, "round": 0.9}).get("apple", 0) > 0.3
        # 红单 → 不激活（AND 门抑制共享特征误激活）
        assert "apple" not in self.enc.encode({"red": 0.9})

    def test_single_feature_concept(self):
        """单特征概念（novelty）权重 1.5 可放电。"""
        assert self.enc.encode({"bright": 0.9}).get("novelty", 0) > 0.3

    def test_hebbian_disabled_inference(self):
        """推理时 enable_hebbian=False（防意外 LTD）。"""
        self.enc.encode({"red": 0.9, "round": 0.9})
        assert self.enc.snn.enable_hebbian is False

    def test_open_set_grows(self):
        """开放集：register_concept 扩展完整 SNN 拓扑。"""
        before = self.enc.num_neurons
        self.enc.register_concept("fire", ["red", "bright"])
        assert self.enc.num_neurons > before
        # 新概念可激活
        cv = self.enc.encode({"red": 0.9, "bright": 0.9})
        assert cv.get("fire", 0) > 0.3, f"expected fire, got {cv}"
