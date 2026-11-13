"""顶层 LLM 降级修复：空 reasoning 的 need_info 应被过滤

背景：LLM 限流/超时/返回空时，coordinator 会得到 decision="need_info"
但 reasoning 为空的"空壳结果"。这类结果不是真决策，会以 reasoning_level=3
污染最终 level 并压制本地脑区的可用决策，表现为 /brain/ask 莫名返回
need_info（conf 恰为 0.7 上限）。

修复：融合前过滤空壳 need_info，让 SNN/规则降级承接。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

import pytest  # noqa: E402
from services.brain.coordinator import RegionCoordinator, RegionResult  # noqa: E402
from models.brain import CognitionResult, NeuralSignal  # noqa: E402


def _sig():
    return NeuralSignal(id="t1", type="expense",
                       payload={"amount": 500, "category": "office"},
                       source="test", urgency=50)


def _res(region, decision, conf, level, reasoning=""):
    return RegionResult(
        region=region, ok=True,
        result=CognitionResult(
            signal_id="t1", reasoning_level=level, confidence=conf,
            decision=decision, reasoning=reasoning,
        ),
    )


def test_empty_need_info_dropped():
    """LLM 空壳 need_info（reasoning 空）应被过滤，由规则承接。"""
    c = RegionCoordinator()
    results = [
        _res("llm", "need_info", 0.7, 3, ""),      # 空壳，应丢弃
        _res("rule", "auto_approve", 0.5, 1, "小额办公"),
    ]
    out = c._integrate(_sig(), results, {})
    assert out.decision == "auto_approve"
    assert out.reasoning_level == 1   # 未被 level=3 污染


def test_substantive_need_info_kept():
    """带 reasoning 的 need_info 是真决策（缺信息），应保留不被过滤。"""
    c = RegionCoordinator()
    results = [
        _res("llm", "need_info", 0.7, 3, "缺少发票号，需补充"),
        _res("rule", "auto_approve", 0.5, 1, "小额"),
    ]
    out = c._integrate(_sig(), results, {})
    assert out.decision == "need_info"
    assert out.reasoning_level == 3


def test_whitespace_reasoning_dropped():
    """纯空格的 reasoning 视为空壳，应丢弃。"""
    c = RegionCoordinator()
    results = [
        _res("llm", "need_info", 0.7, 3, "   "),
        _res("rule", "escalate", 0.6, 1, "大额"),
    ]
    out = c._integrate(_sig(), results, {})
    assert out.decision == "escalate"


def test_all_empty_falls_to_no_action():
    """全部为空壳 need_info 时应降级到 no_action 兜底，而非输出 need_info。"""
    c = RegionCoordinator()
    results = [_res("llm", "need_info", 0.7, 3, "")]
    out = c._integrate(_sig(), results, {})
    assert out.decision == "no_action"
