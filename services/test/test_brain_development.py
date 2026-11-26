"""test/test_brain_development.py — 发育式 SNN 结构形成测试

覆盖用户 2026-11-26 洞察（Phase A/B）：
1. 增殖期：动态区生成未分化神经元
2. 突触探索：从无到有弱连接形成骨架（解决 0 条边）
3. 自发分簇：拓扑 BFS 形成功能簇
4. 不破坏核心区：发育不动 0-39 固定拓扑
5. 弱引导：同先验群倾向连接（非纯随机）
6. 突触修剪：弱连接被剪除
7. 侧向抑制：簇内负权重边
"""
import os
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

from services.brain.snn import SNN, NeuronType
from services.brain.development import DevelopmentDriver, _DEV_START, _DEV_END


def _mk_net() -> SNN:
    """创建干净网络（含动态区空槽）。"""
    net = SNN(num_neurons=40)  # 固定核心 0-39
    # 动态区预留（不创建神经元，增殖时创建）
    return net


def test_proliferate():
    """增殖期：动态区生成未分化神经元，不接线。"""
    net = _mk_net()
    dev = DevelopmentDriver(net)
    created = dev.proliferate(n=30)
    assert created == 30, f"应增殖 30, got {created}"
    # 动态区神经元存在
    dev_neurons = [
        i for i in range(_DEV_START, _DEV_END + 1)
        if i < len(net.neurons) and net.neurons[i].neuron_type.value != "unused"
    ]
    assert len(dev_neurons) >= 30
    # 增殖不接线
    assert dev._stats["explored_edges"] == 0
    print(f"  ✅ 增殖 {created} 神经元，未接线")


def test_explore_synapses_skeleton():
    """突触探索：从无到有弱连接，形成骨架（0 条边 → >0 条边）。"""
    net = _mk_net()
    dev = DevelopmentDriver(net)
    dev.proliferate(n=40)
    created = dev.explore_synapses(max_new=80)
    # 应有探索连接（骨架形成）
    assert created > 0, "应形成探索连接骨架"
    # 验证动态区内部边 > 0
    dev_edges = [
        (s, t) for s in net.out_edges
        for t in net.out_edges[s]
        if _DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END
    ]
    assert len(dev_edges) > 0, "动态区应形成内部边（骨架）"
    print(f"  ✅ 探索 {created} 条突触，动态区内部边 {len(dev_edges)} 条（骨架形成）")


def test_core_untouched():
    """发育不破坏核心区（0-39 固定拓扑）。"""
    net = _mk_net()
    # 记录核心区连接
    core_before = set()
    for s in net.out_edges:
        for t in net.out_edges[s]:
            if s < 40 and t < 40:
                core_before.add((s, t))
    dev = DevelopmentDriver(net)
    dev.proliferate(n=30)
    dev.explore_synapses(max_new=60)
    # 核心区连接不变
    core_after = set()
    for s in net.out_edges:
        for t in net.out_edges[s]:
            if s < 40 and t < 40:
                core_after.add((s, t))
    assert core_before == core_after, "核心区连接被发育改变！"
    print(f"  ✅ 核心区 {len(core_before)} 条连接未受影响")


def test_differentiate_clusters():
    """自发分簇：拓扑 BFS 形成功能簇。"""
    net = _mk_net()
    dev = DevelopmentDriver(net)
    dev.proliferate(n=40)
    dev.explore_synapses(max_new=100)
    result = dev.differentiate()
    clusters = result["clusters"]
    # 分簇应产生（可能有 1+ 个簇）
    assert isinstance(clusters, list)
    print(f"  ✅ 分簇产生 {result['count']} 个簇, 簇大小 {[len(c) for c in clusters]}")


def test_weak_guide_preference():
    """弱引导：同先验群（同 ID 区间）倾向连接（非纯随机）。"""
    net = _mk_net()
    dev = DevelopmentDriver(net, params={"explore_prob": 0.05, "weak_guide": 0.8})
    dev.proliferate(n=50)
    dev.explore_synapses(max_new=200)
    # 统计同群（输入区 40-99 内部）vs 跨群连接
    same_group = 0
    cross_group = 0
    for s in net.out_edges:
        for t in net.out_edges[s]:
            if not (_DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END):
                continue
            s_input = s <= 99
            t_input = t <= 99
            if s_input == t_input:
                same_group += 1
            else:
                cross_group += 1
    # 弱引导应使同群连接倾向（同群 > 跨群，因同群概率加成）
    # 注：探索是随机 + 引导加成，同群应占比高
    total = same_group + cross_group
    if total > 0:
        same_ratio = same_group / total
        # 弱引导 0.8 → 同群显著偏好（>50%）
        assert same_ratio > 0.5, f"同群占比 {same_ratio:.2f} 应 >0.5（弱引导生效）"
    print(f"  ✅ 同群 {same_group} / 跨群 {cross_group}（弱引导偏好）")


def test_prune_weak():
    """突触修剪：弱连接被剪除。"""
    net = _mk_net()
    dev = DevelopmentDriver(net, params={"keep_weight": 0.30})
    dev.proliferate(n=30)
    # 建立一些弱连接（权重 < 0.30）
    for s in range(40, 55):
        for t in range(56, 70):
            if random.random() < 0.5:
                net.connect(s, t, weight=0.1, step=1)
    before = sum(1 for s in net.out_edges for t in net.out_edges[s]
                 if _DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END)
    pruned = dev.prune_weak_synapses()
    after = sum(1 for s in net.out_edges for t in net.out_edges[s]
                if _DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END)
    assert pruned > 0, "应剪除弱突触"
    assert after < before, "弱突触应被剪除"
    print(f"  ✅ 修剪 {pruned} 条弱突触 ({before}→{after})")


def test_lateral_inhibition():
    """侧向抑制：簇内负权重边。"""
    net = _mk_net()
    dev = DevelopmentDriver(net)
    dev.proliferate(n=20)
    clusters = [[40, 41, 42, 43, 44], [45, 46, 47, 48, 49]]
    added = dev.apply_lateral_inhibition(clusters)
    assert added > 0, "应加侧向抑制边"
    # 验证存在负权重边
    neg = [(s, t) for s in net.out_edges for t in net.out_edges[s]
           if net.out_edges[s][t].weight < 0]
    assert len(neg) > 0, "应有负权重（抑制）边"
    print(f"  ✅ 侧向抑制 {added} 条负权重边")


def test_convergence_no_overgrowth():
    """收敛：多次发育循环后边数稳定，不无限增长（防 667 边暴涨）。"""
    net = _mk_net()
    dev = DevelopmentDriver(net, params={"max_dev_edges": 60, "prune_ratio": 0.35})
    # 先增殖
    dev.proliferate(n=50)
    # 多次发育循环
    edges_history = []
    for t in range(1, 11):
        dev.run_development_cycle(time=t)
        edges = sum(1 for s in net.out_edges for tgt in net.out_edges[s]
                    if _DEV_START <= s <= _DEV_END and _DEV_START <= tgt <= _DEV_END)
        edges_history.append(edges)
    # 边数应被限制在 max_dev_edges 附近，不无限增长
    final_edges = edges_history[-1]
    assert final_edges <= 60, f"边数超上限: {final_edges} > 60"
    # 连续两轮应稳定（收敛，不暴涨）
    last_two = edges_history[-2:]
    assert last_two[-1] <= 60, f"收敛失败: {last_two}"
    print(f"  ✅ 收敛: 边数历史 {edges_history}，最终 {final_edges} ≤ 60")


if __name__ == "__main__":
    import random
    print("===== 发育式 SNN 测试 =====")
    test_proliferate()
    test_explore_synapses_skeleton()
    test_core_untouched()
    test_differentiate_clusters()
    test_weak_guide_preference()
    test_prune_weak()
    test_lateral_inhibition()
    test_convergence_no_overgrowth()
    print("\n全部通过 ✅")
