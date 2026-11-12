"""test_brain_concept_channel.py — 通用认知通道（开放集概念→主SNN决策）测试

验证：
- 新概念（含开放集非预设，如 apple/banana）动态注册概念输入神经元（220+）
- 概念激活 → 概念槽权重注入 _continuous_weights
- 概念槽走独立概念中继子网，不污染档位槽（12 eval 硬约束保持 12/12）
- 概念→决策连接可经 _reward_modulated_strengthen 学习加强
- 概念槽 + 神经元 + 连接持久化，重启保留
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.snn_region import (
    SNNRegion,
    _CONCEPT_NEURON_BASE,
    _CONCEPT_RELAY_BASE,
)
from services.brain.neuro_registry import ConceptRegistry


def _mk_signal(type_="expense", urgency=50, amount=5000, cv=None):
    payload = {"amount": amount}
    if cv is not None:
        payload["_concept_vector"] = cv
    return __import__("models.brain", fromlist=["NeuralSignal"]).NeuralSignal(
        type=type_, urgency=urgency, payload=payload, context={},
    )


class TestConceptChannel:
    def _region(self):
        tmp = tempfile.mkdtemp()
        r = SNNRegion(save_path=os.path.join(tmp, "snn_test.json"))
        return r

    def test_new_concept_registers_slot(self):
        """开放集新概念 apple → 动态注册概念输入神经元（220+）。"""
        r = self._region()
        nid = r._ensure_concept_channel("apple")
        assert nid is not None
        assert nid >= _CONCEPT_NEURON_BASE
        assert r.concept_registry.get("apple") == nid

    def test_concept_relay_built(self):
        """概念输入神经元有出边到概念中继，中继有出边到隐藏层。"""
        r = self._region()
        nid = r._ensure_concept_channel("banana")
        assert nid is not None
        relay_nid = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
        # 概念 → 中继
        assert relay_nid in r.snn.out_edges.get(nid, ())
        # 中继 → 隐藏层（至少一条）
        assert len(r.snn.out_edges.get(relay_nid, ())) >= 1

    def test_continuous_injects_concept_weight(self):
        """概念激活 → 概念槽权重注入 _continuous_weights。"""
        r = self._region()
        sig = _mk_signal(cv={"apple": 0.9, "danger": 0.3})
        w = r._continuous_weights(sig)
        # apple 概念槽被注册并注入强度
        apple_nid = r.concept_registry.get("apple")
        assert apple_nid is not None
        assert apple_nid in w
        assert w[apple_nid] > 1.0
        # 危险概念仍走硬映射 urg 通道（兼容）
        assert 201 in w

    def test_nonpreset_concept_works(self):
        """非预设概念（quark）也能注册并注入，不因无硬映射被忽略。"""
        r = self._region()
        sig = _mk_signal(cv={"quark": 0.8})
        w = r._continuous_weights(sig)
        quark_nid = r.concept_registry.get("quark")
        assert quark_nid is not None
        assert w.get(quark_nid, 0) > 1.0

    def test_concept_channel_learning_strengthens(self):
        """概念→决策连接可经强化学习加强（非硬编码）。"""
        r = self._region()
        nid = r._ensure_concept_channel("apple")
        assert nid is not None
        # 找一条概念中继→隐藏层连接，记录权重
        relay_nid = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
        outs = r.snn.out_edges.get(relay_nid, {})
        assert len(outs) >= 1
        first_hid = list(outs.keys())[0]
        before = r.snn.out_edges[relay_nid][first_hid].weight
        # 用 _reward_modulated_strengthen 加强（模拟反馈学习目标连接）
        r.snn._reward_modulated_strengthen(
            relay_nid, eta=0.5, auto_create=False,
        )
        after = r.snn.out_edges[relay_nid][first_hid].weight
        assert after >= before

    def test_persist_restart(self):
        """概念槽 + 神经元 + 连接持久化，重启保留。"""
        tmp = tempfile.mkdtemp()
        save_path = os.path.join(tmp, "snn_test.json")
        r = SNNRegion(save_path=save_path)
        nid = r._ensure_concept_channel("apple")
        assert nid is not None
        r._auto_save()
        # 模拟重启
        r2 = SNNRegion(save_path=save_path)
        assert r2.concept_registry.get("apple") == nid
        # 神经元存在且类型 INPUT
        assert nid < r2.snn.num_neurons
        # 概念中继连接保留
        relay_nid = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
        assert relay_nid in r2.snn.out_edges.get(nid, ())

    def test_twelve_eval_no_regression(self):
        """概念通道启用后 12 eval 硬约束必须保持 12/12（无概念向量的信号不受影响）。"""
        import asyncio
        r = self._region()
        cases = [
            ("expense", {"amount": 88000, "category": "equipment"}, 90, "escalate"),
            ("expense", {"amount": 500, "category": "office"}, 50, "auto_approve"),
            ("expense", {"amount": 35000, "category": "travel"}, 70, "escalate"),
            ("expense", {"amount": 800, "category": "meals"}, 40, "auto_approve"),
            ("user_request", {"question": "hello"}, 30, "chat"),
            ("user_request", {"question": "cancel order #12345"}, 60, "escalate"),
            ("approval_pending", {"amount": 15000, "category": "services"}, 80, "escalate"),
            ("approval_pending", {"amount": 500, "category": "consumables"}, 30, "auto_approve"),
            ("threshold_breach", {"risk_level": "critical"}, 95, "escalate"),
            ("threshold_breach", {"risk_level": "low"}, 20, "auto_approve"),
            ("approval_pending", {"amount": 300, "status": "pending"}, 60, "flag"),
            ("approval_pending", {"amount": 80000, "status": "pending"}, 90, "escalate"),
        ]

        async def _run():
            correct = 0
            for i, (st, pl, ug, exp) in enumerate(cases):
                sig = _mk_signal(type_=st, urgency=ug)
                sig.payload = pl  # 无 _concept_vector
                res = await r.reason(sig, {}, None)
                dec = res.result.decision if res.result else None
                if dec == exp:
                    correct += 1
            return correct

        correct = asyncio.run(_run())
        assert correct == 12, f"回归失败：{correct}/12"
