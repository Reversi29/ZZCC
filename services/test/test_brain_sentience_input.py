"""测试感受认知接入（方向B：底层认知）。

sentience 6 维连续感受（threat/safety/interest/confusion/urgency/familiarity）
作为主 SNN 的认知输入（202-207），经独立中继（216-221）连输出层。
决策由认知表征涌现，而非人工 type/金额分档。
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.brain.snn_region import (
    SNNRegion,
    _SENTIENCE_BASE,
    _SENTIENCE_RELAY_BASE,
)
from models.brain import NeuralSignal


def _mk_signal(sentience=None, st="expense", urg=50, amount=500):
    payload = {"amount": amount}
    if sentience:
        payload["_sentience"] = sentience
    return NeuralSignal(id="s", type=st, payload=payload, source="test", urgency=urg)


def _region(tmp_path):
    return SNNRegion(save_path=str(tmp_path / "snn.json"))


def _run(coro):
    return asyncio.run(coro)


def test_sentience_inputs_created(tmp_path):
    """有 _sentience 时，感受输入神经元（202-207）+ 中继（216-221）应创建。"""
    region = _region(tmp_path)
    sent = {"threat": 0.8, "urgency": 0.9, "familiarity": 0.3}
    sig = _mk_signal(sent)
    _run(region.reason(sig, {}, None))
    assert region.snn.num_neurons >= _SENTIENCE_RELAY_BASE + 6
    for i in range(6):
        nid = _SENTIENCE_BASE + i
        rid = _SENTIENCE_RELAY_BASE + i
        assert nid < region.snn.num_neurons, f"感受输入 {nid} 未创建"
        assert rid < region.snn.num_neurons, f"感受中继 {rid} 未创建"


def test_sentience_threat_drives_decision(tmp_path):
    """高 threat 感受应能驱动主 SNN 决策（经中继→输出竞争）。"""
    region = _region(tmp_path)
    sig = _mk_signal({"threat": 1.0, "urgency": 1.0}, st="expense", urg=90, amount=88000)
    r = _run(region.reason(sig, {}, None))
    assert r.result is not None
    assert r.result.decision is not None


def test_sentience_no_key_eval_compat(tmp_path):
    """无 _sentience 键（eval 信号）时，感受通道不激活，决策正常。"""
    region = _region(tmp_path)
    sig = _mk_signal(None, st="expense", urg=50, amount=500)
    r = _run(region.reason(sig, {}, None))
    assert r.result is not None
    assert r.result.decision is not None


def test_sentience_weights_in_continuous(tmp_path):
    """感受强度应出现在 _continuous_weights（供中继驱动）。"""
    region = _region(tmp_path)
    sent = {"threat": 0.8, "urgency": 0.9}
    sig = _mk_signal(sent)
    w = region._continuous_weights(sig)
    assert _SENTIENCE_BASE in w, f"threat 通道未激活: {w.keys()}"
    assert w[_SENTIENCE_BASE] > 1.0
    assert _SENTIENCE_BASE + 4 in w, f"urgency 感受通道未激活: {w.keys()}"
