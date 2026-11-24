#!/usr/bin/env python3
"""结构可塑性参数自动调优器。

目标: 找一组结构可塑性参数, 使:
  1. eval 保持 12/12 (核心约束, 硬性 — 护栏判据)
  2. 动态区演化活跃 (优化目标: 步长多样化 + 通断发生)

方法: 网格搜索关键参数(min_weight_for_keep, step_max, step_evolve_rate),
每个组合跑多次蒙特卡洛(随机注入+反馈训练), 要求每次 eval 12/12,
再比较演化活跃度(动态区步长方差 / 通断次数)。

核心区冻结(plasticity_core_freeze=True)始终开启, 保证 0-39 不被扰动。
调优只针对动态区参数。

用法:
  python3 snn_plasticity_tuner.py                  # 全网格
  python3 snn_plasticity_tuner.py --quick          # 快速(减半组合)
  python3 snn_plasticity_tuner.py --rounds 3       # 每组合蒙特卡洛轮数
  python3 snn_plasticity_tuner.py --best-only      # 只报告最优
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import Any

# 导入根: services/interface
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "interface"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from eval_cases import EVAL_CASES, run as eval_run  # noqa: E402

# ── 动态区定义 ────────────────────────────────────────────
# 核心区 0-39 冻结(plasticity_core_freeze), 调优只作用 ≥40
DYNAMIC_MIN = 40


def build_region(params: dict) -> Any:
    """构造带参数的 SNNRegion(干净拓扑, 临时存储)。"""
    from services.brain.snn_region import SNNRegion

    tmp = tempfile.mkdtemp()
    region = SNNRegion(save_path=os.path.join(tmp, "s.json"))
    # 开启结构可塑性 + 核心区冻结
    region.snn.enable_structural_plasticity = True
    region.snn.plasticity_core_freeze = True
    # 应用待调参数
    region.snn.min_weight_for_keep = params.get("min_weight_for_keep", 0.05)
    region.snn.step_max = params.get("step_max", 5)
    region.snn.step_evolve_rate = params.get("step_evolve_rate", 0.01)
    region.snn.allow_synaptogenesis = params.get("allow_synaptogenesis", False)
    return region


def simulate_feedback(region: Any, rounds: int = 5) -> None:
    """模拟真实流量: 随机信号 + 反馈训练(动态区演化驱动)。"""
    import random
    from models.brain import NeuralSignal

    random.seed(42)
    signal_types = ["expense", "user_request", "approval_pending", "threshold_breach"]
    decisions = ["auto_approve", "escalate", "reject", "flag", "chat"]
    for i in range(rounds):
        st = random.choice(signal_types)
        urg = random.randint(20, 90)
        pl = {"amount": random.randint(100, 100000)}
        sig = NeuralSignal(id=f"tune{i}", type=st, payload=pl,
                           source="tune", urgency=urg)
        dec = random.choice(decisions)
        region.train_from_feedback(sig, dec, True, wrong_decision=None)


def measure_evolution(region: Any) -> dict:
    """测量动态区演化活跃度。"""
    snn = region.snn
    dyn_steps = [c.step for s in snn.out_edges
                 for t, c in snn.out_edges[s].items()
                 if s >= DYNAMIC_MIN or t >= DYNAMIC_MIN]
    dyn_edges = sum(1 for s in snn.out_edges
                    for _ in snn.out_edges[s].items()
                    if s >= DYNAMIC_MIN or _[0] >= DYNAMIC_MIN)
    step_variance = (max(dyn_steps) - min(dyn_steps)) if dyn_steps else 0
    return {
        "dyn_edges": dyn_edges,
        "dyn_step_spread": step_variance,
        "dyn_step_distinct": len(set(dyn_steps)),
    }


def eval_score(region: Any) -> tuple[int, list]:
    """跑 eval, 返回 (通过数, 失败列表)。"""
    return eval_run(region)


def tune(params_grid: dict, rounds: int = 3) -> list[dict]:
    """网格搜索, 返回按活跃度排序的结果列表。"""
    import itertools

    keys = list(params_grid.keys())
    combos = list(itertools.product(*[params_grid[k] for k in keys]))
    results = []
    for combo in combos:
        params = dict(zip(keys, combo))
        region = build_region(params)
        # 蒙特卡洛: 多轮模拟反馈(动态区演化)
        for _ in range(rounds):
            simulate_feedback(region, rounds=rounds)
        # 硬约束: 每次 eval 必须 12/12
        ok, fails = eval_score(region)
        if ok != len(EVAL_CASES):
            results.append({
                "params": params, "eval": ok, "fails": fails,
                "evolution": measure_evolution(region), "viable": False,
            })
            continue
        results.append({
            "params": params, "eval": ok, "fails": fails,
            "evolution": measure_evolution(region), "viable": True,
        })
        print(f"  ✓ {params} → eval {ok}/12, 演化 {results[-1]['evolution']}")
    # 排序: 可行优先, 再按演化活跃度
    results.sort(key=lambda r: (not r["viable"],
                                -r["evolution"]["dyn_step_spread"],
                                -r["evolution"]["dyn_edges"]))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="快速(减半组合)")
    ap.add_argument("--rounds", type=int, default=3, help="每组合蒙特卡洛轮数")
    ap.add_argument("--best-only", action="store_true", help="只报告最优")
    args = ap.parse_args()

    # 网格: 关键参数范围
    grid = {
        "min_weight_for_keep": [0.02, 0.05, 0.10],
        "step_max": [3, 5, 8],
        "step_evolve_rate": [0.005, 0.01, 0.05],
    }
    if args.quick:
        grid = {
            "min_weight_for_keep": [0.05, 0.10],
            "step_max": [5, 8],
            "step_evolve_rate": [0.01, 0.05],
        }

    print(f"网格搜索: {len(list(__import__('itertools').product(*grid.values())))} 组合, "
          f"每组合 {args.rounds} 轮蒙特卡洛")
    results = tune(grid, rounds=args.rounds)

    viable = [r for r in results if r["viable"]]
    print(f"\n{'='*60}")
    print(f"可行组合: {len(viable)}/{len(results)}")
    if viable:
        print("最优(按演化活跃度排序):")
        for r in viable[:5]:
            print(f"  {r['params']} → eval {r['eval']}/12, 演化 {r['evolution']}")
    else:
        print("⚠️ 无可行组合 — 所有参数都破坏 eval。需放宽核心区冻结或降演化速率。")
        # 报告最接近的
        best = min(results, key=lambda r: -r["eval"])
        print(f"最接近: {best['params']} → eval {best['eval']}/12, 失败 {best['fails']}")
    if args.best_only:
        return

    print(f"\n{'='*60}")
    print("全部结果:")
    for r in results:
        tag = "✓" if r["viable"] else "✗"
        print(f"  {tag} {r['params']} → {r['eval']}/12, "
              f"步长展布{r['evolution']['dyn_step_spread']}, "
              f"动态边{r['evolution']['dyn_edges']}")


if __name__ == "__main__":
    main()
