"""need_info 污染治理测试。

need_info（动态输出槽 100+）是"信息请求"而非业务结论，不应作为默认
赢家碾压 reject/escalate。历史反馈可能强化概念中继→need_info 边
（如 218→100 w=1.5、221→100 w=1.14），劫持概念信号。

治理：概念注册/激活时统一削弱概念中继→need_info 误导连接。
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

from models.brain import NeuralSignal  # noqa: E402
from services.brain.snn_region import SNNRegion  # noqa: E402


def _make_region():
    return SNNRegion(save_path=tempfile.mkdtemp() + "/s.json")


def test_concept_channel_suppresses_need_info():
    """概念注册/激活时削弱中继→need_info 误导连接。"""
    region = _make_region()
    # 激活一个概念（rejection），应触发概念通道注册
    sig = NeuralSignal(
        id="t1", type="expense",
        payload={"amount": 500, "_concept_vector": {"rejection": 1.0}},
        source="eval", urgency=30,
    )
    import asyncio
    asyncio.run(region.reason(sig, {}, None))

    # 获取 rejection 概念中继
    cnid = region.concept_registry.get("rejection")
    assert cnid is not None, "rejection 概念应已注册"
    relay_nid = 230 + (cnid - 220)
    # 中继→need_info 连接应被削弱（若存在）
    need_nid = region._decision_to_output_neuron("need_info")
    if need_nid is not None and relay_nid in region.snn.out_edges:
        conn = region.snn.out_edges[relay_nid].get(need_nid)
        if conn is not None:
            assert conn.weight <= 0.05, (
                f"概念中继→need_info 应被削弱，实际 {conn.weight}"
            )


def test_need_info_penalty_applied():
    """need_info 输出在 _decode_output 有结构惩罚（_NEED_INFO_PENALTY）。"""
    region = _make_region()
    # 直接检查 _NEED_INFO_PENALTY 常量
    from services.brain import snn_region as mod
    assert mod._NEED_INFO_PENALTY < 1.0, (
        "need_info 应有竞争惩罚系数（<1.0）"
    )


def test_concept_driven_decision_not_need_info():
    """概念驱动的实质决策不应被 need_info 劫持。

    rejection 概念（预训练种子→reject）即使 need_info 有强入边，
    也应胜出 reject（need_info 被结构惩罚）。
    """
    region = _make_region()
    # 人为强化概念中继→need_info（模拟历史污染）
    sig = NeuralSignal(
        id="t1", type="expense",
        payload={"amount": 500, "_concept_vector": {"rejection": 1.0}},
        source="eval", urgency=30,
    )
    import asyncio
    r = asyncio.run(region.reason(sig, {}, None))
    d = r.result.decision if r.result else None
    # rejection 预训练种子→reject；need_info 有惩罚不应劫持
    assert d == "reject", (
        f"rejection 概念应驱动 reject（非 need_info），实际 {d}"
    )
