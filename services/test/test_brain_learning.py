"""Brain feedback learning regression tests."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))


def test_learn_feedback_updates_skill_memory(monkeypatch):
    from services.brain import memory as mem

    decision_row = (
        "sig_1", "expense", "auto_approve", 0.8, 2,
        "small expense", "[]", "[]", "L2_stat", "correct", "manager confirmed", "2026-09-06",
    )
    memory_store = {
        ("skill", "expense", "skill:auto_approve"): {
            "type": "skill",
            "module": "expense",
            "key": "skill:auto_approve",
            "value": {"decision": "auto_approve", "success_rate": 0.6, "samples": 9},
            "confidence": 0.6,
            "hit_count": 1,
            "miss_count": 0,
        }
    }

    async def fake_get_decisions(db, limit=50, signal_type=None, decision=None):
        assert signal_type == "expense"
        assert decision == "auto_approve"
        return [{
            "signal_id": decision_row[0],
            "signal_type": decision_row[1],
            "decision": decision_row[2],
            "confidence": decision_row[3],
            "reasoning_level": decision_row[4],
            "reasoning": decision_row[5],
            "action_results": decision_row[7],
            "outcome": "correct",
            "feedback": "manager confirmed",
            "created_at": decision_row[11],
        }]

    async def fake_db_execute(sql, params=None):
        sql = str(sql)
        result = MagicMock()
        result.rowcount = 1
        result.fetchone.return_value = decision_row if "SELECT signal_id" in sql else None
        return result

    async def fake_db_commit():
        pass

    db = MagicMock()
    db.execute = fake_db_execute
    db.commit = fake_db_commit

    async def fake_memory_get(db, type_, module, key):
        return memory_store.get((type_, module, key))

    async def fake_memory_set(db, entry):
        key = (entry["type"], entry["module"], entry["key"])
        existing = memory_store.get(key)
        if existing:
            existing["value"].update(entry.get("value") or {})
            existing["confidence"] = entry.get("confidence", existing["confidence"])
            existing["hit_count"] += int(entry.get("hit_count") or 0)
            existing["miss_count"] += int(entry.get("miss_count") or 0)
        else:
            memory_store[key] = dict(entry, value=dict(entry.get("value") or {}))

    monkeypatch.setattr(mem, "get_decisions", fake_get_decisions)
    monkeypatch.setattr(mem, "memory_get", fake_memory_get)
    monkeypatch.setattr(mem, "memory_set", fake_memory_set)

    skill = asyncio.run(mem.summarize_skill_from_feedback(db, "sig_1", True, "manager confirmed"))

    assert skill["ok"] is True
    assert skill["skill_id"] == "auto_approve"
    assert skill["signal_type"] == "expense"
    assert skill["summary"] == "manager confirmed"
    assert skill["success_rate"] == 1.0
    assert skill["confidence_delta"] == 0.03

    entry = memory_store[("skill", "expense", "skill:auto_approve")]
    assert entry["confidence"] > 0.6
    assert entry["hit_count"] == 2
    assert entry["miss_count"] == 0
    assert entry["value"]["success_rate"] == 1.0
    assert entry["value"]["last_outcome"] == "correct"
