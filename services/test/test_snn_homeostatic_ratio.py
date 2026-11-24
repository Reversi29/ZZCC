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
    """突触稀疏（比例<目标×tolerance）→ 生长。"""
    net = _make_net_with_dynamic_region(num_input=10, num_output=5, with_edges=0)
    net.enable_homeostatic_ratio = True
    net.homeostatic_check_interval = 1  # 每步都检测
    # 区域 40-59: 10 神经元 0 边 → 比例 0 < 1.6 → 应生长
    before = sum(len(net.out_edges.get(i, {})) for i in range(40, 50))
    net._homeostatic_ratio_control(t=100)
    after = sum(len(net.out_edges.get(i, {})) for i in range(40, 50))
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
    """比例在容忍窗口内 → 不动作。"""
    # 构造比例在 [1.6, 2.5] 内: 10 神经元 18 边 → 1.8
    net2 = _make_net_with_dynamic_region(num_input=10, num_output=5, with_edges=18)
    net2.enable_homeostatic_ratio = True
    net2.homeostatic_check_interval = 1
    # 收窄区域到实际构造范围,避免稀释比例
    net2.homeostatic_regions = [(40, 50, 2.0), (100, 105, 2.0)]
    before = sum(len(net2.out_edges.get(i, {})) for i in range(40, 50))
    net2._homeostatic_ratio_control(t=100)
    after = sum(len(net2.out_edges.get(i, {})) for i in range(40, 50))
    assert before == after, f"容忍窗口内不应动作(输入区): before={before}, after={after}"


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
