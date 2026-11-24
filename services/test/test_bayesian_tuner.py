"""贝叶斯优化器核心单元测试(纯 Python GPR/EI)。"""
import importlib.util
import sys
from pathlib import Path

TOOLS = str(Path(__file__).resolve().parents[1] / "tools")
spec = importlib.util.spec_from_file_location(
    "snn_bayesian_tuner", str(Path(TOOLS) / "snn_bayesian_tuner.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)


class TestGPR:
    def test_fit_parabola(self):
        """GPR 应拟合抛物线并预测接近真实。"""
        gp = bt.GaussianProcess(noise=1e-4, length=1.0)
        xs = [-2, -1, 0, 1, 2]
        ys = [x * x for x in xs]
        for x, y in zip(xs, ys):
            gp.add([float(x)], float(y))
        mu, sigma = gp.predict([0.5])
        assert abs(mu - 0.25) < 0.2, f"GPR 偏差过大: {mu}"
        assert sigma >= 0, "方差应非负"

    def test_predict_variance_shrinks(self):
        """有数据点处方差应小(已探索)。"""
        gp = bt.GaussianProcess(noise=1e-3)
        gp.add([0.0], 1.0)
        gp.add([1.0], 2.0)
        _, s_known = gp.predict([0.0])
        _, s_unknown = gp.predict([5.0])
        assert s_unknown > s_known, "未探索点方差应更大"


class TestEI:
    def test_unknown_explored(self):
        """EI 应鼓励探索: 未探索点 EI 高于已知点。"""
        gp = bt.GaussianProcess()
        gp.add([0.0], 1.0)
        ei_known = bt.expected_improvement(gp, [0.0], 1.0)
        ei_unknown = bt.expected_improvement(gp, [5.0], 1.0)
        assert ei_unknown > ei_known, "未探索点 EI 应更高"


class TestVectorRoundtrip:
    def test_roundtrip(self):
        """参数 ↔ 向量归一化往返一致。"""
        p = {"min_weight_for_keep": 0.05, "step_max": 8,
             "step_evolve_rate": 0.05, "allow_synaptogenesis": 1}
        v = bt.to_vec(p)
        p2 = bt.from_vec(v)
        for k in p:
            if k in bt.SPACE:
                assert abs(p[k] - p2[k]) < 0.02, f"{k} 往返不一致: {p[k]} vs {p2[k]}"
        assert p2["allow_synaptogenesis"] in (0, 1), "离散参数应取整"

    def test_bounds_respected(self):
        """采样点应在参数空间边界内。"""
        import random
        rng = random.Random(1)
        for _ in range(50):
            p = bt.random_point(rng)
            for k, (lo, hi) in bt.SPACE.items():
                assert lo <= p[k] <= hi, f"{k}={p[k]} 超出边界"
            assert p["allow_synaptogenesis"] in (0, 1)


class TestEvaluate:
    def test_eval_returns_structure(self):
        """evaluate 返回完整结构(可行/eval/演化/分)。"""
        params = {"min_weight_for_keep": 0.05, "step_max": 8,
                  "step_evolve_rate": 0.05, "allow_synaptogenesis": 0}
        r = bt.evaluate(params, rounds=1)
        for k in ("params", "eval", "fails", "evolution", "viable", "score"):
            assert k in r, f"缺失字段 {k}"
        assert r["viable"] in (True, False)
        assert isinstance(r["evolution"], dict)
        assert "dyn_step_spread" in r["evolution"]
