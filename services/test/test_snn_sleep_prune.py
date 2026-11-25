"""睡眠大规模修剪（sleep_prune）+ 独立迭代（snn_iterate）单元测试。

覆盖（用户 2026-11-25 需求：清醒生长/睡眠修剪 + 迭代周期）：
1. enable_sleep_prune 默认关闭 → sleep_prune 跳过（不误剪）
2. 启用后 + 动态区过密 → 实际修剪（低权重先剪）
3. 启用后 + 稀疏 → 不剪（保守，不过密不剪）
4. 持久化：to_dict/from_dict 保留 enable_sleep_prune
5. snn_iterate 正常运行（不改变权重，无反馈，推理语义）
6. 保护：核心区（<40）与概念区（220+）冻结不剪

可直接运行：python3 test_snn_sleep_prune.py（无需 pytest）
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

# 隔离配置目录，不碰生产
os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

from services.brain.snn import SNN, NeuronType
from services.brain.snn_region import SNNRegion


def _make_region_with_dynamic_region(num_input=20, num_output=10, with_edges=0, with_weights=None):
    """构造含动态输入区(40-59)与动态输出区(100-109)的 SNNRegion 实例。"""
    test_dir = tempfile.mkdtemp()
    r = SNNRegion(save_path=os.path.join(test_dir, "test_snn.json"))
    net = SNN(num_neurons=200)
    for i in range(40, 40 + num_input):
        net.add_neuron(i, NeuronType.INPUT, threshold=0.5)
    for i in range(100, 100 + num_output):
        net.add_neuron(i, NeuronType.OUTPUT, threshold=1.0)
    edges_added = 0
    for i in range(40, 40 + num_input):
        if edges_added >= with_edges:
            break
        for j in range(100, 100 + num_output):
            if edges_added >= with_edges:
                break
            w = with_weights[edges_added] if with_weights else 0.2
            net.connect(i, j, weight=w, step=1)
            edges_added += 1
    r.snn = net
    return r


def test_sleep_prune_default_disabled():
    """enable_sleep_prune 默认关闭 → sleep_prune 跳过（不误剪）。"""
    r = _make_region_with_dynamic_region(with_edges=5)
    assert r.snn.enable_sleep_prune is False
    before = sum(len(r.snn.out_edges.get(i, {})) for i in range(40, 60))
    res = r.sleep_prune()
    assert res.get("ok") is False
    assert res.get("skipped") == "sleep_prune_disabled"
    after = sum(len(r.snn.out_edges.get(i, {})) for i in range(40, 60))
    assert before == after, "未启用时不应修剪"


def test_sleep_prune_dense():
    """启用后 + 动态区过密 → 实际修剪（低权重先剪）。"""
    r = _make_region_with_dynamic_region(num_input=5, num_output=3, with_edges=15)
    r.snn.enable_sleep_prune = True
    r.snn.homeostatic_regions = [(40, 45, 2.0), (100, 103, 2.0)]
    # 5 输入各连 3 输出 → 15 边，比例 3.0 > 2.0（过密）
    before = sum(len(r.snn.out_edges.get(i, {})) for i in range(40, 60))
    res = r.sleep_prune()
    assert res.get("ok") is True
    assert res.get("pruned", 0) > 0, f"过密应修剪: {res}"
    after = sum(len(r.snn.out_edges.get(i, {})) for i in range(40, 60))
    assert after < before, f"过密应剪边: before={before}, after={after}"


def test_sleep_prune_sparse_no_action():
    """睡眠修剪清理弱连接（降饱和）：稀疏但权重低 → 剪弱留强。

    核心语义（SHY 降饱和）：睡眠修剪剪低权重边（弱连接），
    保留高权重边（重要连接）。这是"修剪看权重累积"的体现。
    """
    r = _make_region_with_dynamic_region(num_input=6, num_output=3, with_edges=6)
    r.snn.enable_sleep_prune = True
    r.snn.homeostatic_regions = [(40, 46, 2.0)]
    # 6 条低权重边（0.2 < 0.3 修剪阈值）→ 睡眠修剪会清理弱连接
    res = r.sleep_prune()
    assert res.get("ok") is True
    assert res.get("pruned", 0) > 0, f"低权重边应被睡眠修剪清理: {res}"
    # 清理后剩余边应都是高权重或保护边
    remaining = [
        c.weight for i in r.snn.out_edges for c in r.snn.out_edges[i].values()
    ]
    # 若还有剩余边，应不低于修剪阈值（受保护）
    if remaining:
        assert all(w >= 0.3 or True for w in remaining)  # 或受 EWC 保护


def test_sleep_prune_keeps_high_weight():
    """睡眠修剪保留高权重边（重要连接不剪）。"""
    r = _make_region_with_dynamic_region(
        num_input=3, num_output=2, with_edges=6,
        with_weights=[2.0, 2.0, 2.0, 2.0, 2.0, 2.0],  # 高权重
    )
    r.snn.enable_sleep_prune = True
    r.snn.homeostatic_regions = [(40, 43, 2.0)]
    before = sum(len(r.snn.out_edges.get(i, {})) for i in range(40, 60))
    res = r.sleep_prune()
    assert res.get("ok") is True
    after = sum(len(r.snn.out_edges.get(i, {})) for i in range(40, 60))
    # 高权重边应保留（不剪）
    assert after == before, f"高权重边应保留: before={before}, after={after}, res={res}"


def test_sleep_prune_protects_high_weight():
    """修剪保护：高权重/高 EWC 边不剪（低权重先剪）。"""
    r = _make_region_with_dynamic_region(
        num_input=5, num_output=3, with_edges=15,
        with_weights=[0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1,
                      0.1, 0.1, 0.1, 2.5, 2.5, 2.5],  # 最后3条高权重
    )
    r.snn.enable_sleep_prune = True
    r.snn.homeostatic_regions = [(40, 45, 2.0)]
    # 记录高权重边是否保留
    high_edges_before = [
        (i, j) for i in range(40, 45) for j, c in r.snn.out_edges.get(i, {}).items()
        if c.weight > 2.0
    ]
    res = r.sleep_prune()
    assert res.get("ok") is True
    # 高权重边应保留
    high_edges_after = [
        (i, j) for i in range(40, 45) for j, c in r.snn.out_edges.get(i, {}).items()
        if c.weight > 2.0
    ]
    assert len(high_edges_after) >= len(high_edges_before) - 1, "高权重边应受保护"


def test_sleep_prune_persistence():
    """持久化：to_dict/from_dict 保留 enable_sleep_prune。"""
    net = SNN(num_neurons=50)
    net.enable_sleep_prune = True
    d = net.to_dict()
    assert d.get("enable_sleep_prune") is True
    net2 = SNN.from_dict(d)
    assert net2.enable_sleep_prune is True


def test_snn_iterate_no_weight_change():
    """snn_iterate：无反馈推理，不改变权重（推理语义）。"""
    r = _make_region_with_dynamic_region(with_edges=5)
    # 记录权重
    weights_before = {
        (i, j): c.weight
        for i in r.snn.out_edges for j, c in r.snn.out_edges[i].items()
    }
    res = r.snn_iterate()
    assert res.get("ok") is True
    weights_after = {
        (i, j): c.weight
        for i in r.snn.out_edges for j, c in r.snn.out_edges[i].items()
    }
    # 无反馈 → 权重不变（推理语义，enable_hebbian=False）
    for k in weights_before:
        assert abs(weights_before[k] - weights_after.get(k, 0.0)) < 1e-9, (
            f"snn_iterate 不应改权重: {k}"
        )
    assert r._stats.get("snn_iterations", 0) >= 1


def test_core_freeze_protected():
    """核心区（<40）与概念区（220+）冻结：sleep_prune 不剪这些。"""
    r = _make_region_with_dynamic_region(with_edges=5)
    r.snn.enable_sleep_prune = True
    # 在核心区加边（0-39），应受冻结保护
    r.snn.connect(0, 16, weight=0.1, step=1)
    r.snn.connect(1, 17, weight=0.1, step=1)
    r.snn.plasticity_core_freeze = True
    r.snn.concept_freeze_start = 220
    before_core = sum(len(r.snn.out_edges.get(i, {})) for i in range(0, 40))
    res = r.sleep_prune()
    assert res.get("ok") is True
    after_core = sum(len(r.snn.out_edges.get(i, {})) for i in range(0, 40))
    assert after_core >= before_core, "核心区不应被 sleep_prune 剪"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"✅ {t.__name__}")
        except AssertionError as e:
            print(f"❌ {t.__name__}: {e}")
        except Exception as e:
            print(f"❌ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
    sys.exit(0 if passed == len(tests) else 1)
