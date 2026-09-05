"""services/brain/core.py — 类脑常驻内核（Phase A）

目标：把 request-trigger 推理升级为可常驻运行的中枢闭环：

    感知信号 → 丘脑门控 → 记忆检索 → 皮层推理 → 行动执行 → 记忆写回 → 统计广播

当前版本保持轻量、可插拔：
- BrainCore 负责后台 tick 与队列消费
- Thalamus 负责优先级/去重/噪声过滤
- MemoryBroker 只做薄封装，后续可替换为 embedding / NebulaGraph / 多记忆类型
- 行动执行和推理仍复用现有 ReasoningEngine / ActionExecutor
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from models.brain import CognitionResult, NeuralSignal
from sqlalchemy import text

from services.brain import action_executor as ae
from services.brain import memory as mem
from services.brain import reasoning as rsn
from services.brain import rules as rls
from services.brain.broker import MemoryBroker

logger = logging.getLogger("brain.core")


class Thalamus:
    """丘脑：输入门控、去重、优先级调整。"""

    def __init__(self, min_urgency: int = 0, dedupe_ttl: int = 900):
        self.min_urgency = min_urgency
        self.dedupe_ttl = dedupe_ttl
        self._seen: Dict[str, float] = {}

    def gate(self, signal: NeuralSignal, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        key = self._key(signal)
        last = self._seen.get(key)
        if last and now - last < self.dedupe_ttl and not force:
            return {"pass": False, "reason": "duplicate_recent", "key": key}
        if signal.urgency < self.min_urgency and not force:
            return {"pass": False, "reason": "below_min_urgency", "key": key}

        # 简单内稳态/注意力调整：非常紧急信号提高优先级；噪声信号降低。
        adjusted = signal.urgency
        payload = signal.payload or {}
        if payload.get("error") or payload.get("failed"):
            adjusted = min(100, adjusted + 10)
        if signal.type == "noise" or payload.get("ignored"):
            adjusted = max(0, adjusted - 30)
        signal.urgency = adjusted

        self._seen[key] = now
        self._prune()
        return {"pass": True, "reason": "accepted", "key": key}

    def _key(self, signal: NeuralSignal) -> str:
        raw = json.dumps({
            "type": signal.type,
            "source": signal.source,
            "payload": signal.payload,
        }, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _prune(self) -> None:
        cutoff = time.time() - self.dedupe_ttl
        for k, ts in list(self._seen.items()):
            if ts < cutoff:
                self._seen.pop(k, None)

    def stats(self) -> dict:
        return {"seen": len(self._seen), "min_urgency": self.min_urgency, "dedupe_ttl": self.dedupe_ttl}


class BrainCore:
    """常驻类脑内核。"""

    def __init__(self, interval_seconds: int = 15, batch_limit: int = 20, execute_actions: bool = True):
        self.interval_seconds = max(1, interval_seconds)
        self.batch_limit = max(1, batch_limit)
        self.execute_actions = execute_actions
        self.thalamus = Thalamus()
        self.broker = MemoryBroker()
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._stats = {
            "started_at": None,
            "stopped_at": None,
            "ticks": 0,
            "signals_seen": 0,
            "signals_gated_out": 0,
            "signals_processed": 0,
            "actions_executed": 0,
            "last_tick_at": None,
            "last_processed_at": None,
            "last_error": "",
        }

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def config(self) -> dict:
        return {
            "interval_seconds": self.interval_seconds,
            "batch_limit": self.batch_limit,
            "execute_actions": self.execute_actions,
            "thalamus": self.thalamus.stats(),
        }

    def stats(self) -> dict:
        return dict(self._stats)

    def status(self) -> dict:
        return {
            "ok": True,
            "running": self.running,
            "config": self.config(),
            "stats": self.stats(),
            "working_memory": self.broker.stats()["working_memory"],
            "memory": self.broker.stats(),
            "semantic": self.broker.semantic.status() if self.broker.semantic else {"enabled": False},
            "reasoning": rsn.engine.stats(),
            "rules_loaded": len(rls.list_rules()),
            "actions": ae.list_executors(),
        }

    async def start(self) -> dict:
        if self.running:
            return self.status()
        self._stop.clear()
        self._stats["started_at"] = _iso()
        self._stats["stopped_at"] = None
        self._task = asyncio.create_task(self._run(), name="brain-core")
        logger.info("brain_core_started", interval=self.interval_seconds, batch=self.batch_limit)
        return self.status()

    async def stop(self) -> dict:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
            except Exception as exc:
                self._stats["last_error"] = str(exc)
        self._stats["stopped_at"] = _iso()
        self._task = None
        logger.info("brain_core_stopped")
        return self.status()

    async def _run(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            try:
                result = await self.tick()
                self._stats["last_processed_at"] = _iso()
                if result.get("processed", 0):
                    self._stats["signals_processed"] += int(result.get("processed", 0))
                    self._stats["actions_executed"] += int(result.get("actions", 0))
            except Exception as exc:
                self._stats["last_error"] = str(exc)
                logger.exception("brain_core_tick_failed")
            elapsed = time.time() - started
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(0.1, self.interval_seconds - elapsed))
            except asyncio.TimeoutError:
                continue

    async def tick(self) -> Dict[str, Any]:
        """手动/自动 tick：处理一批待办信号。"""
        async with self._lock:
            self._stats["ticks"] += 1
            self._stats["last_tick_at"] = _iso()
            from services.db import managed_session

            seen = 0
            gated_out = 0
            results = []
            total_actions = 0
            async with managed_session() as db:
                signals = await mem.dequeue_pending(db, limit=self.batch_limit)
                seen = len(signals)
                for item in signals:
                    signal = _signal_from_row(item)
                    gate = self.thalamus.gate(signal)
                    if not gate["pass"]:
                        gated_out += 1
                        await mem.mark_processed(db, signal.id)
                        continue

                    memory_context = await self.broker.retrieve_for_signal(db, signal.to_dict())
                    working_memory = self.broker.get_working(f"queue_{signal.id}")
                    cognition = await rsn.engine.reason(signal, working_memory, db, memory_context=memory_context)
                    action_results = []
                    if self.execute_actions and cognition.actions:
                        action_results = await ae.executor.execute_all(cognition, db)
                        total_actions += len(action_results)

                    await mem.log_decision(db, cognition.to_dict())
                    await self.broker.remember_signal_and_cognition(db, signal.to_dict(), cognition.to_dict(), action_results)
                    await db.execute(
                        text("UPDATE brain_decision_log SET action_results = :results WHERE signal_id = :sid"),
                        {
                        "results": json.dumps(action_results, ensure_ascii=False),
                        "sid": cognition.signal_id,
                    })
                    await mem.mark_processed(db, signal.id)
                    self.broker.push_working(f"queue_{signal.id}", signal.to_dict(), cognition.to_dict())
                    results.append({
                        "signal_id": signal.id,
                        "decision": cognition.decision,
                        "confidence": cognition.confidence,
                        "reasoning_level": cognition.reasoning_level,
                        "memory_context_counts": memory_context["counts"],
                        "actions": len(action_results),
                    })
                await db.commit()

            self._stats["signals_seen"] += seen
            self._stats["signals_gated_out"] += gated_out
            return {
                "ok": True,
                "seen": seen,
                "gated_out": gated_out,
                "processed": len(results),
                "actions": total_actions,
                "results": results,
            }


def _signal_from_row(row: dict) -> NeuralSignal:
    payload = row.get("payload", {}) or {}
    context = row.get("context", {}) or {}
    if isinstance(payload, str):
        payload = json.loads(payload) if payload else {}
    if isinstance(context, str):
        context = json.loads(context) if context else {}
    return NeuralSignal(
        id=row["id"],
        type=row.get("type", ""),
        payload=payload,
        source=row.get("source", "queue"),
        urgency=row.get("urgency", 50),
        context=context,
    )


def _iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# 全局单例
brain_core = BrainCore()
