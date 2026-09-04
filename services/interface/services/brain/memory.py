"""services/brain/memory.py — 类脑记忆系统

- WorkingMemory：短期上下文（进程内 dict + TTL）
- LongTermMemory：长期记忆（PostgreSQL brain_memory 表）
- 决策日志：写入 brain_decision_log 表
- 信号队列：写入 brain_signal 表
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger("brain.memory")


class WorkingMemory:
    """类脑工作记忆——短期上下文保持。

    - 按 session_id 隔离
    - TTL 淘汰 + 容量限制
    - 进程内 dict（简单可靠）
    """

    def __init__(self, ttl: int = 3600, max_items: int = 100):
        self._store: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_items))
        self._ttl = ttl
        self._max_items = max_items
        self._last_access: Dict[str, float] = {}

    def push(self, session_id: str, signal: dict, cognition: dict) -> None:
        now = time.time()
        self._store[session_id].append({
            "signal": signal,
            "cognition": cognition,
            "timestamp": now,
            "iso": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        })
        self._last_access[session_id] = now
        self._evict_session(session_id)

    def get_context(self, session_id: str) -> List[dict]:
        now = time.time()
        self._last_access[session_id] = now
        entries = list(self._store.get(session_id, []))
        # TTL 过滤
        return [e for e in entries if (now - e["timestamp"]) < self._ttl]

    def clear_session(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._last_access.pop(session_id, None)

    def clear_all(self) -> None:
        self._store.clear()
        self._last_access.clear()

    def stats(self) -> dict:
        return {
            "sessions": len(self._store),
            "total_entries": sum(len(v) for v in self._store.values()),
            "ttl_seconds": self._ttl,
            "max_per_session": self._max_items,
        }

    def _evict_session(self, session_id: str) -> None:
        now = time.time()
        dq = self._store[session_id]
        while dq and (now - dq[0]["timestamp"]) > self._ttl:
            dq.popleft()


# ── 长期记忆（DB） ──
async def memory_get(db, type_: str, module: str, key: str) -> Optional[dict]:
    result = await db.execute(
        text("SELECT type, module, key, value, confidence, hit_count, miss_count, created_at, updated_at "
             "FROM brain_memory WHERE type = :type AND module = :module AND key = :key"),
        {"type": type_, "module": module, "key": key},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "type": row[0],
        "module": row[1],
        "key": row[2],
        "value": row[3],
        "confidence": row[4],
        "hit_count": row[5],
        "miss_count": row[6],
        "created_at": _iso(row[7]),
        "updated_at": _iso(row[8]),
    }


async def memory_set(db, entry: dict) -> None:
    """插入或更新长期记忆（UPSERT）。"""
    import json
    value_json = json.dumps(entry.get("value", {}), ensure_ascii=False)
    now = datetime.now(timezone.utc)
    await db.execute(
        text("""
            INSERT INTO brain_memory (type, module, key, value, confidence, hit_count, miss_count, created_at, updated_at)
            VALUES (:type, :module, :key, :value, :confidence, :hit_count, :miss_count, NOW(), NOW())
            ON CONFLICT (type, module, key)
            DO UPDATE SET
                value = EXCLUDED.value,
                confidence = EXCLUDED.confidence,
                hit_count = brain_memory.hit_count + EXCLUDED.hit_count,
                miss_count = brain_memory.miss_count + EXCLUDED.miss_count,
                updated_at = NOW()
        """),
        {
            "type": entry["type"],
            "module": entry["module"],
            "key": entry["key"],
            "value": value_json,
            "confidence": entry.get("confidence", 0.5),
            "hit_count": entry.get("hit_count", 0),
            "miss_count": entry.get("miss_count", 0),
        },
    )


async def memory_list(
    db,
    type_: Optional[str] = None,
    module: Optional[str] = None,
    limit: int = 100,
) -> List[dict]:
    params: Dict[str, Any] = {"limit": limit}
    where = []
    if type_:
        where.append("type = :type")
        params["type"] = type_
    if module:
        where.append("module = :module")
        params["module"] = module
    where_sql = " AND ".join(where) if where else "1=1"
    result = await db.execute(
        text(f"SELECT type, module, key, value, confidence, hit_count, miss_count, created_at, updated_at "
             f"FROM brain_memory WHERE {where_sql} ORDER BY updated_at DESC LIMIT :limit"),
        params,
    )
    rows = result.fetchall()
    return [
        {
            "type": r[0], "module": r[1], "key": r[2], "value": r[3],
            "confidence": r[4], "hit_count": r[5], "miss_count": r[6],
            "created_at": _iso(r[7]), "updated_at": _iso(r[8]),
        }
        for r in rows
    ]


async def memory_delete(db, type_: str, module: str, key: str) -> bool:
    result = await db.execute(
        text("DELETE FROM brain_memory WHERE type = :type AND module = :module AND key = :key"),
        {"type": type_, "module": module, "key": key},
    )
    return result.rowcount > 0


async def memory_touch(db, type_: str, module: str, key: str, hit: bool = True) -> None:
    """更新 hit/miss 计数。"""
    if hit:
        await db.execute(
            text("UPDATE brain_memory SET hit_count = hit_count + 1, "
                 "confidence = LEAST(1.0, confidence + 0.02), updated_at = NOW() "
                 "WHERE type = :t AND module = :m AND key = :k"),
            {"t": type_, "m": module, "k": key},
        )
    else:
        await db.execute(
            text("UPDATE brain_memory SET miss_count = miss_count + 1, "
                 "confidence = GREATEST(0.0, confidence - 0.02), updated_at = NOW() "
                 "WHERE type = :t AND module = :m AND key = :k"),
            {"t": type_, "m": module, "k": key},
        )


# ── 决策日志 ──
async def log_decision(db, cognition: dict, actions_result: Optional[List[dict]] = None) -> None:
    import json
    await db.execute(
        text("""
            INSERT INTO brain_decision_log
                (signal_id, signal_type, decision, confidence, reasoning_level,
                 reasoning, actions, action_results, reasoning_level_name)
            VALUES (:signal_id, :signal_type, :decision, :confidence, :level,
                    :reasoning, :actions, :results, :level_name)
        """),
        {
            "signal_id": cognition.get("signal_id", ""),
            "signal_type": cognition.get("signal_type", ""),
            "decision": cognition.get("decision", ""),
            "confidence": cognition.get("confidence", 0.0),
            "level": cognition.get("reasoning_level", 1),
            "reasoning": cognition.get("reasoning", ""),
            "actions": json.dumps(cognition.get("actions", []), ensure_ascii=False),
            "results": json.dumps(actions_result or [], ensure_ascii=False),
            "level_name": ["", "L1_rule", "L2_stat", "L3_llm"][cognition.get("reasoning_level", 1)]
                           if cognition.get("reasoning_level", 1) in (1, 2, 3) else "unknown",
        },
    )


async def get_decisions(
    db,
    limit: int = 50,
    signal_type: Optional[str] = None,
    decision: Optional[str] = None,
) -> List[dict]:
    params: Dict[str, Any] = {"limit": limit}
    where = []
    if signal_type:
        where.append("signal_type = :signal_type")
        params["signal_type"] = signal_type
    if decision:
        where.append("decision = :decision")
        params["decision"] = decision
    where_sql = " AND ".join(where) if where else "1=1"
    result = await db.execute(
        text(f"SELECT id, signal_id, signal_type, decision, confidence, reasoning_level, reasoning, "
             f"action_results, outcome, feedback, created_at "
             f"FROM brain_decision_log WHERE {where_sql} ORDER BY created_at DESC LIMIT :limit"),
        params,
    )
    rows = result.fetchall()
    return [
        {
            "id": r[0], "signal_id": r[1], "signal_type": r[2], "decision": r[3],
            "confidence": r[4], "reasoning_level": r[5], "reasoning": r[6],
            "action_results": r[7], "outcome": r[8], "feedback": r[9],
            "created_at": _iso(r[10]),
        }
        for r in rows
    ]


async def record_outcome(
    db,
    signal_id: str,
    correct: bool,
    feedback: Optional[str] = None,
) -> int:
    """记录决策反馈，用于学习闭环。返回更新行数。"""
    result = await db.execute(
        text("""
            UPDATE brain_decision_log
            SET outcome = :outcome, feedback = :feedback
            WHERE signal_id = :signal_id
        """),
        {"outcome": "correct" if correct else "incorrect",
         "feedback": feedback,
         "signal_id": signal_id},
    )
    return result.rowcount


# ── 信号队列 ──
async def enqueue_signal(db, signal: dict) -> str:
    """把感知信号写入队列，供异步处理。"""
    import json
    await db.execute(
        text("""
            INSERT INTO brain_signal (id, type, payload, source, urgency, context, processed, created_at)
            VALUES (:id, :type, :payload, :source, :urgency, :context, false, NOW())
        """),
        {
            "id": signal.get("id", ""),
            "type": signal.get("type", ""),
            "payload": json.dumps(signal.get("payload", {}), ensure_ascii=False),
            "source": signal.get("source", "manual"),
            "urgency": signal.get("urgency", 50),
            "context": json.dumps(signal.get("context", {}), ensure_ascii=False),
        },
    )
    return signal.get("id", "")


async def dequeue_pending(
    db,
    limit: int = 20,
    min_urgency: int = 0,
) -> List[dict]:
    """取出未处理信号，按紧急度降序。"""
    result = await db.execute(
        text("""
            SELECT id, type, payload, source, urgency, context, created_at
            FROM brain_signal
            WHERE processed = false AND urgency >= :min_urgency
            ORDER BY urgency DESC, created_at ASC
            LIMIT :limit
        """),
        {"limit": limit, "min_urgency": min_urgency},
    )
    rows = result.fetchall()
    return [
        {
            "id": r[0], "type": r[1], "payload": r[2], "source": r[3],
            "urgency": r[4], "context": r[5], "created_at": _iso(r[6]),
        }
        for r in rows
    ]


async def mark_processed(db, signal_id: str) -> bool:
    result = await db.execute(
        text("UPDATE brain_signal SET processed = true WHERE id = :id"),
        {"id": signal_id},
    )
    return result.rowcount > 0


# ── 统计表 DDL ──
BRAIN_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS brain_memory (
    id BIGSERIAL PRIMARY KEY,
    type VARCHAR(32) NOT NULL,
    module VARCHAR(64) NOT NULL,
    key VARCHAR(128) NOT NULL,
    value JSONB,
    confidence DOUBLE PRECISION DEFAULT 0.5,
    hit_count INT DEFAULT 0,
    miss_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (type, module, key)
);

CREATE TABLE IF NOT EXISTS brain_decision_log (
    id BIGSERIAL PRIMARY KEY,
    signal_id VARCHAR(64) NOT NULL,
    signal_type VARCHAR(64) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    reasoning_level INT NOT NULL DEFAULT 1,
    reasoning TEXT,
    actions JSONB,
    action_results JSONB,
    reasoning_level_name VARCHAR(16),
    outcome VARCHAR(16),
    feedback TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bdl_signal ON brain_decision_log (signal_id);
CREATE INDEX IF NOT EXISTS idx_bdl_type ON brain_decision_log (signal_type, decision);

CREATE TABLE IF NOT EXISTS brain_signal (
    id VARCHAR(64) PRIMARY KEY,
    type VARCHAR(64) NOT NULL,
    payload JSONB,
    source VARCHAR(32) DEFAULT 'manual',
    urgency INT DEFAULT 50,
    context JSONB,
    processed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bsig_processed ON brain_signal (processed, urgency DESC);
"""


async def init_brain_tables(db) -> None:
    """幂等建表。"""
    for stmt in BRAIN_TABLES_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            await db.execute(text(stmt))


def _iso(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat(timespec="milliseconds")
    return str(v)


# ── 全局单例 ──
working_memory = WorkingMemory()
