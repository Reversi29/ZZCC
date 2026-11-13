"""测试方向C：感受中继速率编码（持续注入）。

sustain_weights 持续注入感受通道（202-207），感受中继（216-221）真正
速率编码放电（强度越高中继放电越频繁），驱动输出竞争。
档位槽保持一次性注入（不破坏 AND 门）。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.brain.snn_region import SNNRegion, _SENTIENCE_RELAY_BASE
from models.brain import NeuralSignal


def _run(coro):
    return asyncio.run(coro)


def _mk(sentience=None, st="expense", urg=50, amount=500):
    payload = {"amount": amount}
    if sentience:
        payload["_sentience"] = sentience
    return NeuralSignal(id="s", type=st, payload=payload, source="test", urgency=urg)


def test_sentience_relay_rate_encoding(tmp_path):
    """感受中继速率编码：sustain_weights 持续注入 → 中继放电。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    sig = _mk({"threat": 1.0, "urgency": 1.0})
    r = _run(region.reason(sig, {}, None))
    cr = r.result
    active = cr.memory_updates.get("snn_active", []) if cr else []
    # 感受中继（216-221）应放电（速率编码）
    relay_fired = [n for n in active if _SENTIENCE_RELAY_BASE <= n < _SENTIENCE_RELAY_BASE + 6]
    assert relay_fired, f"感受中继未放电: {active}"


def test_sentience_relay_no_eval_pollution(tmp_path):
    """eval 信号（无 _sentience）→ sustain_weights 空 → 不污染档位决策。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    # 12 eval 场景之一：expense 500 → auto_approve
    sig = _mk(None, st="expense", urg=50, amount=500)
    r = _run(region.reason(sig, {}, None))
    assert r.result is not None
    assert r.result.decision in ("auto_approve", "approve")


def test_sentience_rate_encoding_specificity(tmp_path):
    """学习 escalate 后，威胁高（速率编码）参与竞争（conf 梯度）。"""
    region = SNNRegion(save_path=str(tmp_path / "snn.json"))
    sig = _mk({"threat": 1.0})
    _run(region.reason(sig, {}, None))
    for _ in range(10):
        region.train_from_feedback(sig, "escalate", True, wrong_decision=None)
    r = _run(region.reason(sig, {}, None))
    # 威胁高 → escalate 中继权重已加强
    w = region.snn.out_edges.get(_SENTIENCE_RELAY_BASE, {}).get(34)
    assert w is not None and w.weight > 1.0, f"threat 中继→escalate 未加强: {w}"
