"""动态区演化监控测试：结构可塑性是否健康演化。

验证 _update_dyn_evolution_stats 正确统计动态区(≥40):
- 边数/步长展布/步长种类
- 修剪(边减少)/生长(边增加)检测
- 累计总量
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

from services.brain.snn_region import SNNRegion


def _make_region(tmp_path):
    region = SNNRegion(save_path=str(tmp_path / "s.json"))
    # create_default 是 40 神经元(0-39), 动态区≥40 需运行时注册/扩展
    # 测试里显式扩展神经元到 60, 模拟生产运行时动态注册后的状态
    for nid in range(40, 60):
        if nid >= region.snn.num_neurons:
            region.snn.add_neuron(nid)
    return region


class TestDynEvolutionStats:
    def test_initial_stats_fields(self, tmp_path):
        """初始 stats 应有动态区演化字段。"""
        region = _make_region(tmp_path)
        for k in ("dyn_edges", "dyn_step_spread", "dyn_step_distinct",
                  "dyn_pruned", "dyn_grown", "dyn_last_updated"):
            assert k in region._stats, f"缺失字段 {k}"

    def test_stats_after_feedback(self, tmp_path):
        """训练反馈后动态区统计更新。"""
        from models.brain import NeuralSignal
        region = _make_region(tmp_path)
        sig = NeuralSignal(id="t1", type="expense", payload={"amount": 500},
                           source="test", urgency=50)
        region.train_from_feedback(sig, "auto_approve", True, wrong_decision=None)
        # 训练后应统计到动态区(≥40)边
        assert region._stats["dyn_edges"] >= 0, "动态区边数应为非负"
        assert region._stats["dyn_last_updated"] > 0, "应记录更新时间戳"

    def test_growth_detection(self, tmp_path):
        """显式建连 → 检测到生长。"""
        from models.brain import NeuralSignal
        region = _make_region(tmp_path)
        # 先统计基线
        region._update_dyn_evolution_stats()
        before = region._stats["dyn_edges"]
        # 在动态区建连
        region.snn.connect(40, 50, weight=0.5, step=1)
        region._update_dyn_evolution_stats()
        assert region._stats["dyn_edges"] == before + 1, "建连后动态区边+1"
        assert region._stats["dyn_grown"] >= 1, "应检测到生长"

    def test_prune_detection(self, tmp_path):
        """断开连接 → 检测到修剪。"""
        from models.brain import NeuralSignal
        region = _make_region(tmp_path)
        # 动态区建连
        region.snn.connect(40, 50, weight=0.5, step=1)
        region._update_dyn_evolution_stats()
        before = region._stats["dyn_edges"]
        # 断开
        region.snn.disconnect(40, 50)
        region._update_dyn_evolution_stats()
        assert region._stats["dyn_edges"] == before - 1, "断开后动态区边-1"
        assert region._stats["dyn_pruned"] >= 1, "应检测到修剪"

    def test_step_spread_measurement(self, tmp_path):
        """步长展布/种类统计正确。"""
        region = _make_region(tmp_path)
        region.snn.connect(40, 50, weight=0.5, step=1)
        region.snn.connect(41, 51, weight=0.5, step=5)
        region.snn.connect(42, 52, weight=0.5, step=8)
        region._update_dyn_evolution_stats()
        assert region._stats["dyn_step_spread"] == 7, "步长展布应为 8-1=7"
        assert region._stats["dyn_step_distinct"] == 3, "3 种不同步长"
        assert region._stats["dyn_edges"] == 3, "3 条动态区边"

    def test_cumulative_total(self, tmp_path):
        """累计修剪/生长总量。"""
        region = _make_region(tmp_path)
        # 建连再断开, 累计总量应反映
        region.snn.connect(40, 50, weight=0.5, step=1)
        region._update_dyn_evolution_stats()
        region.snn.disconnect(40, 50)
        region._update_dyn_evolution_stats()
        assert region._stats["dyn_grown_total"] >= 1, "累计生长≥1"
        assert region._stats["dyn_pruned_total"] >= 1, "累计修剪≥1"
