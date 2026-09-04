"""models/brain.py — 类脑 AI 数据模型

定义 NeuralSignal（感知信号）、CognitionResult（认知结果）、Action（行动）等核心数据结构。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional


def _uuid() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ── 行动 ──
@dataclass
class Action:
    """类脑系统的行动指令。

    通过 ActionExecutor 统一执行，所有行动可审计。
    """
    type: str                              # approve / reject / escalate / create_document / send_notification / trigger_flow / ...
    params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""                       # 为什么执行此行动
    priority: int = 5                      # 1-10

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "params": self.params,
            "reason": self.reason,
            "priority": self.priority,
        }


# ── 感知信号 ──
@dataclass
class NeuralSignal:
    """感知层输入信号——类脑系统的统一输入单元。"""
    type: str                              # approval_pending / threshold_breach / plugin_event / user_request / cron_alert / external_event
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "manual"                 # api_call / event_bus / webhook / cron / manual
    urgency: int = 50                      # 0-100，影响注意力分配
    context: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=_uuid)
    created_at: str = field(default_factory=_now_iso)
    processed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "source": self.source,
            "urgency": self.urgency,
            "context": self.context,
            "created_at": self.created_at,
            "processed": self.processed,
        }


# ── 认知结果 ──
@dataclass
class CognitionResult:
    """推理引擎输出——类脑系统的核心决策。"""
    reasoning_level: int                   # 1=规则 / 2=统计 / 3=LLM
    confidence: float                      # 0.0-1.0
    decision: str                          # auto_approve / reject / escalate / flag / need_info / no_action
    reasoning: str                         # 推理过程说明
    signal_id: str = ""                    # 由 reason() 方法在返回前注入
    actions: List[Action] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    memory_updates: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "reasoning_level": self.reasoning_level,
            "confidence": self.confidence,
            "decision": self.decision,
            "reasoning": self.reasoning,
            "actions": [a.to_dict() for a in self.actions],
            "risks": self.risks,
            "memory_updates": self.memory_updates,
            "created_at": self.created_at,
        }


# ── 规则定义 ──
@dataclass
class BrainRule:
    """L1 规则引擎的规则。

    condition 是 Callable[[dict, dict], bool]：
      - 第一个参数 signal.payload
      - 第二个参数 signal.context
    """
    id: str
    module: str                            # procurement / expense / hr / ...
    condition: Any                         # Callable[[dict, dict], bool]
    action: str                            # approve / reject / escalate / flag / need_info
    confidence: float = 0.8
    description: str = ""
    enabled: bool = True

    def matches(self, payload: Dict[str, Any], context: Dict[str, Any]) -> bool:
        try:
            return bool(self.condition(payload, context))
        except Exception:
            return False


# ── 记忆条目 ──
@dataclass
class MemoryEntry:
    """长期记忆条目。"""
    type: str                              # pattern / rule / feedback / lesson / preference
    module: str                            # procurement / expense / ...
    key: str
    value: Dict[str, Any]
    confidence: float = 0.5
    hit_count: int = 0
    miss_count: int = 0
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "module": self.module,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
