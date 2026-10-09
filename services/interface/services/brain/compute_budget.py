"""services/brain/compute_budget.py — 算力/资源分配层

在丘脑与各脑区之间的资源管理层，负责：
- 按意图与紧急度动态分配时间/Token/成本预算
- 执行截止时间（deadline）约束
- 优雅降级：超预算的脑区自动跳过
- 追踪实际使用量与配额消耗

设计原则：
1. 预算是软上限——单个脑区超支不影响其他脑区并行执行
2. 高紧急度信号获得更高预算（如 alert 比 chitchat 多 5x LLM 预算）
3. LLM 调用按 Token 计费，统计/规则按毫秒计费
4. 所有预算操作是同步的，零 I/O 开销
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Intent(str, Enum):
    """信号意图分类——由丘脑 classify() 产出。"""
    BUSINESS = "business"    # 业务请求：审批/报销/采购
    ALERT = "alert"          # 告警：异常/失败/风险
    QUERY = "query"          # 知识查询：是什么/怎么
    CHITCHAT = "chitchat"    # 闲聊：问候/寒暄
    SYSTEM = "system"        # 系统事件：健康检查/内部
    NOISE = "noise"          # 噪声：无意义/极短


# 各意图的默认预算（毫秒/Token）
_DEFAULT_BUDGETS: Dict[Intent, Dict[str, Dict[str, float]]] = {
    Intent.BUSINESS: {
        "rule":        {"time_ms": 50,   "tokens": 0},
        "statistical": {"time_ms": 200,  "tokens": 0},
        "llm":         {"time_ms": 30000, "tokens": 2048},
        "snn":         {"time_ms": 500,  "tokens": 0},
        "semantic":    {"time_ms": 1500, "tokens": 0},
        "episodic":    {"time_ms": 500,  "tokens": 0},
        "web_search":  {"time_ms": 0,    "tokens": 0},  # 业务默认不联网（避免噪声）
    },
    Intent.ALERT: {
        "rule":        {"time_ms": 50,   "tokens": 0},
        "statistical": {"time_ms": 0,    "tokens": 0},  # 告警不套历史审批模式
        "llm":         {"time_ms": 45000, "tokens": 4096},
        "snn":         {"time_ms": 0,    "tokens": 0},  # 告警不走 SNN（非业务决策）
        "semantic":    {"time_ms": 2000, "tokens": 0},
        "episodic":    {"time_ms": 800,  "tokens": 0},
        "web_search":  {"time_ms": 0,    "tokens": 0},  # 告警不联网
    },
    Intent.QUERY: {
        "rule":        {"time_ms": 50,   "tokens": 0},
        "statistical": {"time_ms": 0,    "tokens": 0},  # 查询不查历史审批模式
        "llm":         {"time_ms": 20000, "tokens": 1024},
        "snn":         {"time_ms": 0,    "tokens": 0},  # 查询不走 SNN
        "semantic":    {"time_ms": 2000, "tokens": 0},
        "episodic":    {"time_ms": 500,  "tokens": 0},
        "web_search":  {"time_ms": 8000, "tokens": 0},  # 查询允许联网搜索
    },
    Intent.CHITCHAT: {
        "rule":        {"time_ms": 30,   "tokens": 0},
        "statistical": {"time_ms": 0,    "tokens": 0},  # 闲聊不查历史模式
        "llm":         {"time_ms": 10000, "tokens": 512},
        "snn":         {"time_ms": 0,    "tokens": 0},  # 闲聊不激活 SNN（避免误审批）
        "semantic":    {"time_ms": 0,    "tokens": 0},  # 闲聊不查语义记忆
        "episodic":    {"time_ms": 300,  "tokens": 0},
        "web_search":  {"time_ms": 0,    "tokens": 0},  # 闲聊不联网
    },
    Intent.SYSTEM: {
        "rule":        {"time_ms": 30,   "tokens": 0},
        "statistical": {"time_ms": 100,  "tokens": 0},
        "llm":         {"time_ms": 5000, "tokens": 256},
        "snn":         {"time_ms": 0,    "tokens": 0},  # 系统事件不走 SNN
        "semantic":    {"time_ms": 500,  "tokens": 0},
        "episodic":    {"time_ms": 200,  "tokens": 0},
        "web_search":  {"time_ms": 0,    "tokens": 0},  # 系统事件不联网
    },
    Intent.NOISE: {
        "rule":        {"time_ms": 30,   "tokens": 0},
        "statistical": {"time_ms": 0,    "tokens": 0},
        "llm":         {"time_ms": 0,    "tokens": 0},  # 噪声不消耗算力
        "snn":         {"time_ms": 0,    "tokens": 0},  # 噪声不激活 SNN
        "semantic":    {"time_ms": 0,    "tokens": 0},
        "episodic":    {"time_ms": 0,    "tokens": 0},
        "web_search":  {"time_ms": 0,    "tokens": 0},  # 噪声不联网
    },
}

# 紧急度系数：urgency=50 时为 1.0，urgency=100 时为 1.5x
_URGENCY_SCALE = {
    "low":    0.7,   # urgency < 30
    "normal": 1.0,   # 30 <= urgency < 70
    "high":   1.3,   # 70 <= urgency < 90
    "critical": 1.5, # urgency >= 90
}


@dataclass
class RegionBudget:
    """单个脑区的预算。"""
    time_ms: float = 0.0
    tokens: int = 0
    allowed: bool = True  # False 表示该意图下此脑区不激活

    def scaled(self, factor: float) -> "RegionBudget":
        return RegionBudget(
            time_ms=self.time_ms * factor,
            tokens=int(self.tokens * factor) if self.tokens > 0 else 0,
            allowed=self.allowed,
        )


@dataclass
class Usage:
    """单个脑区的实际使用量。"""
    time_ms: float = 0.0
    tokens: int = 0
    ok: bool = True
    error: str = ""
    timeout: bool = False


@dataclass
class BudgetReport:
    """整次推理的预算使用报告。"""
    intent: Intent
    urgency_tier: str
    scale_factor: float
    regions: Dict[str, Usage] = field(default_factory=dict)
    total_time_ms: float = 0.0
    total_tokens: int = 0
    degraded: bool = False  # True 表示有脑区因超预算被跳过
    skip_reasons: Dict[str, str] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    deadline_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "urgency_tier": self.urgency_tier,
            "scale_factor": self.scale_factor,
            "regions": {
                k: {"time_ms": round(v.time_ms, 1), "tokens": v.tokens,
                    "ok": v.ok, "timeout": v.timeout, "error": v.error}
                for k, v in self.regions.items()
            },
            "total_time_ms": round(self.total_time_ms, 1),
            "total_tokens": self.total_tokens,
            "degraded": self.degraded,
            "skip_reasons": self.skip_reasons,
        }


class ComputeBudget:
    """算力预算分配器。

    用法：
        budget = ComputeBudget()
        plan = budget.allocate(Intent.BUSINESS, urgency=50)
        # 各脑区并行执行，拿到自己的 RegionBudget
        llm_budget = plan["llm"]  # RegionBudget(time_ms=30000, tokens=2048, allowed=True)
        # 执行后记录使用量
        budget.record("llm", time_ms=25000, tokens=1500)
        report = budget.report()
    """

    def __init__(self, max_total_time_ms: float = 60000.0):
        self._plans: Dict[str, Dict[str, RegionBudget]] = {}
        self._usages: Dict[str, Usage] = {}
        self._max_total_time_ms = max_total_time_ms

    @staticmethod
    def _urgency_tier(urgency: int) -> str:
        if urgency < 30:
            return "low"
        if urgency < 70:
            return "normal"
        if urgency < 90:
            return "high"
        return "critical"

    def allocate(self, intent: Intent, urgency: int = 50) -> Dict[str, RegionBudget]:
        """按意图与紧急度分配预算。

        返回 {region_name: RegionBudget}。
        urgency 影响缩放系数（high=1.3x, critical=1.5x），影响所有脑区。
        """
        tier = self._urgency_tier(urgency)
        factor = _URGENCY_SCALE[tier]
        defaults = _DEFAULT_BUDGETS.get(intent, _DEFAULT_BUDGETS[Intent.BUSINESS])
        plan: Dict[str, RegionBudget] = {}
        for region, b in defaults.items():
            budget = RegionBudget(
                time_ms=b["time_ms"] * factor if b["time_ms"] > 0 else 0,
                tokens=int(b["tokens"] * factor) if b["tokens"] > 0 else 0,
                allowed=b["time_ms"] > 0 or b["tokens"] > 0,
            )
            plan[region] = budget
        self._plans[intent.value] = plan
        self._usages.clear()
        return plan

    def record(self, region: str, time_ms: float = 0.0, tokens: int = 0,
               ok: bool = True, error: str = "", timeout: bool = False) -> None:
        """记录单个脑区的实际使用量。"""
        self._usages[region] = Usage(
            time_ms=time_ms, tokens=tokens, ok=ok, error=error, timeout=timeout
        )

    def report(self, intent: Intent, urgency: int = 50) -> BudgetReport:
        """生成预算使用报告。"""
        tier = self._urgency_tier(urgency)
        factor = _URGENCY_SCALE[tier]
        plan = self._plans.get(intent.value, {})
        total_time = sum(u.time_ms for u in self._usages.values())
        total_tokens = sum(u.tokens for u in self._usages.values())
        skip_reasons: Dict[str, str] = {}
        for region, b in plan.items():
            if not b.allowed:
                skip_reasons[region] = f"intent={intent.value} 不激活此脑区"
            elif region not in self._usages:
                skip_reasons[region] = "未执行（可能被降级）"
            elif self._usages[region].timeout:
                skip_reasons[region] = "超时"
        return BudgetReport(
            intent=intent,
            urgency_tier=tier,
            scale_factor=factor,
            regions=dict(self._usages),
            total_time_ms=total_time,
            total_tokens=total_tokens,
            degraded=bool(skip_reasons),
            skip_reasons=skip_reasons,
            deadline_ms=total_time,
        )

    @staticmethod
    def should_timeout(region: str, budget: Optional[RegionBudget], elapsed_ms: float) -> bool:
        """判断某脑区是否已超出其时间预算。"""
        if budget is None or not budget.allowed:
            return False
        if budget.time_ms <= 0:
            return False
        return elapsed_ms > budget.time_ms
