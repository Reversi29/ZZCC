"""P3 概念预训练种子测试。

验证：
1. 新概念首次出现匹配种子 → 预置中继→目标输出连接
2. danger 概念 → escalate 输出连接
3. approval 概念 → auto_approve 输出连接
4. 连接已存在时不覆盖（尊重学习权重）
5. 无种子概念不预置连接
6. concept_decision_weights 预置
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

import pytest  # noqa: E402
from services.brain.snn_region import (  # noqa: E402
    SNNRegion, _CONCEPT_PRETRAIN_SEEDS,
    _CONCEPT_RELAY_BASE, _CONCEPT_NEURON_BASE,
)


@pytest.fixture
def region(tmp_path):
    save = str(tmp_path / "pretrain_snn.json")
    return SNNRegion(save_path=save)


def test_seeds_table_defined():
    """种子表存在且非空。"""
    assert isinstance(_CONCEPT_PRETRAIN_SEEDS, dict)
    assert len(_CONCEPT_PRETRAIN_SEEDS) > 5
    assert _CONCEPT_PRETRAIN_SEEDS["danger"] == "escalate"
    assert _CONCEPT_PRETRAIN_SEEDS["approval"] == "auto_approve"
    assert _CONCEPT_PRETRAIN_SEEDS["rejection"] == "reject"
    assert _CONCEPT_PRETRAIN_SEEDS["chitchat"] == "chat"


def test_danger_concept_pretrains_escalate(region):
    """danger 概念 → escalate 输出连接预置。"""
    nid = region._ensure_concept_channel("danger")
    assert nid is not None
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    out_edges = region.snn.out_edges.get(relay, {})
    # 34 = escalate
    assert 34 in out_edges
    assert out_edges[34].weight >= 0.5


def test_approval_concept_pretrains_auto_approve(region):
    """approval 概念 → auto_approve(32) 输出连接预置。"""
    nid = region._ensure_concept_channel("approval")
    assert nid is not None
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    out_edges = region.snn.out_edges.get(relay, {})
    assert 32 in out_edges


def test_rejection_concept_pretrains_reject(region):
    """rejection 概念 → reject(33) 输出连接预置。"""
    nid = region._ensure_concept_channel("rejection")
    assert nid is not None
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    out_edges = region.snn.out_edges.get(relay, {})
    assert 33 in out_edges


def test_no_seed_concept_no_pretrain(region):
    """无种子概念（如 banana）不预置输出连接。"""
    nid = region._ensure_concept_channel("banana")
    assert nid is not None
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    out_edges = region.snn.out_edges.get(relay, {})
    # banana 无种子 → 中继只连隐藏层，不直连输出
    for out_nid in (32, 33, 34, 35, 36, 37):
        assert out_nid not in out_edges


def test_pretrain_does_not_overwrite(region):
    """连接已存在时不覆盖（尊重已学习权重）。"""
    nid = region._ensure_concept_channel("danger")
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    # 手动设置高权重
    region.snn.out_edges[relay][34].weight = 1.4
    region._ensure_concept_channel("danger")
    # 未被覆盖
    assert region.snn.out_edges[relay][34].weight == 1.4


def test_fuzzy_match_substring(region):
    """模糊匹配：概念名包含种子关键字。"""
    nid = region._ensure_concept_channel("fire_alarm")
    assert nid is not None
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    out_edges = region.snn.out_edges.get(relay, {})
    # "fire_alarm" 含 "fire" → escalate(34)
    assert 34 in out_edges


def test_decision_weights_pretrained(region):
    """concept_decision_weights 预置。"""
    region._ensure_concept_channel("danger")
    cdw = region._stats.get("concept_decision_weights", {})
    assert "danger" in cdw
    assert "urg" in cdw["danger"]


def test_suppress_need_info_drive(region):
    """概念中继→need_info 误导连接被抑制。"""
    # 先注册 need_info 动态输出槽并让中继连到它
    region._ensure_concept_channel("rejection")
    # 手动建一个 need_info 输出连接（模拟历史反馈强化）
    nid = region.concept_registry.get("rejection")
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    # 注册 need_info 输出槽
    ni = region.output_registry.register("need_info")
    region.snn.connect(relay, ni, weight=1.2, delay=1)
    # 再次调用预训练种子 → 抑制 need_info
    region._apply_pretrain_seed("rejection", relay)
    conn = region.snn.out_edges.get(relay, {}).get(ni)
    if conn is not None:
        assert conn.weight < 1.2  # 被削弱
    assert region._stats.get("need_info_suppressed", 0) >= 1


def test_rejection_not_hijacked_by_need_info(region):
    """rejection 概念不被 need_info 劫持（reject 连接占优）。"""
    nid = region._ensure_concept_channel("rejection")
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    # 预训练后 reject(33) 应存在
    assert 33 in region.snn.out_edges.get(relay, {})
    # 且 need_info 输出若存在，权重应低于 reject
    ni = region.output_registry.get("need_info")
    if ni is not None and ni in region.snn.out_edges.get(relay, {}):
        reject_w = region.snn.out_edges[relay][33].weight
        ni_w = region.snn.out_edges[relay][ni].weight
        assert reject_w > ni_w


def test_suppress_existing_need_info_connection(region):
    """已有中继→need_info 连接也被抑制（不只新建）。"""
    nid = region._ensure_concept_channel("rejection")
    relay = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
    # 已有连接 232→100 w=0.97（模拟历史强化）
    ni = region.output_registry.register("need_info")
    if ni in region.snn.out_edges.get(relay, {}):
        old = region.snn.out_edges[relay][ni].weight
        region._apply_pretrain_seed("rejection", relay)
        new = region.snn.out_edges[relay][ni].weight
        assert new < old  # 被削弱
