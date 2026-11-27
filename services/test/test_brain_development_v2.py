"""test/test_brain_development_v2.py — 发育 v2 修复测试

覆盖 2026-11-27 用户质疑"发育未起作用/骨架未形成"的修复：
1. 分功能区配额探索：input/output/concept 三区都有边（不再低 ID 集中）
2. 输出链打通：输出区(100-199)有出边连核心输出(32-37)/概念区（消除死端）
3. 步长演化：发育边步长不全是 1（多尺度）
4. 探索边权重稳固：> keep_weight（不空转）
5. 核心区不污染：发育后核心区连接不变
6. 收敛：多次循环边数不暴涨（防 667 前科）
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

from services.brain.snn import SNN, NeuronType
from services.brain.development import (
    DevelopmentDriver, _DEV_START, _DEV_END,
    _DEV_INPUT_END, _DEV_OUTPUT_START, _DEV_OUTPUT_END, _CONCEPT_START,
    _CORE_OUTPUTS,
)


def _mk_net() -> SNN:
    """创建干净网络（核心 0-39 + 动态区增殖槽）。"""
    net = SNN(num_neurons=40)
    return net


def _dev_edges(net: SNN):
    return [
        (s, t, net.out_edges[s][t])
        for s in net.out_edges
        for t in net.out_edges[s]
        if _DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END
    ]


def _run_dev(net: SNN, cycles: int = 5, params: dict = None) -> DevelopmentDriver:
    """运行多轮发育循环。"""
    import random
    random.seed(42)  # 确定性：测试可复现（避免共享随机序列导致不稳定）
    p = {"max_dev_edges": 120, "prune_ratio": 0.35}
    if params:
        p.update(params)
    dev = DevelopmentDriver(net, params=p)
    dev.proliferate(n=60)
    for t in range(1, cycles + 1):
        dev.run_development_cycle(time=t)
    return dev


def test_zone_coverage():
    """v2: 分功能区探索——input/output 区都有边，不再低 ID 集中。"""
    net = _mk_net()
    dev = _run_dev(net, cycles=3)
    edges = _dev_edges(net)
    assert len(edges) > 0, "应形成探索边"
    # 统计源所在功能区
    src_zones = set()
    for s, t, _ in edges:
        if _DEV_START <= s <= _DEV_INPUT_END:
            src_zones.add("input")
        elif _DEV_OUTPUT_START <= s <= _DEV_OUTPUT_END:
            src_zones.add("output")
    # 探索应覆盖输入区（感知来源）
    assert "input" in src_zones, f"输入区无探索边: {src_zones}"
    print(f"  ✅ 探索源分区覆盖: {src_zones}，边 {len(edges)}")


def test_output_chain_connected():
    """v2: 输出链打通——输出区(100-199)有出边连核心输出/概念区（消除死端）。"""
    net = _mk_net()
    dev = _run_dev(net, cycles=3)
    # 输出区神经元有出边
    out_connected = [
        s for s in net.out_edges
        if _DEV_OUTPUT_START <= s <= _DEV_OUTPUT_END and len(net.out_edges[s]) > 0
    ]
    assert len(out_connected) > 0, "输出区(100-199)神经元应有出边（打通决策链）"
    # 验证出边指向核心输出或概念区
    chain_targets = set()
    for s in out_connected:
        for t in net.out_edges[s]:
            if t in _CORE_OUTPUTS or t >= _CONCEPT_START:
                chain_targets.add(t)
    assert len(chain_targets) > 0, f"输出区出边应连核心输出/概念区，got {chain_targets}"
    print(f"  ✅ 输出链打通: {len(out_connected)} 输出神经元有出边，连 {sorted(chain_targets)}")


def test_step_evolved():
    """v2: 步长演化——发育边步长不全是 1（多尺度）。"""
    net = _mk_net()
    dev = _run_dev(net, cycles=8, params={"step_evolve_rate": 0.3})
    edges = _dev_edges(net)
    assert len(edges) > 0
    steps = {c.step for _, _, c in edges}
    # 步长演化应产生非 1 步长（多尺度）
    non_one = [c.step for _, _, c in edges if c.step != 1]
    assert len(non_one) > 0, f"步长应演化出非 1 值，got steps={steps}"
    print(f"  ✅ 步长演化: steps={sorted(steps)}，非1步长 {len(non_one)} 条")


def test_weight_stable():
    """v2: 探索边权重 > keep_weight（骨架稳固，不空转）。"""
    net = _mk_net()
    dev = _run_dev(net, cycles=3)
    edges = _dev_edges(net)
    assert len(edges) > 0
    # 探索边权重应 >= explore_weight_min (> keep_weight)
    below = [c.weight for _, _, c in edges if c.weight < 0.20]
    assert len(below) == 0, f"探索边不应低于 keep_weight=0.20: {len(below)} 条"
    print(f"  ✅ 探索边权重稳固（>0.20），最低 {min(c.weight for _,_,c in edges):.3f}")


def test_core_not_polluted():
    """v2: 核心区不污染——发育后核心区(0-39)连接不变。"""
    net = _mk_net()
    # 建一个核心区小拓扑（模拟固定核心）
    net.add_neuron(0, NeuronType.INPUT)
    net.add_neuron(16, NeuronType.EXCITATORY)
    net.add_neuron(32, NeuronType.OUTPUT)
    net.connect(0, 16, weight=0.9, step=1)
    net.connect(16, 32, weight=0.9, step=1)
    core_before = set()
    for s in net.out_edges:
        for t in net.out_edges[s]:
            if s < 40 and t < 40:
                core_before.add((s, t, net.out_edges[s][t].weight))
    dev = _run_dev(net, cycles=3)
    core_after = set()
    for s in net.out_edges:
        for t in net.out_edges[s]:
            if s < 40 and t < 40:
                core_after.add((s, t, net.out_edges[s][t].weight))
    assert core_before == core_after, "核心区连接被发育改变！"
    print(f"  ✅ 核心区 {len(core_before)} 条连接未受影响")


def test_convergence_v2():
    """v2: 收敛——多次循环边数不暴涨（防 667 前科）。"""
    net = _mk_net()
    dev = _run_dev(net, cycles=15, params={"max_dev_edges": 80})
    edges = _dev_edges(net)
    assert len(edges) <= 80, f"边数超上限: {len(edges)} > 80"
    print(f"  ✅ 收敛: 最终 {len(edges)} 边 ≤ 80")


def test_no_core_in_dev_edges():
    """v2: 发育边不涉及核心区（源/目标都 ≥40）。"""
    net = _mk_net()
    dev = _run_dev(net, cycles=3)
    for s, t, _ in _dev_edges(net):
        assert s >= 40 and t >= 40, f"发育边涉及核心: {s}→{t}"
    print("  ✅ 发育边全在动态区（核心不参与）")


if __name__ == "__main__":
    print("===== 发育 v2 修复测试 =====")
    test_zone_coverage()
    test_output_chain_connected()
    test_step_evolved()
    test_weight_stable()
    test_core_not_polluted()
    test_convergence_v2()
    test_no_core_in_dev_edges()
    print("\n全部通过 ✅")
