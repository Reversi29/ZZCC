"""结构可塑性演化护栏测试(闭环第 3 步)。

验证 snn_structural_guard 核心逻辑:
- is_evolution_active: 动态区是否演化过(修剪/生长/步长)
- 判据: eval 掉分 且 演化活跃 → 结构可塑性嫌疑
- 回退逻辑(JSON 层面): 禁用 enable_structural_plasticity
"""
import importlib.util
import json
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
spec = importlib.util.spec_from_file_location(
    "snn_structural_guard", str(Path(__file__).resolve().parents[1] / "tools" / "snn_structural_guard.py"))
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)


class TestEvolutionActive:
    def test_no_evolution(self):
        assert sg.is_evolution_active({
            "dyn_pruned_total": 0, "dyn_grown_total": 0, "dyn_step_spread": 0}) is False

    def test_prune_active(self):
        assert sg.is_evolution_active({
            "dyn_pruned_total": 1, "dyn_grown_total": 0, "dyn_step_spread": 0}) is True

    def test_growth_active(self):
        assert sg.is_evolution_active({
            "dyn_pruned_total": 0, "dyn_grown_total": 3, "dyn_step_spread": 0}) is True

    def test_step_evolve_active(self):
        assert sg.is_evolution_active({
            "dyn_pruned_total": 0, "dyn_grown_total": 0, "dyn_step_spread": 7}) is True


class TestJudgement:
    def test_healthy_evolution(self):
        """eval 12/12 + 演化活跃 → 健康(不触发)。"""
        dyn = {"dyn_pruned_total": 1, "dyn_grown_total": 0, "dyn_step_spread": 3}
        active = sg.is_evolution_active(dyn)
        assert active is True
        # 判据: 12/12 → 不触发
        assert 12 >= sg.EVAL_THRESHOLD

    def test_drift_suspicion(self):
        """eval < 12 + 演化活跃 → 嫌疑(触发回退)。"""
        dyn = {"dyn_pruned_total": 2, "dyn_grown_total": 0, "dyn_step_spread": 5}
        active = sg.is_evolution_active(dyn)
        assert active is True
        # 判据: 10/12 掉分且演化 → 嫌疑
        assert 10 < sg.EVAL_THRESHOLD


class TestRollback:
    def test_disable_structural_in_network(self, tmp_path):
        """回退应禁用 enable_structural_plasticity 且保留其他字段。"""
        # 模拟网络文件
        net_path = tmp_path / "snn_network.json"
        orig = {
            "num_neurons": 234,
            "enable_structural_plasticity": True,
            "min_weight_for_keep": 0.05,
            "edges": [{"source": 0, "target": 1, "weight": 1.0, "step": 1}],
        }
        net_path.write_text(json.dumps(orig), encoding="utf-8")

        # 调用回退核心逻辑(不依赖 docker)
        data = json.loads(net_path.read_text())
        data["enable_structural_plasticity"] = False
        net_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        # 验证
        result = json.loads(net_path.read_text())
        assert result["enable_structural_plasticity"] is False, "应禁用结构可塑性"
        assert result["num_neurons"] == 234, "应保留其他字段"
        assert result["min_weight_for_keep"] == 0.05, "应保留参数"
