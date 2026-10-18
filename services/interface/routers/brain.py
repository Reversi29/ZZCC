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
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from models.brain import Action, CognitionResult, NeuralSignal
# (Brain AI 端点不需要用户鉴权，是全局系统服务)
from services.brain import (
    action_executor as ae,
    brain_core,
    memory as mem,
    reasoning as rsn,
    rules as rls,
    semantic as sem,
    snn_region as snn_mod,
)
from services.brain.broker import broker

logger = logging.getLogger("brain.api")

router = APIRouter(prefix="/brain", tags=["Brain AI"])

_CONFIG_FILE = os.environ.get(
    "BRAIN_CONFIG_FILE",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "brain_config.json"),
)


def _load_brain_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "provider": "openai-compatible",
        "protocol": os.environ.get("QCLAW_LLM_PROTOCOL")
        or os.environ.get("OPENAI_PROTOCOL")
        or "openai",
        "api_base": os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("QCLAW_LLM_BASE_URL")
        or "https://api.openai.com/v1",
        "api_key": os.environ.get("OPENAI_API_KEY")
        or os.environ.get("QCLAW_LLM_API_KEY", ""),
        "model": os.environ.get("OPENAI_MODEL")
        or os.environ.get("QCLAW_LLM_MODEL")
        or "qwen/qwen3.8-flash",
        "temperature": float(
            os.environ.get("OPENAI_TEMPERATURE")
            or os.environ.get("QCLAW_LLM_TEMPERATURE")
            or 0.3,
        ),
    }
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in cfg and v is not None:
                        cfg[k] = v
    except Exception:
        pass
    # 兼容旧字段：若 protocol 未设但有 provider，用 provider 推断
    if not cfg.get("protocol") and cfg.get("provider"):
        p = str(cfg["provider"]).lower()
        if "anthropic" in p or "claude" in p:
            cfg["protocol"] = "anthropic"
        elif "gemini" in p or "google" in p:
            cfg["protocol"] = "gemini"
        else:
            cfg["protocol"] = "openai"
    return cfg


def _save_brain_config(cfg: Dict[str, Any]) -> None:
    try:
        tmp = _CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _CONFIG_FILE)
    except Exception:
        pass



brain_config: Dict[str, Any] = _load_brain_config()

# 启动时将持久化配置同步到推理引擎实例
rsn.engine.update_llm_config(
    api_key=brain_config.get("api_key") or None,
    model=brain_config.get("model") or "qwen/qwen3.8-flash",
    api_base=brain_config.get("api_base") or None,
    temperature=brain_config.get("temperature"),
    protocol=brain_config.get("protocol"),
)

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
    payload: Optional[dict] = None  # 客户端可传入原始信号 payload，供 SNN 反馈学习使用
    correct_decision: Optional[str] = None  # correct=false 时，客户端指定正确的决策类型（如 auto_approve/reject/escalate/flag）


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

class BrainConfigUpdate(BaseModel):
    provider: Optional[str] = Field(None, description="云端模型提供商（兼容旧字段）")
    protocol: Optional[str] = Field(
        None, description="API 协议类型：openai | anthropic | gemini"
    )
    api_base: Optional[str] = Field(None, description="API Base URL")
    api_key: Optional[str] = Field(None, description="API Key")
    model: Optional[str] = Field(None, description="模型名")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)


@router.get("/config")
async def get_brain_config():
    cfg = dict(brain_config)
    key = cfg.pop("api_key", "")
    return {
        "ok": True,
        "config": cfg,
        "has_api_key": bool(key),
    }


@router.post("/config")
async def update_brain_config(
    request: BrainConfigUpdate,
):
    updates = request.model_dump(exclude_none=True)
    brain_config.update(updates)
    _save_brain_config(brain_config)
    rsn.engine.update_llm_config(
        api_key=brain_config.get("api_key") or None,
        model=brain_config.get("model") or "qwen/qwen3.8-flash",
        api_base=brain_config.get("api_base") or None,
        temperature=brain_config.get("temperature"),
        protocol=brain_config.get("protocol"),
    )
    # 不回显 api_key 明文，仅告知是否已配置
    masked = {k: v for k, v in brain_config.items() if k != "api_key"}
    masked["has_api_key"] = bool(brain_config.get("api_key"))
    return {"ok": True, "config": masked, "stats": rsn.engine.stats()}


@router.post("/config/test")
async def test_brain_config():
    result = await rsn.engine.test_llm_connection()
    return {"ok": bool(result.get("ok")), **result}


@router.post("/ask")
async def ask(
    request: AskRequest,
):
    """主动咨询：同步推理并返回结果。

    Brain AI 是全局系统服务，不需要用户登录即可使用。

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
    session_id = request.session_id or f"ask_anon_{signal.id}"
    working_memory = mem.working_memory.get_context(session_id)

    # 3. 推理
    memory_context: Dict[str, Any] = {}
    async with managed_session() as db:
        memory_context = await broker.retrieve_for_signal(db, signal.to_dict())
        cognition = await rsn.engine.reason(signal, working_memory, db, memory_context=memory_context)

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
        await broker.remember_signal_and_cognition(db, signal.to_dict(), cognition.to_dict(), action_results)
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
):
    """推理统计。"""
    return {"ok": True, "stats": rsn.engine.stats()}


@router.get("/decisions")
async def decisions(
    limit: int = Query(50, ge=1, le=500),
    signal_type: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
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
):
    """查询长期记忆。"""
    from services.db import managed_session

    async with managed_session() as db:
        rows = await mem.memory_list(db, type_=type, module=module, limit=limit)
    return {"ok": True, "memory": rows, "count": len(rows)}


@router.post("/memory")
async def write_memory(
    request: MemoryWriteRequest,
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
):
    """反馈学习：标记决策正确/错误。"""
    from services.db import managed_session

    async with managed_session() as db:
        updated = await mem.record_outcome(db, request.signal_id, request.correct, request.feedback)
        skill = await mem.summarize_skill_from_feedback(
            db,
            request.signal_id,
            request.correct,
            request.feedback,
        )
        await db.commit()
        semantic_result = {"ok": True, "skipped": True, "reason": "no decision log row"}
        if skill.get("ok") and broker.semantic is not None:
            try:
                decisions = await mem.get_decisions(db, limit=1, signal_type=skill.get("signal_type"), decision=skill.get("decision"))
                decision_row = decisions[0] if decisions else None
                if decision_row:
                    signal_for_semantic = {
                        "id": decision_row.get("signal_id"),
                        "type": decision_row.get("signal_type"),
                        "module": skill.get("module"),
                        "payload": {"decision": skill.get("decision"), "feedback": request.feedback or ""},
                        "source": "learn_feedback",
                        "urgency": 50,
                        "created_at": decision_row.get("created_at"),
                    }
                    cognition_for_semantic = {
                        "decision": skill.get("decision"),
                        "reasoning_level": skill.get("reasoning_level"),
                        "confidence": skill.get("success_rate", 0.5),
                        "reasoning": skill.get("summary", ""),
                    }
                    semantic_result = await broker.semantic.remember(
                        signal_for_semantic,
                        cognition_for_semantic,
                        action_results=[{"ok": request.correct, "action": "learn_feedback"}],
                    )
            except Exception as exc:
                semantic_result = {"ok": False, "error": str(exc)}
        # SNN 反馈学习：将决策标注传递给脉冲神经网络
        snn_result = {"ok": True, "skipped": True}
        try:
            if skill.get("ok"):
                decisions_all = await mem.get_decisions(db, limit=1, signal_type=skill.get("signal_type"), decision=skill.get("decision"))
                decision_row = decisions_all[0] if decisions_all else None
                if decision_row:
                    sig_id = decision_row.get("signal_id", "")
                    # payload 优先级：request.payload > brain_signal 表 > 从 action_results 提取
                    sig_payload = request.payload if request.payload else {}
                    if not sig_payload and sig_id:
                        from sqlalchemy import text as sa_text
                        sig_rows = (await db.execute(
                            sa_text("SELECT payload FROM brain_signal WHERE id = :sid"),
                            {"sid": sig_id},
                        )).fetchall()
                        if sig_rows and sig_rows[0][0]:
                            import json as _json
                            try:
                                sig_payload = _json.loads(sig_rows[0][0]) if isinstance(sig_rows[0][0], str) else sig_rows[0][0]
                            except (ValueError, TypeError):
                                sig_payload = {}
                    if not sig_payload:
                        # 从 action_results JSON 中尝试提取 amount 等信息
                        import json as _json
                        ar = decision_row.get("action_results", "[]")
                        if isinstance(ar, str):
                            try:
                                ar = _json.loads(ar)
                            except (ValueError, TypeError):
                                ar = []
                        if isinstance(ar, list):
                            for a in ar:
                                if isinstance(a, dict) and a.get("params"):
                                    params = a["params"]
                                    if "amount" in params or "category" in params:
                                        sig_payload = params
                                        break
                    signal_obj = NeuralSignal(
                        id=sig_id,
                        type=decision_row.get("signal_type", ""),
                        payload=sig_payload,
                        source=decision_row.get("source", "learn_feedback"),
                        urgency=decision_row.get("urgency", 50),
                    )
                    # correct=false 时优先用客户端指定的 correct_decision；否则回退到原始决策
                    effective_decision = request.correct_decision or skill.get("decision", "")
                    snn_result = snn_mod.snn_region.train_from_feedback(
                        signal=signal_obj,
                        correct_decision=effective_decision,
                        was_correct=request.correct,
                    )
        except Exception as exc:
            snn_result = {"ok": False, "error": str(exc)}
    return {"ok": True, "updated": updated, "skill": skill, "semantic": semantic_result, "snn": snn_result}


@router.get("/semantic/status")
async def semantic_status(
):
    """语义记忆（NebulaGraph）状态。"""
    return {"ok": True, **sem.semantic_memory.status()}


@router.post("/semantic/ensure-schema")
async def semantic_ensure_schema(
):
    """创建/校验语义记忆 space、tag、edge。"""
    return await sem.semantic_memory.ensure_schema()


@router.get("/core/status")
async def brain_core_status(
):
    """常驻类脑内核状态。"""
    return brain_core.status()


@router.post("/core/start")
async def brain_core_start(
):
    """启动常驻 tick 循环。"""
    return await brain_core.start()


@router.post("/core/stop")
async def brain_core_stop(
):
    """停止常驻 tick 循环。"""
    return await brain_core.stop()


@router.post("/core/tick")
async def brain_core_tick(
    limit: int = Query(20, ge=1, le=100),
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
):
    """启用/禁用规则。"""
    ok = rls.set_enabled(rule_id, enabled)
    if not ok:
        raise HTTPException(404, "规则不存在")
    return {"ok": True, "rule_id": rule_id, "enabled": enabled}


# ═══════════════════════════════════════════════════════════
# SNN 脉冲神经网络管理
# ═══════════════════════════════════════════════════════════

@router.get("/snn/status")
async def snn_status():
    """SNN 网络状态。"""
    return snn_mod.snn_region.status()


@router.post("/snn/reset")
async def snn_reset():
    """重置推理状态（不清除学习权重）。"""
    snn_mod.snn_region.reset()
    return {"ok": True, "message": "推理状态已重置"}


@router.post("/snn/reset-network")
async def snn_reset_network():
    """重置网络（清除所有学习，恢复默认拓扑）。"""
    snn_mod.snn_region.reset_network()
    return {"ok": True, "message": "网络已重置为默认拓扑"}


@router.post("/snn/save")
async def snn_save():
    """手动保存网络到磁盘。"""
    ok = snn_mod.snn_region.save()
    return {"ok": ok}


@router.get("/snn/graph")
async def snn_graph():
    """SNN 连接图（节点+边，供前端可视化）。"""
    return {"ok": True, **snn_mod.snn_region.connection_graph()}


@router.post("/snn/train")
async def snn_train(request: dict):
    """手动训练 SNN（注入信号模式并学习）。

    支持传 payload 以训练金额/详情条件化决策：
        {"signal_type":"approval_pending","decision":"escalate","payload":{"amount":600000},"steps":50}
    """
    signal_type = request.get("signal_type", "user_request")
    decision = request.get("decision", "auto_approve")
    steps = int(request.get("steps", 10))
    urgency = int(request.get("urgency", 50))
    payload = request.get("payload", {})
    signal = NeuralSignal(type=signal_type, payload=payload, urgency=urgency)
    for _ in range(steps):
        snn_mod.snn_region.train_from_feedback(
            signal=signal, correct_decision=decision, was_correct=True,
        )
    return {"ok": True, "steps": steps, "stats": snn_mod.snn_region.status()}


@router.get("/snn/connections")
async def snn_connections():
    """列出所有连接（含权重和延迟）。"""
    net = snn_mod.snn_region.snn
    connections = []
    for src in net.out_edges:
        for tgt, conn in net.out_edges[src].items():
            connections.append({
                "source": src, "target": tgt,
                "weight": round(conn.weight, 4),
                "delay": conn.delay,
            })
    connections.sort(key=lambda e: (-e["weight"], e["source"], e["target"]))
    return {"ok": True, "count": len(connections), "connections": connections}


# ─────────────────────────────────────────────────────────────
# 图谱布局 API — 供前端调用，返回 world 坐标
# 传入 nodes/links，服务端用 networkx 计算布局，返回 {id:[x,y]}
# 支持 spring（力导）/ circular / category 三种算法
# ─────────────────────────────────────────────────────────────

import math as _math

@router.post("/graph/layout")
async def graph_layout(request: dict):
    """计算图谱布局坐标。

    请求体:
        {
            "nodes": [{"id":"a"}, {"id":"b"}, ...],
            "links": [{"source":"a","target":"b"}, ...],
            "algorithm": "spring" | "circular" | "category",
            "categories": [{"id":"a","category":0}, ...],
            "seed": 42,
            "worldRadius": 800
        }
    返回:
        {"ok": true, "algorithm": "spring", "positions": {"a":[x,y], ...}}
    """
    try:
        nodes = request.get("nodes") or []
        links = request.get("links") or []
        algorithm = (request.get("algorithm") or "spring").lower()
        seed = int(request.get("seed", 42))
        world_radius = float(request.get("worldRadius", 800))
        categories = request.get("categories") or []

        node_ids = [n.get("id") for n in nodes if n.get("id")]
        seen = set()
        uniq_ids = []
        for nid in node_ids:
            if nid not in seen:
                seen.add(nid)
                uniq_ids.append(nid)

        if not uniq_ids:
            return {"ok": True, "algorithm": algorithm, "positions": {}}

        if algorithm == "category":
            positions = _layout_category(uniq_ids, categories, world_radius)
        elif algorithm == "circular":
            positions = _layout_circular(uniq_ids, world_radius)
        else:
            positions = _layout_spring(uniq_ids, links, seed, world_radius)

        return {"ok": True, "algorithm": algorithm, "positions": positions}
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph_layout failed: %s", exc)
        return {"ok": False, "error": str(exc), "positions": {}}


def _layout_spring(node_ids: list, links: list, seed: int, world_radius: float) -> dict:
    """力导布局（Fruchterman-Reingold 变体）。"""
    import networkx as nx

    G = nx.Graph()
    G.add_nodes_from(node_ids)
    node_set = set(node_ids)
    for e in links:
        src = e.get("source")
        dst = e.get("target")
        if src and dst and src in node_set and dst in node_set and src != dst:
            if not G.has_edge(src, dst):
                G.add_edge(src, dst)

    pos = nx.spring_layout(G, k=2.0, iterations=80, seed=seed)

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    if not xs:
        return {}
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xr = (xmax - xmin) or 1.0
    yr = (ymax - ymin) or 1.0
    scale = world_radius * 2.0 / max(xr, yr)
    cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0

    out = {}
    for nid, (x, y) in pos.items():
        out[nid] = [round((x - cx) * scale, 2), round((y - cy) * scale, 2)]
    return out


def _layout_circular(node_ids: list, world_radius: float) -> dict:
    """环形布局，均匀分布在圆周上。"""
    n = len(node_ids)
    if n == 0:
        return {}
    out = {}
    for i, nid in enumerate(node_ids):
        angle = (i / n) * 2 * _math.pi - _math.pi / 2
        out[nid] = [
            round(_math.cos(angle) * world_radius * 0.85, 2),
            round(_math.sin(angle) * world_radius * 0.85, 2),
        ]
    return out


def _layout_category(node_ids: list, categories: list, world_radius: float) -> dict:
    """按 category 分组，组中心绕大圆分布，组内 golden-angle 螺旋。"""
    golden_angle = 2.399963229728653
    cat_of: dict = {c.get("id"): int(c.get("category", 0)) for c in categories if c.get("id")}

    groups: dict = {}
    for nid in node_ids:
        cat = cat_of.get(nid, 0)
        groups.setdefault(cat, []).append(nid)

    group_keys = sorted(groups.keys())
    gcount = len(group_keys)
    out = {}

    if gcount == 1:
        _fill_spiral(list(groups.values())[0], 0.0, 0.0, world_radius * 0.7, golden_angle, out)
        return out

    for gi, cat in enumerate(group_keys):
        angle = (gi / gcount) * 2 * _math.pi - _math.pi / 2
        gx = _math.cos(angle) * world_radius * 0.6
        gy = _math.sin(angle) * world_radius * 0.6
        _fill_spiral(groups[cat], gx, gy, world_radius * 0.35, golden_angle, out)

    return out


def _fill_spiral(nodes: list, cx: float, cy: float, radius: float,
                 golden_angle: float, out: dict) -> None:
    """黄金角螺旋排布（确定性，无随机）。"""
    n = len(nodes)
    if n == 0:
        return
    local_r = radius / (n ** 0.5)
    for i, nid in enumerate(nodes):
        a = i * golden_angle
        r = local_r * (i + 1) ** 0.5
        out[nid] = [round(cx + _math.cos(a) * r, 2), round(cy + _math.sin(a) * r, 2)]
