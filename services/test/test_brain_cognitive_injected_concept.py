"""测试 cognitive_coder.encode 合并 payload 注入的开放集概念。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.brain.cognitive_coder import CognitiveCoder


@pytest.fixture
def coder():
    c = CognitiveCoder()
    c.use_snn_encoding = False  # 规则式，确定性
    yield c


def test_injected_concept_merged(coder):
    """payload 显式注入的开放集概念应被合并（非覆盖）。"""
    cv = coder.encode(
        text="500元香蕉采购需要审批",
        payload={"amount": 500, "_concept_vector": {"banana": 0.9}},
    )
    concepts = dict(cv.concepts)
    # 规则式应提取 approval（采购），注入应保留 banana
    assert "banana" in concepts, f"banana missing: {concepts}"
    assert concepts["banana"] >= 0.8, f"banana too weak: {concepts['banana']}"
    assert "approval" in concepts, f"approval missing: {concepts}"


def test_injected_concept_no_override(coder):
    """注入概念不应覆盖规则式提取（共存取高）。"""
    cv = coder.encode(
        text="500元香蕉采购需要审批",
        payload={"amount": 500, "_concept_vector": {"approval": 0.3}},
    )
    concepts = dict(cv.concepts)
    # approval 规则式应达 1.0（采购/审批），注入 0.3 不应拉低
    assert concepts.get("approval", 0) >= 0.8, f"approval overridden: {concepts}"


def test_injected_concept_empty(coder):
    """无注入概念时行为不变。"""
    cv = coder.encode(text="500元香蕉采购需要审批", payload={"amount": 500})
    concepts = dict(cv.concepts)
    assert "banana" not in concepts
    assert concepts.get("approval", 0) >= 0.8


def test_injected_concept_invalid_types(coder):
    """非数值注入概念应被忽略。"""
    cv = coder.encode(
        text="500元采购",
        payload={"amount": 500, "_concept_vector": {"bad": "not_number", "ok": 0.8}},
    )
    concepts = dict(cv.concepts)
    assert "bad" not in concepts
    assert concepts.get("ok", 0) >= 0.7
