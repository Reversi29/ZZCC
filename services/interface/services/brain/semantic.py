"""services/brain/semantic.py — 类脑语义记忆（NebulaGraph 后端）。

原则：
- 只保存语义索引，不替代 PostgreSQL 主账本。
- 启动/查询失败只降级，不阻塞 BrainCore 或 /brain/* 主路径。
- 用固定 space/tag/edge，避免依赖业务方先手建 schema。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.brain.memory import _infer_module, _signal_keywords

logger = logging.getLogger("brain.semantic")

DEFAULT_SPACE = "brain_semantic"
SIGNAL_TAG = "BrainSignal"
DECISION_TAG = "BrainDecision"
RELATION_EDGE = "RELATES_TO"

SIGNAL_COLS = [
    ("signal_type", "string"),
    ("module", "string"),
    ("source", "string"),
    ("urgency", "int64"),
    ("keyword", "string"),
    ("confidence", "double"),
    ("created_at", "string"),
    ("updated_at", "string"),
    ("payload", "string"),
]

DECISION_COLS = [
    ("decision", "string"),
    ("reasoning_level", "int64"),
    ("confidence", "double"),
    ("outcome", "string"),
    ("reasoning", "string"),
    ("created_at", "string"),
    ("updated_at", "string"),
    ("cognition", "string"),
]

RELATION_COLS = [
    ("relation_type", "string"),
    ("signal_id", "string"),
    ("confidence", "double"),
    ("created_at", "string"),
    ("updated_at", "string"),
    ("summary", "string"),
]


def _enabled() -> bool:
    return os.getenv("BRAIN_SEMANTIC_ENABLED", "1").lower() not in {"0", "false", "off", "no"}


def _space() -> str:
    return os.getenv("BRAIN_SEMANTIC_SPACE", DEFAULT_SPACE)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _signal_vid(signal: Dict[str, Any]) -> str:
    sid = signal.get("id") or signal.get("signal_id") or hashlib.sha256(json.dumps(signal, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return f"signal_{sid}"[:63]


def _decision_vid(signal: Dict[str, Any], cognition: Dict[str, Any]) -> str:
    sid = signal.get("id") or signal.get("signal_id") or hashlib.sha256(json.dumps(signal, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    decision = str(cognition.get("decision") or "no_action").replace("/", "_")[:40]
    return f"decision_{sid}_{decision}"[:63]


def _keyword(signal: Dict[str, Any]) -> str:
    keywords = _signal_keywords(signal)
    return "|".join(keywords[:5])


class SemanticMemory:
    """NebulaGraph-backed semantic memory facade."""

    def __init__(self, enabled: bool | None = None, space: Optional[str] = None):
        self.enabled = _enabled() if enabled is None else enabled
        self.space = space or _space()
        self.stats = {
            "enabled": self.enabled,
            "space": self.space,
            "writes": 0,
            "retrieves": 0,
            "errors": 0,
            "last_error": "",
            "last_write_at": None,
            "last_retrieve_at": None,
        }
        self._schema_ready = False
        self._client = None

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "space": self.space,
            "schema_ready": self._schema_ready,
            **{k: v for k, v in self.stats.items() if k not in {"enabled", "space"}},
        }

    def _client_obj(self):
        from modules import nebula_client as neb

        if self._client is None:
            self._client = neb.get_client()
        return self._client

    def _run_sync(self, fn, *args, **kwargs):
        return asyncio.to_thread(fn, *args, **kwargs)

    def _with_session(self, fn):
        client = self._client_obj()
        with client.session() as sess:
            return fn(sess)

    def _ensure_schema_sync(self, sess) -> None:
        from services import graph as g

        client = self._client_obj()
        try:
            client._run(sess, f'USE `{self.space}`; YIELD 1;')
        except Exception:
            g.create_space(client, sess, self.space)
            g.wait_space(client, sess, self.space, timeout=30)
        g.create_tag(client, sess, self.space, SIGNAL_TAG, SIGNAL_COLS)
        g.create_tag(client, sess, self.space, DECISION_TAG, DECISION_COLS)
        g.create_edge_type(client, sess, self.space, RELATION_EDGE, RELATION_COLS)
        self._schema_ready = True

    async def ensure_schema(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": True, "enabled": False, "skipped": True}
        try:
            await self._run_sync(self._with_session, self._ensure_schema_sync)
            return {"ok": True, "enabled": True, "space": self.space, "schema_ready": True}
        except Exception as exc:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(exc)
            logger.warning("brain_semantic_schema_failed: %s", exc)
            return {"ok": False, "enabled": True, "space": self.space, "error": str(exc)}

    async def retrieve(self, signal: Dict[str, Any], limit: int = 10) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "vertices": [], "edges": []}
        self.stats["retrieves"] += 1
        self.stats["last_retrieve_at"] = _iso()
        try:
            data = await self._run_sync(self._retrieve_sync, signal, limit)
            data["enabled"] = True
            return data
        except Exception as exc:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(exc)
            logger.warning("brain_semantic_retrieve_failed: %s", exc)
            return {"enabled": True, "vertices": [], "edges": [], "error": str(exc)}

    async def remember(
        self,
        signal: Dict[str, Any],
        cognition: Dict[str, Any],
        action_results: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": True, "enabled": False, "skipped": True}
        self.stats["writes"] += 1
        self.stats["last_write_at"] = _iso()
        signal_vid = _signal_vid(signal)
        decision_vid = _decision_vid(signal, cognition)
        action_results = action_results or []
        success_count = sum(1 for r in action_results if r.get("ok"))
        total_actions = len(action_results)
        outcome = "unknown"
        if cognition.get("reasoning_level") == 1 and total_actions == 0:
            outcome = "no_action"
        elif total_actions > 0 and success_count == total_actions:
            outcome = "success"
        elif total_actions > 0 and success_count < total_actions:
            outcome = "partial"
        try:
            result = await self._run_sync(self._remember_sync, signal_vid, decision_vid, signal, cognition, outcome)
            result["enabled"] = True
            return {"ok": True, **result}
        except Exception as exc:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(exc)
            logger.warning("brain_semantic_remember_failed: %s", exc)
            return {"ok": False, "enabled": True, "error": str(exc)}

    def _retrieve_sync(self, signal: Dict[str, Any], limit: int) -> Dict[str, Any]:
        from services import graph as g

        client = self._client_obj()
        vid = _signal_vid(signal)
        module = _infer_module(signal)
        signal_type = str(signal.get("type") or "")
        decision = str(signal.get("decision") or signal.get("payload", {}).get("decision") or "")
        with client.session() as sess:
            self._ensure_schema_sync(sess)
            vertices: List[dict] = []
            try:
                vertices.extend(g.fetch_vertex(client, sess, self.space, vid))
            except Exception as exc:
                logger.debug("brain_semantic_fetch_vertex_failed: %s", exc)
            for nql in [
                f'MATCH (n:{SIGNAL_TAG}) WHERE n.module = "{module}" OR n.signal_type = "{signal_type}" '
                "RETURN n LIMIT 20;",
                f'MATCH (n:{DECISION_TAG}) WHERE n.decision = "{decision}" '
                "RETURN n LIMIT 20;" if decision else None,
                f'GO FROM "{vid}" OVER {RELATION_EDGE} YIELD $$.{DECISION_TAG} AS vertex;',
                f'GO FROM "{vid}" OVER {RELATION_EDGE} YIELD EDGE AS edge;',
            ]:
                if not nql:
                    continue
                try:
                    resp = client.query(sess, self.space, nql)
                    rows = g._rows_to_dicts(resp)
                    for row in rows:
                        if "edge" in row:
                            row.setdefault("kind", "edge")
                        else:
                            row.setdefault("kind", "vertex")
                        vertices.append(row)
                except Exception as exc:
                    logging.getLogger("brain.semantic").debug("brain_semantic_lookup_failed: %s", exc)
            return {"vertices": _dedupe(vertices)[:limit], "edges": []}

    def _remember_sync(self, signal_vid: str, decision_vid: str, signal: Dict[str, Any], cognition: Dict[str, Any], outcome: str) -> Dict[str, Any]:
        client = self._client_obj()
        module = _infer_module(signal)
        now = _iso()
        with client.session() as sess:
            self._ensure_schema_sync(sess)
            signal_props = {
                "signal_type": str(signal.get("type") or ""),
                "module": module,
                "source": str(signal.get("source") or ""),
                "urgency": int(signal.get("urgency") or 0),
                "keyword": _keyword(signal),
                "confidence": float(cognition.get("confidence") or 0.0),
                "created_at": signal.get("created_at") or now,
                "updated_at": now,
                "payload": json.dumps(signal.get("payload") or {}, ensure_ascii=False)[:8192],
            }
            decision_props = {
                "decision": str(cognition.get("decision") or "no_action"),
                "reasoning_level": int(cognition.get("reasoning_level") or 1),
                "confidence": float(cognition.get("confidence") or 0.0),
                "outcome": outcome,
                "reasoning": str(cognition.get("reasoning") or "")[:1024],
                "created_at": now,
                "updated_at": now,
                "cognition": json.dumps(cognition, ensure_ascii=False)[:8192],
            }
            edge_props = {
                "relation_type": "signal_decision",
                "signal_id": str(signal.get("id") or ""),
                "confidence": float(cognition.get("confidence") or 0.0),
                "created_at": now,
                "updated_at": now,
                "summary": f"{module}:{cognition.get('decision') or 'no_action'}:{outcome}",
            }
            upsert_vertex(client, sess, self.space, SIGNAL_TAG, signal_vid, signal_props)
            upsert_vertex(client, sess, self.space, DECISION_TAG, decision_vid, decision_props)
            upsert_edge(client, sess, self.space, RELATION_EDGE, signal_vid, decision_vid, edge_props)
        return {"signal_vid": signal_vid, "decision_vid": decision_vid, "outcome": outcome}


def upsert_vertex(client, sess, space: str, tag: str, vid: str, props: Dict[str, Any]) -> None:
    from modules.nebula_client import NebulaClient

    cols = ", ".join(f"`{k}`" for k in props)
    vals = ", ".join(NebulaClient._format_value(v) for v in props.values())
    insert_stmt = f'USE `{space}`; INSERT VERTEX IF NOT EXISTS {tag}({cols}) VALUES "{vid}":({vals});'
    client._run(sess, insert_stmt)
    sets = ", ".join(f"`{k}`={NebulaClient._format_value(v)}" for k, v in props.items())
    update_stmt = f'USE `{space}`; UPDATE VERTEX ON {tag} "{vid}" SET {sets};'
    try:
        client._run(sess, update_stmt)
    except Exception as exc:
        # Tag 不存在或历史 schema 缺字段时，插入已落盘即可；更新失败不阻断写入。
        logger.debug("semantic_update_vertex_failed: %s", exc)


def upsert_edge(client, sess, space: str, edge: str, src: str, dst: str, props: Dict[str, Any]) -> None:
    from modules.nebula_client import NebulaClient

    cols = ", ".join(f"`{k}`" for k in props)
    vals = ", ".join(NebulaClient._format_value(v) for v in props.values())
    insert_stmt = f'USE `{space}`; INSERT EDGE IF NOT EXISTS {edge}({cols}) VALUES "{src}"->"{dst}":({vals});'
    client._run(sess, insert_stmt)
    sets = ", ".join(f"`{k}`={NebulaClient._format_value(v)}" for k, v in props.items())
    update_stmt = f'USE `{space}`; UPDATE EDGE ON {edge} "{src}"->"{dst}" SET {sets};'
    try:
        client._run(sess, update_stmt)
    except Exception as exc:
        logger.debug("semantic_update_edge_failed: %s", exc)


def _dedupe(rows: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for row in rows:
        raw = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if raw not in seen:
            seen.add(raw)
            out.append(row)
    return out


semantic_memory = SemanticMemory()
