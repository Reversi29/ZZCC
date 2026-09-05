"""routers/brain.py — 类脑 AI 系统 API

端点：
- POST /brain/ask         主动咨询（同步推理，返回结果）
- POST /brain/observe     被动感知（异步处理，写信号队列）
- GET  /brain/status      系统状态（信号队列/推理统计/内存统计）
- GET  /brain/stats       推理统计（L1/L2/L3 调用次数、命中率）
- GET  /brain/decisions   决策日志（分页）
- GET  /brain/memory      查询长期记忆
- POST /brain/memory      写入/更新记忆
- DELETE /brain/memory    删除记忆
- POST /brain/learn       反馈学习（标记决策正确/错误）
- POST /brain/process-queue  处理信号队列（后台任务触发或手动）
- GET  /brain/core/status   常驻类脑中枢状态
- POST /brain/core/start    启动常驻 tick 循环
- POST /brain/core/stop     停止常驻 tick 循环
- POST /brain/core/tick     手动触发一次中枢 tick
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from models.brain import Action, CognitionResult, NeuralSignal
from routers.auth import get_current_user_dep
from services.brain import (
    action_executor as ae,
    brain_core,
    memory as mem,
    reasoning as rsn,
    rules as rls,
)

logger = logging.getLogger("brain.api")

router = APIRouter(prefix="/brain", tags=["Brain AI"])

R = Dict[str, Any]


# ═══════════════════════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════════════════════
class AskRequest(BaseModel):
    question: Optional[str] = Field(None, description="用户问题（可与 signal 二选一）")
    signal: Optional[Dict[str, Any]] = Field(
        None,
        description="感知信号（若无则从 question 自动推断）",
    )
    context: Dict[str, Any] = Field(default_factory=dict, description="附加上下文")
    session_id: Optional[str] = Field(None, description="会话 ID，用于工作记忆隔离")
    execute_actions: bool = Field(True, description="是否执行认知结果中的行动")


class ObserveRequest(BaseModel):
    signal: Dict[str, Any] = Field(..., description="感知信号")
    auto_process: bool = Field(True, description="是否立即处理（同步推理）")


class MemoryWriteRequest(BaseModel):
    type: str = Field(..., description="pattern/rule/feedback/lesson/preference")
    module: str = Field(..., description="模块名")
    key: str = Field(..., description="键名")
    value: Dict[str, Any] = Field(default_factory=dict, description="记忆内容")
    confidence: float = Field(0.5, ge=0.0, le=1.0)


class LearnRequest(BaseModel):
    signal_id: str
    correct: bool
    feedback: Optional[str] = None


class RuleCreateRequest(BaseModel):
    id: str
    module: str = "custom"
    condition: str = Field(..., description="规则表达式，如 'amount > 1000 and department == \"procurement\"'")
    action: str = "flag"
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    description: str = ""
    enabled: bool = True


# ═══════════════════════════════════════════════════════════
# 核心端点
# ═══════════════════════════════════════════════════════════

@router.post("/ask")
async def ask(
    request: AskRequest,
    user: dict = Depends(get_current_user_dep),
):
    """主动咨询：同步推理并返回结果。

    流程：
    1. 构造 NeuralSignal（从 request.signal 或 question 推断）
    2. 取工作记忆上下文
    3. 三层推理（L1→L2→L3）
    4. 写入决策日志
    5. 执行行动（可选）
    6. 返回结果
    """
    from services.db import managed_session

    # 1. 构造信号
    if request.signal:
        signal = NeuralSignal(
            type=request.signal.get("type", "user_request"),
            payload=request.signal.get("payload", {}),
            source="api_call",
            urgency=request.signal.get("urgency", 50),
            context=request.signal.get("context", {}),
        )
    elif request.question:
        # 从 question 推断（简单场景）
        signal = NeuralSignal(
            type="user_request",
            payload={"question": request.question, "text": request.question},
            source="api_call",
            urgency=50,
            context=request.context,
        )
    else:
        raise HTTPException(400, "必须提供 question 或 signal")

    # 2. 工作记忆 + 长期/情景/技能记忆检索
    session_id = request.session_id or f"ask_{user.get('id', 'anon')}_{signal.id}"
    working_memory = mem.working_memory.get_context(session_id)

    # 3. 推理
    memory_context: Dict[str, Any] = {}
    async with managed_session() as db:
        memory_context = await mem.retrieve_for_signal(db, signal.to_dict())
        cognition = await rsn.engine.reason(signal, working_memory, db)

        # 4. 写入决策日志
        log_payload = {
            "signal_id": cognition.signal_id,
            "signal_type": signal.type,
            "decision": cognition.decision,
            "confidence": cognition.confidence,
            "reasoning_level": cognition.reasoning_level,
            "reasoning": cognition.reasoning,
            "actions": [a.to_dict() for a in cognition.actions],
        }
        await mem.log_decision(db, log_payload)
        await db.commit()

        # 5. 执行行动
        action_results = []
        if request.execute_actions and cognition.actions:
            action_results = await ae.executor.execute_all(cognition, db)
            # 更新决策日志的 action_results
            await db.execute(
                text("UPDATE brain_decision_log SET action_results = :results "
                     "WHERE signal_id = :sid"),
                {"results": json.dumps(action_results, ensure_ascii=False), "sid": cognition.signal_id},
            )
            await db.commit()

        # 6. 更新工作记忆
        mem.working_memory.push(session_id, signal.to_dict(), cognition.to_dict())
        await mem.remember_signal_and_cognition(db, signal.to_dict(), cognition.to_dict(), action_results)
        await db.commit()

    return {
        "ok": True,
        "signal_id": signal.id,
        "cognition": cognition.to_dict(),
        "action_results": action_results,
        "session_id": session_id,
        "memory_context": memory_context,
    }


@router.post("/observe")
async def observe(
    request: ObserveRequest,
    user: dict = Depends(get_current_user_dep),
):
    """被动感知：接收信号。auto_process=True 时同步推理，否则写队列。"""
    from services.db import managed_session

    signal_data = request.signal
    if "type" not in signal_data:
        raise HTTPException(400, "signal 必须包含 type 字段")

    signal = NeuralSignal(
        type=signal_data["type"],
        payload=signal_data.get("payload", {}),
        source=signal_data.get("source", "webhook"),
        urgency=signal_data.get("urgency", 50),
        context=signal_data.get("context", {}),
    )

    async with managed_session() as db:
        await mem.enqueue_signal(db, signal.to_dict())
        await db.commit()

    if not request.auto_process:
        return {"ok": True, "signal_id": signal.id, "queued": True}

    # 同步处理
    return await ask(AskRequest(
        signal=signal.to_dict(),
        context=signal.context,
        execute_actions=True,
    ), user=user)


@router.post("/process-queue")
async def process_queue(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user_dep),
):
    """处理信号队列。手动触发或后台 cron。"""
    from services.db import managed_session

    processed = []
    async with managed_session() as db:
        signals = await mem.dequeue_pending(db, limit=limit)
        for s in signals:
            # PG JSONB 列返回 dict；兼容字符串情况
            raw_payload = s.get("payload", {})
            if isinstance(raw_payload, str):
                raw_payload = json.loads(raw_payload) if raw_payload else {}
            raw_context = s.get("context", {})
            if isinstance(raw_context, str):
                raw_context = json.loads(raw_context) if raw_context else {}
            signal = NeuralSignal(
                id=s["id"],
                type=s["type"],
                payload=raw_payload,
                source=s.get("source", "queue"),
                urgency=s.get("urgency", 50),
                context=raw_context,
            )
            working_memory = mem.working_memory.get_context(f"queue_{s['id']}")
            cognition = await rsn.engine.reason(signal, working_memory, db)
            log_payload = {
                "signal_id": cognition.signal_id,
                "signal_type": signal.type,
                "decision": cognition.decision,
                "confidence": cognition.confidence,
                "reasoning_level": cognition.reasoning_level,
                "reasoning": cognition.reasoning,
                "actions": [a.to_dict() for a in cognition.actions],
            }
            await mem.log_decision(db, log_payload)
            await mem.mark_processed(db, signal.id)
            processed.append({"signal_id": signal.id, "decision": cognition.decision, "confidence": cognition.confidence})
        await db.commit()

    return {"ok": True, "processed": len(processed), "results": processed}


@router.get("/status")
async def status(
    user: dict = Depends(get_current_user_dep),
):
    """系统状态。"""
    from services.db import managed_session

    async with managed_session() as db:
        pending_count = await db.execute(
            text("SELECT COUNT(*) FROM brain_signal WHERE processed = false")
        )
        pending_count = pending_count.fetchone()[0]
        processed_count = await db.execute(
            text("SELECT COUNT(*) FROM brain_signal WHERE processed = true")
        )
        processed_count = processed_count.fetchone()[0]
        memory_count = (await db.execute(text("SELECT COUNT(*) FROM brain_memory"))).fetchone()[0]
        decisions_count = (await db.execute(text("SELECT COUNT(*) FROM brain_decision_log"))).fetchone()[0]

    return {
        "ok": True,
        "signal_queue": {"pending": pending_count, "processed": processed_count},
        "memory_entries": memory_count,
        "decisions_logged": decisions_count,
        "reasoning_stats": rsn.engine.stats(),
        "rules_loaded": len(rls.list_rules()),
        "action_executors": ae.list_executors(),
    }


@router.get("/stats")
async def stats(
    user: dict = Depends(get_current_user_dep),
):
    """推理统计。"""
    return {"ok": True, "stats": rsn.engine.stats()}


@router.get("/decisions")
async def decisions(
    limit: int = Query(50, ge=1, le=500),
    signal_type: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    user: dict = Depends(get_current_user_dep),
):
    """决策日志。"""
    from services.db import managed_session

    async with managed_session() as db:
        rows = await mem.get_decisions(db, limit=limit, signal_type=signal_type, decision=decision)
    return {"ok": True, "decisions": rows, "count": len(rows)}


@router.get("/memory")
async def get_memory(
    type: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    user: dict = Depends(get_current_user_dep),
):
    """查询长期记忆。"""
    from services.db import managed_session

    async with managed_session() as db:
        rows = await mem.memory_list(db, type_=type, module=module, limit=limit)
    return {"ok": True, "memory": rows, "count": len(rows)}


@router.post("/memory")
async def write_memory(
    request: MemoryWriteRequest,
    user: dict = Depends(get_current_user_dep),
):
    """写入/更新长期记忆。"""
    from services.db import managed_session

    async with managed_session() as db:
        await mem.memory_set(db, {
            "type": request.type,
            "module": request.module,
            "key": request.key,
            "value": request.value,
            "confidence": request.confidence,
        })
        await db.commit()
    return {"ok": True, "type": request.type, "module": request.module, "key": request.key}


@router.delete("/memory")
async def delete_memory(
    type: str = Query(...),
    module: str = Query(...),
    key: str = Query(...),
    user: dict = Depends(get_current_user_dep),
):
    """删除记忆条目。"""
    from services.db import managed_session

    async with managed_session() as db:
        deleted = await mem.memory_delete(db, type, module, key)
        await db.commit()
    return {"ok": True, "deleted": deleted}


@router.post("/learn")
async def learn(
    request: LearnRequest,
    user: dict = Depends(get_current_user_dep),
):
    """反馈学习：标记决策正确/错误。"""
    from services.db import managed_session

    async with managed_session() as db:
        updated = await mem.record_outcome(db, request.signal_id, request.correct, request.feedback)
        await db.commit()
    return {"ok": True, "updated": updated}


@router.get("/core/status")
async def brain_core_status(
    user: dict = Depends(get_current_user_dep),
):
    """常驻类脑内核状态。"""
    return brain_core.status()


@router.post("/core/start")
async def brain_core_start(
    user: dict = Depends(get_current_user_dep),
):
    """启动常驻 tick 循环。"""
    return await brain_core.start()


@router.post("/core/stop")
async def brain_core_stop(
    user: dict = Depends(get_current_user_dep),
):
    """停止常驻 tick 循环。"""
    return await brain_core.stop()


@router.post("/core/tick")
async def brain_core_tick(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user_dep),
):
    """手动触发一次常驻内核处理。"""
    brain_core.batch_limit = limit
    return await brain_core.tick()


# ═══════════════════════════════════════════════════════════
# 规则管理
# ═══════════════════════════════════════════════════════════

@router.get("/rules")
async def list_rules(
    module: Optional[str] = Query(None),
    user: dict = Depends(get_current_user_dep),
):
    """列出所有规则。"""
    rules = rls.list_rules(module=module)
    return {
        "ok": True,
        "rules": [
            {
                "id": r.id,
                "module": r.module,
                "action": r.action,
                "confidence": r.confidence,
                "description": r.description,
                "enabled": r.enabled,
            }
            for r in rules
        ],
        "count": len(rules),
    }


@router.post("/rules")
async def create_rule(
    request: RuleCreateRequest,
    user: dict = Depends(get_current_user_dep),
):
    """创建规则（条件表达式字符串形式）。"""
    from models.brain import BrainRule

    try:
        condition_fn = rls._compile_condition_str(request.condition)
    except Exception as e:
        raise HTTPException(400, f"规则表达式编译失败: {e}")

    rule = BrainRule(
        id=request.id,
        module=request.module,
        condition=condition_fn,
        action=request.action,
        confidence=request.confidence,
        description=request.description,
        enabled=request.enabled,
    )
    rls.register_rule(rule)
    return {"ok": True, "rule": {
        "id": rule.id, "module": rule.module, "action": rule.action,
        "confidence": rule.confidence, "description": rule.description,
    }}


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    enabled: bool = Query(...),
    user: dict = Depends(get_current_user_dep),
):
    """启用/禁用规则。"""
    ok = rls.set_enabled(rule_id, enabled)
    if not ok:
        raise HTTPException(404, "规则不存在")
    return {"ok": True, "rule_id": rule_id, "enabled": enabled}
