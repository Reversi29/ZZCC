"""services/brain/broker.py — 统一记忆代理。

把工作记忆、情景/技能记忆、语义图谱封装成一组稳定接口：
- remember/retrieve：给 BrainCore 与 /brain/* 路由调用
- semantic 子接口：当前由 services.brain.semantic 提供 NebulaGraph 后端
- NebulaGraph 异常时降级，不阻塞主路径
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from services.brain import memory as mem

logger = logging.getLogger("brain.broker")


class MemoryBroker:
    """统一记忆入口。

    Phase A 只做薄封装：
    - 工作记忆：mem.working_memory
    - 情景/技能/长期记忆：mem.brain_memory
    - 语义记忆：semantic 模块（NebulaGraph，可降级）
    """

    def __init__(self, semantic=None):
        if semantic is None and os.getenv("BRAIN_SEMANTIC_ENABLED", "1").lower() not in {"0", "false", "off", "no"}:
            from services.brain import semantic as semantic_mod
            semantic = semantic_mod.semantic_memory
        self.semantic = semantic

    async def retrieve_for_signal(self, db, signal: Dict[str, Any], limit: int = 10) -> Dict[str, Any]:
        """推理前上下文：PG 长期/情景/技能 + 可选语义图谱。"""
        pg_context = await mem.retrieve_for_signal(db, signal, limit=limit)

        semantic_context: Dict[str, Any] = {}
        semantic_status = "disabled"
        if self.semantic is not None:
            try:
                semantic_context = await self.semantic.retrieve(signal, limit=limit)
                semantic_status = "ok" if semantic_context.get("vertices") or semantic_context.get("edges") else "empty"
            except Exception as exc:
                semantic_status = f"error: {exc}"
                semantic_context = {"vertices": [], "edges": [], "error": str(exc)}

        pg_counts = pg_context.get("counts", {})
        counts = dict(pg_counts)
        counts["semantic_vertices"] = len(semantic_context.get("vertices", []))
        counts["semantic_edges"] = len(semantic_context.get("edges", []))
        counts["semantic_status"] = semantic_status

        return {
            **pg_context,
            "semantic": semantic_context,
            "counts": counts,
        }

    async def remember_signal_and_cognition(
        self,
        db,
        signal: Dict[str, Any],
        cognition: Dict[str, Any],
        action_results: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        """推理/行动后写回：PG 情景+技能；语义图谱 best-effort。"""
        pg_result = await mem.remember_signal_and_cognition(db, signal, cognition, action_results)

        semantic_result: Dict[str, Any] = {}
        semantic_status = "disabled"
        if self.semantic is not None:
            try:
                semantic_result = await self.semantic.remember(signal, cognition, action_results or [])
                semantic_status = "ok" if semantic_result.get("ok") else "partial"
            except Exception as exc:
                semantic_status = f"error: {exc}"
                semantic_result = {"ok": False, "error": str(exc)}

        return {
            **pg_result,
            "semantic": semantic_result,
            "semantic_status": semantic_status,
        }

    def get_working(self, session_id: str) -> List[dict]:
        return mem.working_memory.get_context(session_id)

    def push_working(self, session_id: str, signal: Dict[str, Any], cognition: Dict[str, Any]) -> None:
        mem.working_memory.push(session_id, signal, cognition)

    def stats(self) -> Dict[str, Any]:
        return {
            "working_memory": mem.working_memory.stats(),
            "semantic": self.semantic.status() if self.semantic is not None else {"enabled": False},
        }

    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "working_memory": mem.working_memory.stats(),
            "semantic": self.semantic.status() if self.semantic is not None else {"enabled": False},
        }


# 全局 broker。semantic 在模块导入时延迟初始化，避免 import 期连 NebulaGraph 失败。
broker = MemoryBroker()


def _ensure_semantic() -> None:
    if broker.semantic is not None:
        return
    try:
        from services.brain import semantic as semantic_mod
        broker.semantic = semantic_mod.semantic_memory
    except Exception as exc:
        logger.warning("semantic_memory_init_failed: %s", exc)


def status() -> Dict[str, Any]:
    _ensure_semantic()
    return broker.status()
