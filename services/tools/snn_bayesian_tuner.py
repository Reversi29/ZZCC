#!/usr/bin/env python3
"""结构可塑性参数贝叶斯优化器(纯 Python, 零第三方依赖)。

替代网格搜索: 用高斯过程(GPR)代理模型 + EI 采集函数, 智能选择下一采样点。
高维/连续参数空间比穷举网格更高效, 每次迭代收敛到更优区域。

目标(同网格调优器):
  1. eval 保持 12/12 (硬约束)
  2. 动态区演化活跃 (优化目标: 步长多样化 + 通断)

参数空间(连续/离散混合):
  min_weight_for_keep ∈ [0.01, 0.20]   (修剪阈值)
  step_max            ∈ [3, 12]        (步长上限)
  step_evolve_rate    ∈ [0.001, 0.10]  (步长演化概率)
  allow_synaptogenesis ∈ {0, 1}        (生长开关)

方法: 初始随机采样 → GPR 拟合 → EI 最大化选择下一候选 → 迭代。
核心区冻结(plasticity_core_freeze=True)始终开启。

用法:
  python3 snn_bayesian_tuner.py                     # 默认 15 轮
  python3 snn_bayesian_tuner.py --iters 20          # 迭代次数
  python3 snn_bayesian_tuner.py --init 5            # 初始随机采样数
  python3 snn_bayesian_tuner.py --rounds 3          # 每候选蒙特卡洛轮数
  python3 snn_bayesian_tuner.py --seed 7            # 随机种子
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
import sys
import tempfile
from typing import Any

# 导入根: services/interface
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "interface"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from eval_cases import EVAL_CASES, run as eval_run  # noqa: E402

# ── 动态区定义 ────────────────────────────────────────────
DYNAMIC_MIN = 40

# 参数空间边界 [min, max]
SPACE = {
    "min_weight_for_keep": (0.01, 0.20),
    "step_max": (3.0, 12.0),
    "step_evolve_rate": (0.001, 0.10),
}
# 离散参数
DISCRETE = {"allow_synaptogenesis": [0, 1]}


# ── 高斯过程(纯 Python) ──────────────────────────────────
def _kernel(x1: list[float], x2: list[float], length: float = 1.0) -> float:
    """RBF 核: exp(-||x1-x2||^2 / (2*length^2))。"""
    sq = sum((a - b) ** 2 for a, b in zip(x1, x2))
    return math.exp(-sq / (2 * length * length))


def _mat_mul(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    return [[sum(A[i][k] * B[k][j] for k in range(len(B)))
             for j in range(len(B[0]))] for i in range(len(A))]


def _mat_vec(A: list[list[float]], v: list[float]) -> list[float]:
    return [sum(A[i][k] * v[k] for k in range(len(v))) for i in range(len(A))]


def _vec_sub(a: list[float], b: list[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _solve(A: list[list[float]], b: list[float]) -> list[float]:
    """高斯消元解 Ax=b(带部分主元)。"""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        # 部分主元
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        if abs(M[col][col]) < 1e-12:
            continue
        for r in range(col + 1, n):
            f = M[r][col] / M[col][col]
            for c in range(col, n + 1):
                M[r][c] -= f * M[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        if abs(M[i][i]) < 1e-12:
            continue
        s = M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / M[i][i]
    return x


class GaussianProcess:
    """GPR 回归(纯 Python, RBF 核 + 噪声)。"""

    def __init__(self, noise: float = 1e-3, length: float = 1.0):
        self.noise = noise
        self.length = length
        self.X: list[list[float]] = []
        self.y: list[float] = []

    def add(self, x: list[float], y: float) -> None:
        self.X.append(x)
        self.y.append(y)

    def predict(self, x: list[float]) -> tuple[float, float]:
        """返回 (均值, 标准差)。"""
        if not self.X:
            return 0.0, 1.0
        n = len(self.X)
        K = [[_kernel(self.X[i], self.X[j], self.length)
              + (self.noise if i == j else 0.0) for j in range(n)]
             for i in range(n)]
        k = [_kernel(x, self.X[i], self.length) for i in range(n)]
        alpha = _solve(K, self.y)
        mean = sum(alpha[i] * k[i] for i in range(n))
        # 方差: k(x,x) - k^T K^-1 k
        K_inv_k = _solve(K, k)
        var = max(0.0, 1.0 - sum(k[i] * K_inv_k[i] for i in range(n)))
        return mean, math.sqrt(var + self.noise)


def expected_improvement(gp: GaussianProcess, x: list[float],
                         y_best: float, xi: float = 0.01) -> float:
    """EI 采集函数。"""
    mu, sigma = gp.predict(x)
    if sigma < 1e-9:
        return 0.0
    z = (mu - y_best - xi) / sigma
    # 标准正态 CDF/PDF(近似)
    cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
    pdf = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
    return (mu - y_best - xi) * cdf + sigma * pdf


# ── 参数空间采样 ─────────────────────────────────────────
def random_point(rng: random.Random) -> dict:
    """随机参数点(连续 + 离散)。"""
    p = {k: rng.uniform(v[0], v[1]) for k, v in SPACE.items()}
    for k, vals in DISCRETE.items():
        p[k] = rng.choice(vals)
    return p


def to_vec(p: dict) -> list[float]:
    """参数 → 归一化向量(用于 GPR)。"""
    v = []
    for k, (lo, hi) in SPACE.items():
        v.append((p[k] - lo) / (hi - lo))
    v.append(float(p["allow_synaptogenesis"]))
    return v


def from_vec(v: list[float]) -> dict:
    """向量 → 参数(反归一化 + 离散化)。"""
    p = {}
    for i, (k, (lo, hi)) in enumerate(SPACE.items()):
        p[k] = lo + v[i] * (hi - lo)
    p["allow_synaptogenesis"] = round(v[-1])
    return p


# ── 目标函数 ─────────────────────────────────────────────
def build_region(params: dict) -> Any:
    from services.brain.snn_region import SNNRegion
    tmp = tempfile.mkdtemp()
    region = SNNRegion(save_path=os.path.join(tmp, "s.json"))
    region.snn.enable_structural_plasticity = True
    region.snn.plasticity_core_freeze = True
    region.snn.min_weight_for_keep = params["min_weight_for_keep"]
    region.snn.step_max = int(round(params["step_max"]))
    region.snn.step_evolve_rate = params["step_evolve_rate"]
    region.snn.allow_synaptogenesis = bool(params["allow_synaptogenesis"])
    return region


def simulate_feedback(region: Any, rounds: int = 5) -> None:
    import random as _r
    from models.brain import NeuralSignal
    _r.seed(42)
    types = ["expense", "user_request", "approval_pending", "threshold_breach"]
    decs = ["auto_approve", "escalate", "reject", "flag", "chat"]
    for i in range(rounds):
        st = _r.choice(types)
        urg = _r.randint(20, 90)
        sig = NeuralSignal(id=f"bayes{i}", type=st,
                           payload={"amount": _r.randint(100, 100000)},
                           source="bayes", urgency=urg)
        region.train_from_feedback(sig, _r.choice(decs), True, wrong_decision=None)


def measure_evolution(region: Any) -> dict:
    snn = region.snn
    dyn_steps = [c.step for s in snn.out_edges
                 for t, c in snn.out_edges[s].items()
                 if s >= DYNAMIC_MIN or t >= DYNAMIC_MIN]
    dyn_edges = sum(1 for s in snn.out_edges
                    for t in snn.out_edges[s].items()
                    if s >= DYNAMIC_MIN or t[0] >= DYNAMIC_MIN)
    return {
        "dyn_edges": dyn_edges,
        "dyn_step_spread": (max(dyn_steps) - min(dyn_steps)) if dyn_steps else 0,
        "dyn_step_distinct": len(set(dyn_steps)),
    }


def evaluate(params: dict, rounds: int = 3) -> dict:
    """评估一个参数点: 蒙特卡洛 + eval 硬约束 + 演化度量。"""
    region = build_region(params)
    for _ in range(rounds):
        simulate_feedback(region, rounds=rounds)
    ok, fails = eval_run(region)
    evo = measure_evolution(region)
    viable = (ok == len(EVAL_CASES))
    # 目标分: 可行优先, 再按演化活跃度。不可行给负分(按掉分程度)
    if viable:
        score = 100.0 + evo["dyn_step_spread"] * 2 + evo["dyn_edges"] * 0.1
    else:
        score = -100.0 * (len(EVAL_CASES) - ok)
    return {"params": params, "eval": ok, "fails": fails,
            "evolution": evo, "viable": viable, "score": score}


def bayesian_optimize(iters: int, init_n: int, rounds: int,
                      rng: random.Random) -> list[dict]:
    """贝叶斯优化主循环。"""
    gp = GaussianProcess(noise=1e-3, length=0.8)
    results = []

    # 1. 初始随机采样(拉丁超立方近似: 随机 + 边界)
    print(f"初始采样 {init_n} 点...")
    init_points = [random_point(rng) for _ in range(init_n)]
    # 加入边界/中心点增强探索(正确构造: 连续参数中心 + 离散参数 0)
    center = {k: (v[0] + v[1]) / 2 for k, v in SPACE.items()}
    center["allow_synaptogenesis"] = 0
    init_points.append(center)
    lo = {k: v[0] for k, v in SPACE.items()}
    lo["allow_synaptogenesis"] = 0
    init_points.append(lo)

    for p in init_points:
        r = evaluate(p, rounds=rounds)
        gp.add(to_vec(p), r["score"])
        results.append(r)
        tag = "✓" if r["viable"] else "✗"
        print(f"  [{tag}] {p} → eval {r['eval']}/12, 分 {r['score']:.1f}")

    # 2. 迭代: EI 最大化选下一候选
    for it in range(iters):
        y_best = max(r["score"] for r in results)
        # 随机采样候选池, 选 EI 最大
        candidates = [random_point(rng) for _ in range(30)]
        best_cand = max(candidates, key=lambda c: expected_improvement(
            gp, to_vec(c), y_best))
        r = evaluate(best_cand, rounds=rounds)
        gp.add(to_vec(best_cand), r["score"])
        results.append(r)
        tag = "✓" if r["viable"] else "✗"
        print(f"  iter {it+1}: [{tag}] {best_cand} → eval {r['eval']}/12, "
              f"分 {r['score']:.1f}")

    # 排序: 可行优先, 再按分
    results.sort(key=lambda r: (not r["viable"], -r["score"]))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=15, help="贝叶斯迭代次数")
    ap.add_argument("--init", type=int, default=5, help="初始随机采样数")
    ap.add_argument("--rounds", type=int, default=3, help="每候选蒙特卡洛轮数")
    ap.add_argument("--seed", type=int, default=7, help="随机种子")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    print(f"贝叶斯优化: {args.init} 初始 + {args.iters} 迭代, "
          f"每候选 {args.rounds} 轮蒙特卡洛, 种子 {args.seed}")
    print(f"参数空间: {SPACE}, 离散: {DISCRETE}")

    results = bayesian_optimize(args.iters, args.init, args.rounds, rng)

    viable = [r for r in results if r["viable"]]
    print(f"\n{'='*60}")
    print(f"可行组合: {len(viable)}/{len(results)}")
    if viable:
        best = viable[0]
        print("最优:")
        print(f"  {best['params']}")
        print(f"    → eval {best['eval']}/12, 演化 {best['evolution']}, "
              f"分 {best['score']:.1f}")
        print("Top 5:")
        for r in viable[:5]:
            print(f"  {r['params']} → {r['eval']}/12, 步长展布"
                  f"{r['evolution']['dyn_step_spread']}")
    else:
        print("⚠️ 无可行组合 — 需放宽核心区冻结或降演化速率。")
        best = max(results, key=lambda r: r["eval"])
        print(f"最接近: {best['params']} → eval {best['eval']}/12")


if __name__ == "__main__":
    main()
