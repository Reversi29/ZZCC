"""Semantic memory regression tests.

These tests lock the nGQL retrieval contract: semantic memory must return
actual vertex properties/edges, not only vertex ids.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))


def _resp(*rows):
    resp = MagicMock()
    resp.is_succeeded.return_value = True
    resp.error_msg.return_value = ""
    if rows and isinstance(rows[0], dict):
        keys = list(rows[0].keys())
        row_lists = [[row.get(k) for k in keys] for row in rows]
    elif rows and isinstance(rows[0], list) and rows[0] and isinstance(rows[0][0], dict):
        keys = list(rows[0][0].keys())
        row_lists = [[row.get(k) for k in keys] for row in rows[0]]
    else:
        keys = []
        row_lists = [list(row) for row in rows]
    resp.rows.return_value = [SimpleNamespace(values=row_list) for row_list in row_lists]
    resp.keys.return_value = keys
    return resp


class _FakeGraph:
    def fetch_vertex(self, *args, **kwargs):
        return []

    def _rows_to_dicts(self, resp):
        keys = list(resp.keys())
        return [{k: v for k, v in zip(keys, row.values)} for row in resp.rows()]

    create_space = lambda self, *args, **kwargs: None
    wait_space = lambda self, *args, **kwargs: None
    create_tag = lambda self, *args, **kwargs: None
    create_edge_type = lambda self, *args, **kwargs: None


def test_semantic_retrieve_returns_vertex_properties_and_edges(monkeypatch):
    import services.brain.semantic as semantic_mod
    from services.brain import semantic as sem_pkg

    queries = []
    responses = [
        _resp([{"vid": "vid_signal", "signal_type": "expense", "module": "ExpenseClaim", "source": "api_check", "urgency": 70, "keyword": "expense", "confidence": 0.85, "created_at": "c", "updated_at": "u", "payload": '{"amount": 700}'}]),
        _resp([]),
        _resp([{"vid": "vid_decision", "decision": "auto_approve", "reasoning_level": 2, "confidence": 0.95, "outcome": "no_action", "reasoning": "r", "created_at": "c", "updated_at": "u", "cognition": '{"reasoning_level": 2}'}]),
        _resp([{"src": "vid_signal", "dst": "vid_decision", "edge": {"src": "vid_signal", "dst": "vid_decision", "edge": "RELATES_TO", "rank": 0, "props": {"confidence": 0.95}}}]),
    ]

    def fake_query(sess, space, nql):
        queries.append(nql)
        return responses.pop(0)

    client = MagicMock()
    client._run.return_value = _resp()
    client.query.side_effect = fake_query
    client.session.return_value = MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=False))

    monkeypatch.setattr(semantic_mod.SemanticMemory, "_client_obj", lambda self: client)
    monkeypatch.setitem(sys.modules, "services.graph", _FakeGraph())

    memory = sem_pkg.SemanticMemory(space="brain_semantic", enabled=True)
    result = asyncio.run(memory.retrieve({"type": "expense", "module": "ExpenseClaim", "decision": "auto_approve", "payload": {"amount": 700}}))

    assert result["enabled"] is True
    assert result["vertices"][0]["vid"] == "vid_signal"
    assert result["vertices"][0]["signal_type"] == "expense"
    assert result["vertices"][0]["module"] == "ExpenseClaim"
    assert json.loads(result["vertices"][0]["payload"]) == {"amount": 700}
    assert result["vertices"][2]["decision"] == "auto_approve"
    assert result["edges"][0]["edge"]["edge"] == "RELATES_TO"
    assert result["edges"][0]["edge"]["props"] == {"confidence": 0.95}
    assert any("YIELD id(vertex) AS vid, BrainSignal.signal_type AS signal_type" in q for q in queries)
    assert any("BrainSignal.payload AS payload" in q for q in queries)
    assert any("edgeSrc(edge) AS src" in q for q in queries)
    assert any("edgeDst(edge) AS dst" in q for q in queries)
    assert any("EDGE AS edge" in q for q in queries)
    assert not any("properties(vertex)" in q for q in queries)
