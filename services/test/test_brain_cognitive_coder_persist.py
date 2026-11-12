"""test_brain_cognitive_coder_persist.py — 方向2 训练样本持久化测试

验证：
- set_db 注入后 learn_from_feedback 积累样本持久化到 brain_memory
- 重启后（新实例 + set_db）加载持久化样本
- 批量训练后清空持久化
- 无 db 纯内存兼容（测试环境）
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.cognitive_coder import CognitiveCoder


class MockDB:
    """mock db：内存存储 brain_memory 表。"""

    def __init__(self):
        self.store = {}

    async def execute(self, sql, params):
        # 简单处理：UPSERT / DELETE / SELECT（text() 对象转 str）
        sql_str = str(sql)
        if "INSERT INTO brain_memory" in sql_str:
            key = params.get("key", "")
            self.store[key] = dict(params)
            return type("R", (), {"fetchone": lambda self: None, "rowcount": 1})()
        if "DELETE FROM brain_memory" in sql_str:
            key = params.get("key", "")
            self.store.pop(key, None)
            return type("R", (), {"fetchone": lambda self: None, "rowcount": 1})()
        # SELECT
        key = params.get("key", "")
        if key in self.store:
            row = self.store[key]
            # memory_get 访问 row[0..8]（含 created_at/updated_at），mock 需返回 9 列
            return type("R", (), {
                "fetchone": lambda self: tuple(row.get(k) for k in
                    ["type", "module", "key", "value", "confidence", "hit_count", "miss_count",
                     "created_at", "updated_at"]),
                "rowcount": 1,
            })()
        return type("R", (), {"fetchone": lambda self: None, "rowcount": 0})()


class TestPersist:
    """训练样本持久化测试。"""

    def test_persist_after_accumulate(self):
        """learn_from_feedback 后样本持久化。"""
        coder = CognitiveCoder()
        db = MockDB()
        coder.set_db(db)
        coder.learn_from_feedback(visual={"red": 0.9, "round": 0.9}, correct_decision="escalate")
        assert len(coder._pending_training_samples) == 1
        assert "training_samples" in db.store

    def test_load_after_restart(self):
        """新实例 set_db 加载持久化样本（跨重启保留）。"""
        coder1 = CognitiveCoder()
        db = MockDB()
        coder1.set_db(db)
        coder1.learn_from_feedback(visual={"red": 0.9, "round": 0.9}, correct_decision="escalate")
        # 模拟重启：新实例 + 同一 db
        coder2 = CognitiveCoder()
        coder2.set_db(db)
        assert len(coder2._pending_training_samples) == 1

    def test_no_db_memory_only(self):
        """无 db 纯内存兼容（测试环境）。"""
        coder = CognitiveCoder()
        coder.learn_from_feedback(visual={"red": 0.9, "round": 0.9}, correct_decision="escalate")
        assert len(coder._pending_training_samples) == 1

    def test_clear_after_batch(self):
        """批量训练后清空持久化。"""
        coder = CognitiveCoder()
        db = MockDB()
        coder.set_db(db)
        for _ in range(10):
            coder.learn_from_feedback(visual={"red": 0.9, "round": 0.9}, correct_decision="escalate")
        assert len(coder._pending_training_samples) == 0
        assert "training_samples" not in db.store
