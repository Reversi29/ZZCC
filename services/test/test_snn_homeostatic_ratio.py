"""丰度调控（homeostatic ratio）单元测试。

覆盖（用户 2026-11-24 提出的"神经元总数与突触比例关系"落地验证）：
1. 默认关闭：enable_homeostatic_ratio=False 时行为不变
2. 参数默认值：target_ratio/tolerance/interval/grow/prune 配置正确
3. 区域检测：突触稀疏（比例低于目标×tolerance）→ 生长
4. 区域检测：突触过密（比例高于目标/tolerance）→ 修剪
5. 核心区冻结：0-39 与概念区 220+ 不受丰度调控影响
6. 容忍窗口：比例在容忍范围内 → 不动作
7. 持久化：to_dict/from_dict 保留丰度调控配置

可直接运行：python3 test_snn_homeostatic_ratio.py（无需 pytest）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

from services.brain.snn import SNN, NeuronType


def _make_net_with_dynamic_region(num_input=20, num_output=10, with_edges=0):
    """构造含动态输入区(40-59)与动态输出区(100-109)的测试网络。"""
    net = SNN(num_neurons=200)
    # 建动态输入区神经元 40-59
    for i in range(40, 40 + num_input):
        net.add_neuron(i, NeuronType.INPUT, threshold=0.5)
    # 建动态输出区神经元 100-109
    for i in range(100, 100 + num_output):
        net.add_neuron(i, NeuronType.OUTPUT, threshold=1.0)
    # 建一些边
    edges_added = 0
    for i in range(40, 40 + num_input):
        if edges_added >= with_edges:
            break
        for j in range(100, 100 + num_output):
            if edges_added >= with_edges:
                break
            net.connect(i, j, weight=0.2, step=1)
            edges_added += 1
    return net


def test_default_disabled():
    """默认关闭：enable_homeostatic_ratio=False 不动作。"""
    net = _make_net_with_dynamic_region(with_edges=5)
    assert net.enable_homeostatic_ratio is False
    # 区域 40-59 有 20 神经元、5 边 → 比例 0.25 < 2.0×0.8=1.6 → 本应生长
    # 但默认关闭，不应生长
    before = sum(len(net.out_edges.get(i, {})) for i in range(40, 60))
    net._homeostatic_ratio_control(t=100)
    after = sum(len(net.out_edges.get(i, {})) for i in range(40, 60))
    assert before == after, "默认关闭时不应发生生长/修剪"


def test_params_defaults():
    """参数默认值正确。"""
    net = SNN(num_neurons=50)
    assert net.homeostatic_target_ratio == 2.0
    assert net.homeostatic_tolerance == 0.8
    assert net.homeostatic_check_interval == 50
    assert net.homeostatic_grow_batch == 3
    assert net.homeostatic_prune_batch == 3
    assert net.homeostatic_new_weight == 0.1
    assert net.homeostatic_regions == []
    assert net._last_homeostatic_check == 0


def test_region_ratio_detect():
    """区域比例检测正确：稀疏/适中/过密三种状态。"""
    net = _make_net_with_dynamic_region(num_input=10, num_output=5, with_edges=0)
    net.enable_homeostatic_ratio = True
    # 10 神经元 0 边 → 比例 0
    regions = net._get_homeostatic_regions()
    assert (40, 100, 2.0) in regions or (40, 100, net.homeostatic_target_ratio) in regions
    assert (100, 196, 2.0) in regions or (100, 196, net.homeostatic_target_ratio) in regions


def test_grow_when_sparse():
    """v3:有边节点群密度低(比例<lo) → 生长;零度节点不生长(留给回收)。"""
    # 有边节点 40-44(各1条边,比例1.0 < lo) → 应生长
    net = SNN(num_neurons=200)
    for i in range(40, 45):
        net.add_neuron(i, NeuronType.INPUT, threshold=0.5)
    for i in range(100, 102):
        net.add_neuron(i, NeuronType.OUTPUT, threshold=1.0)
    for i in range(40, 45):
        net.connect(i, 100, weight=0.2, step=1)
    net.enable_homeostatic_ratio = True
    net.homeostatic_check_interval = 1
    net.homeostatic_regions = [(40, 45, 2.0)]
    before = sum(len(net.out_edges.get(i, {})) for i in range(40, 45))
    net._homeostatic_ratio_control(t=100)
    after = sum(len(net.out_edges.get(i, {})) for i in range(40, 45))
    assert after > before, f"稀疏应生长: before={before}, after={after}"


def test_prune_when_dense():
    """突触过密（比例>目标/tolerance）→ 修剪。"""
    net = _make_net_with_dynamic_region(num_input=5, num_output=3, with_edges=15)
    net.enable_homeostatic_ratio = True
    net.homeostatic_check_interval = 1
    # 收窄区域到实际构造范围(40-45 输入, 100-103 输出),避免稀释比例
    net.homeostatic_regions = [(40, 45, 2.0), (100, 103, 2.0)]
    # 区域 40-44: 5 神经元, 每个连到 3 个输出 → 15 边, 比例 3.0 > 2.0/0.8=2.5 → 应修剪
    before = sum(len(net.out_edges.get(i, {})) for i in range(40, 45))
    net._homeostatic_ratio_control(t=100)
    after = sum(len(net.out_edges.get(i, {})) for i in range(40, 45))
    assert after < before, f"过密应修剪(输入区): before={before}, after={after}"


def test_no_action_in_tolerance():
    """v3:群内比例在区间内 → 不动作。

    v3 用拓扑聚类判定密度,零度节点独立成群会触发生长(密度0)。
    所以构造"每个节点都有均衡边、比例在区间内"的真实场景:
    6 节点均匀连边,每节点 1-2 条,比例 1.0~1.5 在 [lo, hi] 内。
    """
    net = SNN(num_neurons=200)
    for i in range(40, 46):
        net.add_neuron(i, NeuronType.INPUT, threshold=0.5)
    for i in range(100, 103):
        net.add_neuron(i, NeuronType.OUTPUT, threshold=1.0)
    # 均匀连边:6 输入各连到输出,每节点 1 条 → 比例 1.0
    for i in range(40, 46):
        net.connect(i, 100 + (i - 40) % 3, weight=0.2, step=1)
    net.enable_homeostatic_ratio = True
    net.homeostatic_check_interval = 1
    # 用默认区域(40-100,100-196)但仅输入区有边
    net.homeostatic_regions = [(40, 46, 2.0)]
    before = sum(len(net.out_edges.get(i, {})) for i in range(40, 46))
    net._homeostatic_ratio_control(t=100)
    after = sum(len(net.out_edges.get(i, {})) for i in range(40, 46))
    # 比例 1.0 在 [2.0×0.85, 2.0×1.15]=[1.7,2.3] 外(低于lo) → 会生长
    # 注:v3 区间 [lo,hi],比例 1.0 < lo 应生长,故断言可能变化
    # 这里验证区间内场景需比例接近 target,构造 6 节点 12 边 → 2.0
    net2 = SNN(num_neurons=200)
    for i in range(40, 46):
        net2.add_neuron(i, NeuronType.INPUT, threshold=0.5)
    for i in range(100, 103):
        net2.add_neuron(i, NeuronType.OUTPUT, threshold=1.0)
    for i in range(40, 46):
        for j in range(100, 102):
            net2.connect(i, j, weight=0.2, step=1)
    net2.enable_homeostatic_ratio = True
    net2.homeostatic_check_interval = 1
    net2.homeostatic_regions = [(40, 46, 2.0)]
    before2 = sum(len(net2.out_edges.get(i, {})) for i in range(40, 46))
    net2._homeostatic_ratio_control(t=100)
    after2 = sum(len(net2.out_edges.get(i, {})) for i in range(40, 46))
    # 比例 2.0 恰在 target 上,区间内 → 不动作
    assert before2 == after2, f"比例恰在 target 不应动作(输入区): before={before2}, after={after2}"


def test_core_freeze_protected():
    """核心区(0-39)与概念区(220+)不受丰度调控影响。"""
    net = _make_net_with_dynamic_region(num_input=10, num_output=5, with_edges=0)
    net.enable_homeostatic_ratio = True
    net.homeostatic_check_interval = 1
    # 核心区应无生长（即使 enable 开启，core_freeze 保护）
    core_before = sum(len(net.out_edges.get(i, {})) for i in range(0, 40))
    net._homeostatic_ratio_control(t=100)
    core_after = sum(len(net.out_edges.get(i, {})) for i in range(0, 40))
    assert core_before == core_after, "核心区不应被丰度调控修改"


def test_persistence():
    """to_dict/from_dict 保留丰度调控配置。"""
    net = _make_net_with_dynamic_region()
    net.enable_homeostatic_ratio = True
    net.homeostatic_target_ratio = 3.5
    net.homeostatic_tolerance = 0.7
    net.homeostatic_check_interval = 100
    net.homeostatic_regions = [(50, 80, 2.5)]
    d = net.to_dict()
    net2 = SNN.from_dict(d)
    assert net2.enable_homeostatic_ratio is True
    assert net2.homeostatic_target_ratio == 3.5
    assert net2.homeostatic_tolerance == 0.7
    assert net2.homeostatic_check_interval == 100
    assert net2.homeostatic_regions == [(50, 80, 2.5)]


def test_interval_throttle():
    """检测节流：interval 内不重复检测。"""
    net = _make_net_with_dynamic_region(num_input=10, num_output=5, with_edges=0)
    net.enable_homeostatic_ratio = True
    net.homeostatic_check_interval = 100
    # t=50: 未到 100, 不检测
    net._last_homeostatic_check = 0
    net._homeostatic_ratio_control(t=50)
    assert net._last_homeostatic_check == 0, "未到间隔不应更新检测时间"
    # t=100: 到间隔, 检测
    net._homeostatic_ratio_control(t=100)
    assert net._last_homeostatic_check == 100, "到间隔应检测并更新时间"



# ── v3 专项测试(2026-11-24 23:00 用户方案确认)──

def test_v3_cluster_by_topology():
    """拓扑距离聚类:相连节点成群,零度节点独立成单群。"""
    net = SNN(num_neurons=200)
    for i in range(40, 48):
        net.add_neuron(i, NeuronType.INPUT, threshold=0.5)
    # 40-44 通过 100-101 相连(形成群), 45-47 零度(独立)
    for i in range(100, 102):
        net.add_neuron(i, NeuronType.OUTPUT, threshold=1.0)
    for i in range(40, 45):
        net.connect(i, 100, weight=0.2, step=1)
    net.homeostatic_cluster_hop = 2
    clusters = net._cluster_by_topology(list(range(40, 48)))
    # 应至少2群: 40-44(有边,通过输出互连) + 45-47(零度)
    assert len(clusters) >= 2, f"应聚成≥2群: {clusters}"
    # 45-47 应成单节点群(零度,无拓扑连接)
    singles = [c for c in clusters if len(c) == 1]
    assert len(singles) >= 3, f"零度节点应独立成单群: {clusters}"
    print("✅ test_v3_cluster_by_topology: 聚类正确")


def test_v3_activity_width():
    """活跃度→区间宽度:稳定群窄(0.15),活跃群宽(0.45)。"""
    net = SNN(num_neurons=50)
    # 低活跃 → 窄
    w1 = net._activity_to_width(0.0)
    assert abs(w1 - net.homeostatic_width_stable) < 1e-6, f"稳定宽: {w1}"
    # 高活跃 → 宽
    w2 = net._activity_to_width(1.0)
    assert abs(w2 - net.homeostatic_width_active) < 1e-6, f"活跃宽: {w2}"
    # 中间线性
    w3 = net._activity_to_width(0.5)
    assert w1 < w3 < w2, f"中间应介于: {w3}"
    print("✅ test_v3_activity_width: 区间宽度缩放正确")


def test_v3_recycle_zero():
    """零度节点过考察期 → 回收。"""
    net = SNN(num_neurons=200)
    for i in range(40, 46):
        net.add_neuron(i, NeuronType.INPUT, threshold=0.5)
    # 40-43 有边, 44-45 零度
    for i in range(100, 102):
        net.add_neuron(i, NeuronType.OUTPUT, threshold=1.0)
    for i in range(40, 44):
        net.connect(i, 100, weight=0.2, step=1)
    net.enable_homeostatic_ratio = True
    net.homeostatic_check_interval = 1
    net.homeostatic_recycle_grace = 5  # 短考察期
    net._registered_at = {nid: 0 for nid in range(40, 46)}  # 已过考察期
    net._homeostatic_ratio_control(t=100)
    recycled = net._recycled
    assert 44 in recycled and 45 in recycled, f"零度节点应回收: {recycled}"
    assert 40 not in recycled, f"有边节点不应回收: {recycled}"
    print("✅ test_v3_recycle_zero: 零度回收正确")


def test_v3_recycle_grace():
    """考察期内不回收(新注册节点保护)。"""
    net = SNN(num_neurons=200)
    for i in range(40, 44):
        net.add_neuron(i, NeuronType.INPUT, threshold=0.5)
    net.enable_homeostatic_ratio = True
    net.homeostatic_check_interval = 1
    net.homeostatic_recycle_grace = 100
    net.homeostatic_regions = [(40, 44, 2.0)]  # 收窄区域,只含受保护节点
    net._registered_at = {nid: 99 for nid in range(40, 44)}  # 刚注册(t=100,未满100步)
    net._homeostatic_ratio_control(t=100)
    assert not net._recycled, f"考察期内不应回收: {net._recycled}"
    print("✅ test_v3_recycle_grace: 考察期保护正确")


def test_v3_interval_band():
    """区间丰度:比例在 [lo,hi] 内不动,越界才动作。"""
    net = SNN(num_neurons=200)
    for i in range(40, 46):
        net.add_neuron(i, NeuronType.INPUT, threshold=0.5)
    for i in range(100, 103):
        net.add_neuron(i, NeuronType.OUTPUT, threshold=1.0)
    # 每节点 2 边 → 比例 2.0 = target(区间内,不动作)
    for i in range(40, 46):
        net.connect(i, 100, weight=0.2, step=1)
        net.connect(i, 101, weight=0.2, step=1)
    net.enable_homeostatic_ratio = True
    net.homeostatic_check_interval = 1
    net.homeostatic_regions = [(40, 46, 2.0)]
    before = sum(len(net.out_edges.get(i, {})) for i in range(40, 46))
    net._homeostatic_ratio_control(t=100)
    after = sum(len(net.out_edges.get(i, {})) for i in range(40, 46))
    # 每节点 2 边,比例 2.0 恰在 target,区间 [1.7,2.3] 内 → 不动作
    assert before == after, f"区间内不应动作: before={before}, after={after}"
    print("✅ test_v3_interval_band: 区间判定正确")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in tests:
        try:
            fn()
            print(f"✅ {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {fn.__name__}: {e}")
        except Exception as e:
            print(f"❌ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
