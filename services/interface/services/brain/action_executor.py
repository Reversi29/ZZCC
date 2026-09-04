"""services/brain/action_executor.py — 统一行动执行器

- 所有 AI 决策通过此层执行，可审计
- 支持自定义 action 类型（插件可通过 sdk.brain_action 扩展）
- 内置执行器：flag / need_info / no_action / send_notification / trigger_flow
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from models.brain import Action, CognitionResult

logger = logging.getLogger("brain.action")


# 执行器注册表：action_type -> async callable(action, cognition, db) -> dict
_EXECUTORS: Dict[str, Callable[..., Awaitable[dict]]] = {}


def register_executor(action_type: str, fn: Callable[..., Awaitable[dict]]) -> None:
    _EXECUTORS[action_type] = fn
    logger.info("action_executor_registered: %s", action_type)


def list_executors() -> List[str]:
    return list(_EXECUTORS.keys())


# ═══════════════════════════════════════════════════════════
# 内置执行器
# ═══════════════════════════════════════════════════════════

def _executed_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


async def _exec_flag(action: Action, cognition: CognitionResult, db) -> dict:
    """标记信号为风险。仅记录，不修改业务数据。"""
    return {
        "ok": True,
        "action": "flag",
        "flagged": True,
        "reason": action.reason,
        "params": action.params,
        "executed_at": _executed_at(),
    }


async def _exec_need_info(action: Action, cognition: CognitionResult, db) -> dict:
    return {
        "ok": True,
        "action": "need_info",
        "missing_info": action.params.get("missing_fields", []),
        "message": action.reason or "需要补充信息",
    }


async def _exec_no_action(action: Action, cognition: CognitionResult, db) -> dict:
    return {
        "ok": True,
        "action": "no_action",
        "reason": action.reason,
    }


async def _exec_approve(action: Action, cognition: CognitionResult, db) -> dict:
    """批准/自动通过。仅记录决策，实际业务变更需外部集成。"""
    return {
        "ok": True,
        "action": "approve",
        "approved": True,
        "reason": action.reason,
        "params": action.params,
        "signal_id": cognition.signal_id,
        "executed_at": _executed_at(),
    }


async def _exec_reject(action: Action, cognition: CognitionResult, db) -> dict:
    """拒绝/驳回。"""
    return {
        "ok": True,
        "action": "reject",
        "rejected": True,
        "reason": action.reason,
        "params": action.params,
        "signal_id": cognition.signal_id,
        "executed_at": _executed_at(),
    }


async def _exec_escalate(action: Action, cognition: CognitionResult, db) -> dict:
    """升级审批。记录决策 + 尝试写通知。"""
    result = {
        "ok": True,
        "action": "escalate",
        "escalated": True,
        "reason": action.reason,
        "params": action.params,
        "signal_id": cognition.signal_id,
        "executed_at": _executed_at(),
    }
    # 尝试发通知（best-effort）
    try:
        await _exec_send_notification(
            Action(type="send_notification", params={
                "title": f"AI 系统升级审批: {cognition.decision}",
                "message": f"信号 {cognition.signal_id[:12]} 需升级处理。{action.reason}",
                "level": "warning",
            }, reason=action.reason),
            cognition, db
        )
        result["notified"] = True
    except Exception as e:
        result["notified"] = False
        result["notify_error"] = str(e)
    return result


async def _exec_send_notification(action: Action, cognition: CognitionResult, db) -> dict:
    """发送通知（发布到事件总线）。"""
    import json
    from sqlalchemy import text

    payload = {
        "title": action.params.get("title", "AI 系统通知"),
        "message": action.params.get("message", action.reason or ""),
        "level": action.params.get("level", "info"),
        "signal_id": cognition.signal_id,
        "decision": cognition.decision,
    }

    # 用独立 DB session 写通知，避免污染外层事务
    from services.db import managed_session

    try:
        async with managed_session() as notify_db:
            await notify_db.execute(
                text("""
                    INSERT INTO notifications (title, message, level, created_at)
                    VALUES (:title, :message, :level, NOW())
                """),
                {"title": payload["title"], "message": payload["message"], "level": payload["level"]},
            )
            await notify_db.commit()
        return {"ok": True, "action": "send_notification", "notified": True, "payload": payload}
    except Exception as e:
        logger.warning("notification_write_failed: %s", str(e))
        return {
            "ok": True,
            "action": "send_notification",
            "notified": False,
            "warning": f"notifications table missing or write failed: {e}",
            "payload": payload,
        }


async def _exec_trigger_flow(action: Action, cognition: CognitionResult, db) -> dict:
    """触发流程编排（依赖 flow.py 未来实现）。占位实现。"""
    return {
        "ok": True,
        "action": "trigger_flow",
        "flow_id": action.params.get("flow_id"),
        "warning": "flow_engine not implemented yet",
        "params": action.params,
    }


# 注册内置执行器
register_executor("flag", _exec_flag)
register_executor("need_info", _exec_need_info)
register_executor("no_action", _exec_no_action)
register_executor("approve", _exec_approve)
register_executor("auto_approve", _exec_approve)
register_executor("reject", _exec_reject)
register_executor("escalate", _exec_escalate)
register_executor("send_notification", _exec_send_notification)
register_executor("trigger_flow", _exec_trigger_flow)


# ═══════════════════════════════════════════════════════════
# ActionExecutor
# ═══════════════════════════════════════════════════════════
class ActionExecutor:
    """统一行动执行器。"""

    async def execute(
        self,
        action: Action,
        cognition: CognitionResult,
        db,
    ) -> dict:
        """执行单个行动。"""
        executor = _EXECUTORS.get(action.type)
        # 未注册的 action 类型走默认记录器：确保决策有 action_results 落库
        if executor is None:
            return {
                "ok": True,
                "action_type": action.type,
                "action": action.type,
                "recorded": True,
                "default_handler": True,
                "reason": action.reason,
                "params": action.params,
                "signal_id": cognition.signal_id,
                "executed_at": _executed_at(),
            }
        try:
            result = await executor(action, cognition, db)
            result["action_type"] = action.type
            result["action_reason"] = action.reason
            return result
        except Exception as e:
            logger.error("action_execute_failed: action=%s error=%s", action.type, str(e))
            return {
                "ok": False,
                "error": str(e),
                "action": action.to_dict(),
            }

    async def execute_all(
        self,
        cognition: CognitionResult,
        db,
    ) -> List[dict]:
        """执行认知结果中的所有行动。"""
        results = []
        for action in cognition.actions:
            result = await self.execute(action, cognition, db)
            results.append(result)
        return results


executor = ActionExecutor()
