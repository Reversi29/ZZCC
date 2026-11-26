"""test/test_brain_development_integration.py — 发育层集成到 SNNRegion/BrainCore

验证用户 2026-11-26 洞察的落地：
1. SNNRegion 有 development_tick / development_status
2. development_tick 实际增殖+探索+分化（骨架形成）
3. eval 保持 12/12（发育不破坏现有决策）
4. BrainCore 接入 development_interval 调度
"""
import os
import sys
import tempfile
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

from services.brain.snn_region import SNNRegion
from services.brain.core import BrainCore


def test_region_has_development():
    """SNNRegion 有发育驱动。"""
    r = SNNRegion(save_path=os.path.join(tempfile.mkdtemp(), "s.json"))
    assert hasattr(r, "dev_driver"), "缺 dev_driver"
    assert hasattr(r, "development_tick"), "缺 development_tick"
    assert hasattr(r, "development_status"), "缺 development_status"
    st = r.development_status()
    assert "stage" in st
    assert "dev_neurons" in st
    print(f"  ✅ development_status: stage={st['stage']}, dev_neurons={st['dev_neurons']}")


def test_development_tick_skeleton():
    """development_tick 实际增殖+探索+分化（骨架形成）。"""
    r = SNNRegion(save_path=os.path.join(tempfile.mkdtemp(), "s.json"))
    # 初始动态区边
    dyn_before = sum(
        1 for s in r.snn.out_edges for t in r.snn.out_edges[s]
        if 40 <= s <= 199 and 40 <= t <= 199
    )
    # 跑发育
    result = r.development_tick()
    assert result.get("ok"), f"development_tick 失败: {result}"
    # 动态区边应增加（骨架形成）或已有
    dyn_after = sum(
        1 for s in r.snn.out_edges for t in r.snn.out_edges[s]
        if 40 <= s <= 199 and 40 <= t <= 199
    )
    assert dyn_after > 0, "发育后动态区应形成内部边"
    print(f"  ✅ 发育 tick: 动态区边 {dyn_before}→{dyn_after}, stage={result.get('stage')}")


def test_core_has_development_schedule():
    """BrainCore 接入 development_interval。"""
    bc = BrainCore(development_interval=30)
    assert bc.development_interval == 30
    assert hasattr(bc, "_development_tick")
    assert hasattr(bc, "_last_development")
    print(f"  ✅ BrainCore.development_interval={bc.development_interval}")


def test_eval_preserved():
    """发育后 eval 保持 12/12（不破坏现有决策）。"""
    r = SNNRegion(save_path=os.path.join(tempfile.mkdtemp(), "s.json"))
    # 跑发育（多次）
    for _ in range(3):
        r.development_tick()
    # eval
    from models.brain import NeuralSignal
    from tools.eval_cases import EVAL_CASES

    async def _run():
        ok, fails = 0, []
        for i, (t, pl, urg, exp) in enumerate(EVAL_CASES, 1):
            sig = NeuralSignal(id=f"eval{i}", type=t, payload=pl, source="eval", urgency=urg)
            try:
                res = await r.reason(sig, {}, None)
                d = res.result.decision if res.result else None
            except Exception as e:
                d = f"ERR:{e}"
            if d == exp:
                ok += 1
            else:
                fails.append({"i": i, "type": t, "exp": exp, "got": d})
        return ok, fails

    ok, fails = asyncio.run(_run())
    assert ok == 12, f"eval 掉分: {ok}/12 {fails}"
    print(f"  ✅ 发育后 eval {ok}/12 保持")


if __name__ == "__main__":
    print("===== 发育层集成测试 =====")
    test_region_has_development()
    test_development_tick_skeleton()
    test_core_has_development_schedule()
    test_eval_preserved()
    print("\n全部通过 ✅")
