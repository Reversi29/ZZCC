"""services/brain/rules.py — L1 规则引擎

- 全局规则注册表：register_rule / unregister_rule / list_rules
- 插件可通过 sdk.brain_rule 装饰器注入规则
- 支持按 module 分组、按 enabled 过滤
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, List, Optional

from models.brain import BrainRule

logger = logging.getLogger("brain.rules")

# 规则注册表（全局，线程安全）
_LOCK = threading.RLock()
_RULES: Dict[str, BrainRule] = {}


def register_rule(rule: BrainRule) -> BrainRule:
    """注册一条规则。同 id 会被覆盖。"""
    with _LOCK:
        _RULES[rule.id] = rule
    return rule


def unregister_rule(rule_id: str) -> bool:
    with _LOCK:
        return _RULES.pop(rule_id, None) is not None


def get_rule(rule_id: str) -> Optional[BrainRule]:
    with _LOCK:
        return _RULES.get(rule_id)


def list_rules(module: Optional[str] = None, enabled_only: bool = True) -> List[BrainRule]:
    with _LOCK:
        rules = list(_RULES.values())
    if enabled_only:
        rules = [r for r in rules if r.enabled]
    if module:
        rules = [r for r in rules if r.module == module]
    # 按 id 排序，保证稳定
    return sorted(rules, key=lambda r: r.id)


def set_enabled(rule_id: str, enabled: bool) -> bool:
    with _LOCK:
        r = _RULES.get(rule_id)
        if not r:
            return False
        r.enabled = enabled
        return True


# ═══════════════════════════════════════════════════════════
# 内置默认规则（ZZCC services 场景）
# ═══════════════════════════════════════════════════════════
def _builtin_rules() -> List[BrainRule]:
    """ZZCC services 内置规则——业务无关的通用兜底规则。"""
    return [
        BrainRule(
            id="builtin.empty_payload_flag",
            module="core",
            condition=lambda p, c: not p,
            action="need_info",
            confidence=0.9,
            description="空 payload 无法推理，需要补充信息",
        ),
        BrainRule(
            id="builtin.high_urgency_escalate",
            module="core",
            condition=lambda p, c: c.get("urgency", 0) >= 90,
            action="escalate",
            confidence=0.85,
            description="紧急度≥90 的信号升级处理",
        ),
        BrainRule(
            id="builtin.low_urgency_no_action",
            module="core",
            condition=lambda p, c: c.get("urgency", 0) <= 10,
            action="no_action",
            confidence=0.75,
            description="紧急度≤10 的信号忽略",
        ),
        # 业务规则（示例，ZZCC services 场景：chat 消息风控）
        BrainRule(
            id="chat.sensitive_content_flag",
            module="chat",
            condition=lambda p, c: any(k in str(p.get("content", "")).lower()
                                       for k in ["违法", "攻击", "勒索", "诈骗"]),
            action="flag",
            confidence=0.9,
            description="聊天消息含敏感词标记",
        ),
        BrainRule(
            id="chat.spam_pattern_flag",
            module="chat",
            condition=lambda p, c: (
                (p.get("msg_count_1h", 0) or 0) >= 30
                and (p.get("unique_recipients_1h", 0) or 0) >= 20
            ),
            action="flag",
            confidence=0.88,
            description="1小时内≥30条消息且≥20个不同收件人疑似刷消息",
        ),
        # 审批类规则（复用 OA 语义，ZZCC services 未来接入 ERP 单据时使用）
        BrainRule(
            id="expense.small_auto_approve",
            module="expense",
            condition=lambda p, c: (
                0 < (p.get("amount", 0) or 0) <= 1000
                and p.get("doctype") in ("ExpenseClaim", "expense")
            ),
            action="auto_approve",
            confidence=0.9,
            description="小额报销（≤1000）自动通过",
        ),
        BrainRule(
            id="expense.large_escalate",
            module="expense",
            condition=lambda p, c: (p.get("amount", 0) or 0) > 50000,
            action="escalate",
            confidence=0.92,
            description="报销金额>5万升级审批",
        ),
        BrainRule(
            id="procurement.large_escalate",
            module="procurement",
            condition=lambda p, c: (p.get("amount", 0) or 0) > 500000,
            action="escalate",
            confidence=0.95,
            description="采购金额>50万升级审批",
        ),
    ]


_initialized = False


def init_builtin_rules() -> int:
    """启动时调用一次，装载内置规则。返回装载数量。"""
    global _initialized
    if _initialized:
        return len(_RULES)
    _initialized = True
    count = 0
    for rule in _builtin_rules():
        if rule.id not in _RULES:
            register_rule(rule)
            count += 1
    logger.info("brain_rules_initialized: count=%d total=%d", count, len(_RULES))
    return count


def load_rules_from_dict(rules_data: List[Dict]) -> int:
    """从 DB/JSON 加载规则配置（供 API 使用）。返回加载数。"""
    count = 0
    for rd in rules_data:
        cond = rd.get("condition")
        if cond is None:
            continue
        if callable(cond):
            condition_fn: Callable = cond
        elif isinstance(cond, str):
            # 支持 JSON 表达式：{"amount": ">1000"} 或字符串表达式 "amount > 1000"
            condition_fn = _compile_condition_str(cond)
        else:
            continue
        rule = BrainRule(
            id=rd.get("id", f"custom.{len(_RULES)}"),
            module=rd.get("module", "custom"),
            condition=condition_fn,
            action=rd.get("action", "flag"),
            confidence=float(rd.get("confidence", 0.8)),
            description=rd.get("description", ""),
            enabled=rd.get("enabled", True),
        )
        register_rule(rule)
        count += 1
    return count


def _compile_condition_str(expr: str) -> Callable:
    """编译字符串条件表达式为可调用函数。

    支持两种格式：
    1. 简单比较：'amount > 1000'
    2. 逻辑组合：'amount > 1000 and department == "procurement"'

    安全性：仅允许访问 payload/context 中的字段，通过白名单 eval。
    """
    # 允许的运算符：==, !=, <, >, <=, >=, and, or, not, in
    # 白名单 AST 解析
    import ast

    def _safe_eval(node: ast.AST, payload: dict, ctx: dict) -> Any:
        if isinstance(node, ast.Expression):
            return _safe_eval(node.body, payload, ctx)
        if isinstance(node, ast.BoolOp):
            values = [_safe_eval(v, payload, ctx) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            return False
        if isinstance(node, ast.UnaryOp):
            operand = _safe_eval(node.operand, payload, ctx)
            if isinstance(node.op, ast.Not):
                return not operand
            return False
        if isinstance(node, ast.Compare):
            left = _safe_eval(node.left, payload, ctx)
            for op, comparator in zip(node.ops, node.comparators):
                right = _safe_eval(comparator, payload, ctx)
                if isinstance(op, ast.Eq) and left != right:
                    return False
                if isinstance(op, ast.NotEq) and left == right:
                    return False
                if isinstance(op, ast.Lt) and not (left < right):
                    return False
                if isinstance(op, ast.Gt) and not (left > right):
                    return False
                if isinstance(op, ast.LtE) and not (left <= right):
                    return False
                if isinstance(op, ast.GtE) and not (left >= right):
                    return False
                if isinstance(op, ast.In) and left not in right:
                    return False
                left = right
            return True
        if isinstance(node, ast.Name):
            data = payload or {}
            merged = {**ctx, **data}
            return merged.get(node.id)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.List):
            return [_safe_eval(e, payload, ctx) for e in node.elts]
        return None

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError(f"规则表达式语法错误: {expr}")

    def _wrapper(payload: dict, ctx: dict) -> bool:
        try:
            return bool(_safe_eval(tree, payload, ctx))
        except Exception:
            return False

    return _wrapper
