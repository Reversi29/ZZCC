"""实验: 在 snn_iterate 中启用 Hebbian 后, eval 是否回归

结论决定第三组(hebbian_readiness_annealing)的实现范围。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "interface")))
os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

import importlib.util

spec = importlib.util.spec_from_file_location("eval_cases", "tools/eval_cases.py")
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)

from services.brain.snn_region import SNNRegion

PROD = "/tmp/prod_eval_adaptive.json"


def _edge_count(net):
    return sum(len(v) for v in net.out_edges.values())


def eval_of(region):
    ok, fails = ec.run(region)
    return ok, fails


def make_region():
    r = SNNRegion(save_path=os.path.join(tempfile.mkdtemp(), "t.json"))
    r.snn.concept_freeze_start = 220
    return r


def run_experiments():
    from services.brain.snn import SNN

    cases = [
        ("基线(无迭代,hebbian=False)", 0, False),
        ("迭代20次 hebbian=False", 20, False),
        ("迭代20次 hebbian=True", 20, True),
        ("迭代50次 hebbian=True", 50, True),
        ("迭代100次 hebbian=True", 100, True),
        ("迭代200次 hebbian=True", 200, True),
    ]

    print(f"{'实验':<34}{'eval':>8}{'边数':>8}{'总放电':>10}")
    print("-" * 62)
    for name, n_iter, hebbian in cases:
        r = make_region()
        r.snn = SNN.load(PROD)
        base_edges = _edge_count(r.snn)
        # 直接调用底层: 模拟 snn_iterate 的放电, 但可控 hebbian
        import random

        random.seed(42)
        for _ in range(n_iter):
            r.snn.enable_hebbian = hebbian
            r.snn.enable_structural_plasticity = False
            outs, _, _ = r.snn.step_with_learning(
                [202], 1.5
            )  # 内源弱脉冲(同 snn_iterate)
        post_edges = _edge_count(r.snn)
        ok, fails = eval_of(r)
        fires = r.snn.stats()["total_fires"]
        flag = "" if ok == 12 else f"  ← 回归 fails={fails}"
        print(
            f"{name:<34}{ok:>6}/12{post_edges:>8}{fires:>10}"
            f"  (边{base_edges}→{post_edges}){flag}"
        )


if __name__ == "__main__":
    run_experiments()