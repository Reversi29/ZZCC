"""测试方向D：概念槽驱动加成——SNN 概念槽特异性学习胜出。

概念中继（230+）驱动输出时有决策话语权加成（_CONCEPT_DRIVE_BOOST），
避免概念槽特异性学习（如 banana→reject）被档位槽隐藏层 escalate 路径压制。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.brain.snn_region import SNNRegion
from models.brain import NeuralSignal


def _run(coro):
    return asyncio.run(coro)


def _mk_concept(concepts, amount=500):
    return NeuralSignal(
        id="b", type="expense",
        payload={"amount": amount, "_concept_vector": dict(concepts)},
        source="test", urgency=50,
    )


def test_concept_drive_boost(tmp_path):
    """概念槽学习 reject 后，banana 概念驱动决策胜出（不被 escalate 压制）。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    sig = _mk_concept({"approval": 1.0, "banana": 0.9})
    _run(region.reason(sig, {}, None))
    for _ in range(8):
        region.train_from_feedback(sig, "reject", True, wrong_decision=None)
    r = _run(region.reason(sig, {}, None))
    # 概念槽特异性：banana → reject（概念驱动加成后胜出）
    assert r.result is not None
    assert r.result.decision == "reject", f"概念槽 reject 未胜出: {r.result.decision}"
    # 竞争明细：reject 分数应高于 escalate（概念驱动加成生效）
    comp = r.result.memory_updates.get("snn_competition", [])
    rej_score = next((c["score"] for c in comp if c["decision"] == "reject"), 0)
    esc_score = next((c["score"] for c in comp if c["decision"] == "escalate"), 0)
    assert rej_score > esc_score, f"reject({rej_score}) 未胜 escalate({esc_score})"


def test_concept_drive_no_pollution(tmp_path):
    """无概念向量 → 概念中继不放电 → 不污染（auto_approve）。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    sig = _mk_concept({"approval": 1.0, "banana": 0.9})
    _run(region.reason(sig, {}, None))
    for _ in range(8):
        region.train_from_feedback(sig, "reject", True, wrong_decision=None)
    # 对照：无概念向量
    sig2 = NeuralSignal(id="c", type="expense", payload={"amount": 500}, source="test", urgency=50)
    r2 = _run(region.reason(sig2, {}, None))
    assert r2.result is not None
    assert r2.result.decision == "auto_approve", f"概念污染: {r2.result.decision}"


def test_eval_12_no_concept_pollution(tmp_path):
    """12 eval 场景（无概念向量）保持——概念驱动加成不影响。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    # expense 500 → auto_approve（eval 场景）
    sig = NeuralSignal(id="e", type="expense", payload={"amount": 500}, source="test", urgency=50)
    r = _run(region.reason(sig, {}, None))
    assert r.result is not None
    assert r.result.decision in ("auto_approve", "approve")
