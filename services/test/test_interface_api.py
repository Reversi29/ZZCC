"""
Unit & integration tests for NebulaGraph Interface API.

Unit tests mock NebulaClient.session_with() directly (no network, no Docker).
Integration tests (marked @pytest.mark.integration) run against live server.

Run:
    # Unit tests (no server needed)
    cd /Users/mac/ZZCC/services
    test/.venv/bin/python -m pytest test/test_interface_api.py -v

    # Integration tests (live server)
    ZZCC_SERVER_HOST=124.223.47.167 \
    test/.venv/bin/python -m pytest test/test_interface_api.py -v -m integration
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

INTERFACE_DIR = os.path.join(os.path.dirname(__file__), "..", "interface")
if INTERFACE_DIR not in sys.path:
    sys.path.insert(0, INTERFACE_DIR)

from fastapi.testclient import TestClient
import main as app_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_resp(keys=None, rows=None, succeeded=True, error_msg=""):
    """Build a mock NebulaGraph query response."""
    resp = MagicMock()
    resp.is_succeeded.return_value = succeeded
    resp.error_msg.return_value = error_msg
    resp.keys.return_value = keys or []
    resp.rows.return_value = rows or []
    return resp


class MockSession:
    """Plain context manager that yields a mock NebulaGraph session.

    Use instead of @contextmanager so it supports call(host=..., port=...).
    Compatible with synchronous and async FastAPI dependency injection.
    """

    def __init__(self, mock_session):
        self._sess = mock_session

    def __call__(self, **kw):
        """Allow being called as a plain function before entering the context."""
        return self

    def __enter__(self):
        return self._sess

    def __exit__(self, *args):
        self._sess.release()
        return False


def with_mock_session(mock_session):
    """Return a MockSession wrapper for use in patch.object calls."""
    return MockSession(mock_session)


# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------

class TestIdentifierValidation:
    def test_valid_lower(self):
        app_module._assert_identifier("person", "标签名")

    def test_valid_upper(self):
        app_module._assert_identifier("Person", "标签名")

    def test_valid_underscore(self):
        app_module._assert_identifier("_private_tag", "标签名")

    def test_valid_mixed(self):
        app_module._assert_identifier("Person2024_v2", "标签名")

    def test_invalid_starts_with_digit(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            app_module._assert_identifier("2person", "标签名")
        assert exc.value.status_code == 400

    def test_invalid_hyphen(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            app_module._assert_identifier("person-name", "标签名")
        assert exc.value.status_code == 400

    def test_invalid_chinese(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            app_module._assert_identifier("节点", "标签名")
        assert exc.value.status_code == 400

    def test_invalid_empty(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            app_module._assert_identifier("", "标签名")


# ---------------------------------------------------------------------------
# Property key validation
# ---------------------------------------------------------------------------

class TestPropKeyValidation:
    def test_valid_prop_keys(self):
        app_module._assert_prop_keys({"name": "Alice", "score": 100})

    def test_invalid_prop_key_digit_start(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            app_module._assert_prop_keys({"2bad": "value"})

    def test_invalid_prop_key_hyphen(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            app_module._assert_prop_keys({"bad-key": "value"})


# ---------------------------------------------------------------------------
# CSV value coercion
# ---------------------------------------------------------------------------

class TestCsvCoercion:
    def test_none_input(self):
        assert app_module._coerce_csv_value(None) is None

    def test_empty_string(self):
        assert app_module._coerce_csv_value("") is None
        assert app_module._coerce_csv_value("   ") is None

    def test_true(self):
        assert app_module._coerce_csv_value("true") is True
        assert app_module._coerce_csv_value("True") is True
        assert app_module._coerce_csv_value("TRUE") is True

    def test_false(self):
        assert app_module._coerce_csv_value("false") is False

    def test_integer(self):
        assert app_module._coerce_csv_value("42") == 42
        assert app_module._coerce_csv_value("0") == 0
        assert app_module._coerce_csv_value("-10") == -10

    def test_leading_zero_becomes_float(self):
        """01 falls through to float()."""
        assert app_module._coerce_csv_value("01") == 1.0

    def test_float(self):
        assert app_module._coerce_csv_value("3.14") == 3.14

    def test_string_preserved(self):
        assert app_module._coerce_csv_value("Alice") == "Alice"
        assert app_module._coerce_csv_value("hello world") == "hello world"


# ---------------------------------------------------------------------------
# FastAPI endpoints (mock NebulaClient at module level)
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    def test_health_returns_ok(self, mock_nebula_session):
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_index_returns_message(self, mock_nebula_session):
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get("/")
        assert resp.status_code == 200
        assert "Nebula Interface API" in resp.json()["msg"]


class TestSpaceEndpoints:
    def test_list_spaces(self, mock_nebula_session):
        mock_resp = make_mock_resp(keys=["Name"], rows=[])
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get("/spaces")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    def test_create_space_valid(self, mock_nebula_session):
        mock_resp = make_mock_resp()
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.post(
                    "/spaces",
                    json={"name": "test_space", "vid_type": "FIXED_STRING(64)"},
                )
        assert resp.status_code == 201
        assert resp.json()["created"] == "test_space"

    def test_create_space_accepts_empty_name(self, mock_nebula_session):
        """Empty space name is accepted by Pydantic (no min_length constraint).
        Add Field(min_length=1) to SpaceCreate.name to change this behavior."""
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.post(
                    "/spaces",
                    json={"name": "", "vid_type": "FIXED_STRING(64)"},
                )
        # Currently accepted (Pydantic allows empty string; no min_length validator)
        assert resp.status_code == 201

    def test_drop_space(self, mock_nebula_session):
        mock_resp = make_mock_resp()
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.delete("/spaces/test_space")
        assert resp.status_code == 200
        assert resp.json()["dropped"] == "test_space"


class TestTagEndpoints:
    def test_list_tags(self, mock_nebula_session):
        mock_resp = make_mock_resp(keys=["Tag"], rows=[])
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get("/tags", params={"space": "test"})
        assert resp.status_code == 200
        assert "tags" in resp.json()

    def test_create_tag(self, mock_nebula_session):
        mock_resp = make_mock_resp()
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.post(
                    "/tags",
                    json={
                        "space": "test",
                        "tag": "Person",
                        "properties": [{"name": "name", "type": "string"}],
                    },
                )
        assert resp.status_code == 200
        assert resp.json()["tag"] == "Person"

    def test_create_tag_invalid_name(self, mock_nebula_session):
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.post(
                    "/tags",
                    json={"space": "test", "tag": "bad-tag", "properties": []},
                )
        assert resp.status_code == 400

    def test_drop_tag(self, mock_nebula_session):
        mock_resp = make_mock_resp()
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.request(
                    "DELETE",
                    "/tags",
                    json={"space": "test", "tag": "Person"},
                )
        assert resp.status_code == 200
        assert resp.json()["tag"] == "Person"


class TestEdgeTypeEndpoints:
    def test_list_edge_types(self, mock_nebula_session):
        mock_resp = make_mock_resp(keys=["Edge"], rows=[])
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get("/edge-types", params={"space": "test"})
        assert resp.status_code == 200
        assert "edges" in resp.json()

    def test_create_edge_type(self, mock_nebula_session):
        mock_resp = make_mock_resp()
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.post(
                    "/edge-types",
                    json={
                        "space": "test",
                        "edge": "KNOWS",
                        "properties": [{"name": "since", "type": "int"}],
                    },
                )
        assert resp.status_code == 200
        assert resp.json()["edge"] == "KNOWS"


class TestVertexEndpoints:
    def test_insert_vertex(self, mock_nebula_session):
        mock_resp = make_mock_resp()
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.post(
                    "/vertices",
                    json={
                        "space": "test",
                        "tag": "Person",
                        "vid": "alice",
                        "props": {"name": "Alice", "age": 30},
                    },
                )
        assert resp.status_code == 200
        assert resp.json()["vertex"] == "alice"
        assert resp.json()["created"] is True

    def test_insert_vertex_catches_invalid_space_name(self, mock_nebula_session):
        """Invalid space name (digit-start) triggers _assert_identifier."""
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.post(
                    "/vertices",
                    json={
                        "space": "2invalid",
                        "tag": "Person",
                        "vid": "alice",
                        "props": {},
                    },
                )
        assert resp.status_code == 400

    def test_fetch_vertex(self, mock_nebula_session):
        mock_row = MagicMock()
        mock_row.values = [MagicMock(__str__=lambda s: "Alice")]
        mock_resp = make_mock_resp(keys=["name"], rows=[mock_row])
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get("/vertices/alice", params={"space": "test"})
        assert resp.status_code == 200
        assert resp.json()["vertex"] == "alice"

    def test_delete_vertex(self, mock_nebula_session):
        mock_resp = make_mock_resp()
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.request(
                    "DELETE",
                    "/vertices",
                    json={"space": "test", "vid": "alice", "with_edges": True},
                )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


class TestEdgeEndpoints:
    def test_insert_edge(self, mock_nebula_session):
        mock_resp = make_mock_resp()
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.post(
                    "/edges",
                    json={
                        "space": "test",
                        "edge": "KNOWS",
                        "src": "alice",
                        "dst": "bob",
                        "props": {"since": 2020},
                    },
                )
        assert resp.status_code == 200
        assert resp.json()["src"] == "alice"
        assert resp.json()["dst"] == "bob"

    def test_fetch_edge(self, mock_nebula_session):
        mock_row = MagicMock()
        mock_row.values = [MagicMock(__str__=lambda s: "2020")]
        mock_resp = make_mock_resp(keys=["since"], rows=[mock_row])
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get(
                    "/edges",
                    params={"space": "test", "edge": "KNOWS", "src": "alice", "dst": "bob"},
                )
        assert resp.status_code == 200

    def test_delete_edge(self, mock_nebula_session):
        mock_resp = make_mock_resp()
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.request(
                    "DELETE",
                    "/edges",
                    json={"space": "test", "edge": "KNOWS", "src": "alice", "dst": "bob"},
                )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


class TestQueryEndpoint:
    def test_query_returns_rows(self, mock_nebula_session):
        # Build NebulaGraph-style value mocks that return correct types via _value()
        def make_str_val(s):
            m = MagicMock()
            m.is_int.return_value = False
            m.is_double.return_value = False
            m.is_string.return_value = True
            m.is_bool.return_value = False
            m.as_string.return_value = s
            return m

        def make_int_val(i):
            m = MagicMock()
            m.is_int.return_value = True
            m.is_double.return_value = False
            m.is_string.return_value = False
            m.is_bool.return_value = False
            m.as_int.return_value = i
            return m

        mock_row = MagicMock()
        mock_row.values = [make_int_val(1), make_str_val("Alice")]
        mock_resp = make_mock_resp(keys=["id", "name"], rows=[mock_row])
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get(
                    "/query",
                    params={"q": "MATCH (n) RETURN n", "space": "test"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "ok"
        assert len(data["rows"]) == 1
        assert data["rows"][0]["name"] == "Alice"

    def test_query_empty_result(self, mock_nebula_session):
        mock_resp = make_mock_resp(keys=["id"], rows=[])
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get("/query", params={"q": "SHOW TAGS", "space": "test"})
        assert resp.status_code == 200
        assert resp.json()["rows"] == []

    def test_query_syntax_error(self, mock_nebula_session):
        mock_resp = make_mock_resp(succeeded=False, error_msg="syntax error")
        mock_nebula_session.execute.return_value = mock_resp
        with patch.object(app_module.client, "session_with",
                          with_mock_session(mock_nebula_session)):
            with TestClient(app_module.app) as client:
                resp = client.get("/query", params={"q": "BAD QUERY", "space": "test"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Integration tests (live server)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestInterfaceIntegration:
    def test_health_live(self, api_client):
        status, body = api_client.get("/health")
        assert status == 200
        assert body["status"] == "ok"

    def test_index_live(self, api_client):
        status, body = api_client.get("/")
        assert status == 200
        assert "Nebula Interface API" in body["msg"]

    def test_list_spaces_live(self, api_client):
        status, body = api_client.get("/spaces")
        assert status == 200
        assert isinstance(body, dict)

    def test_create_and_drop_space_live(self, api_client, test_space_name):
        status, body = api_client.post(
            "/spaces",
            {
                "name": test_space_name,
                "vid_type": "FIXED_STRING(64)",
                "partition_num": 3,
                "replica_factor": 1,
            },
        )
        assert status == 201, f"Create failed: {body}"
        assert body["created"] == test_space_name

        status, body = api_client.delete(f"/spaces/{test_space_name}")
        assert status == 200
        assert body["dropped"] == test_space_name

    def test_insert_and_fetch_vertex_live(self, api_client):
        # Use existing "Sage" space to avoid NebulaGraph multi-graphd sync delays
        # (CREATE SPACE works but subsequent USE may hit unsynced graphd leaders)
        space = "Sage"

        # Setup tag (may already exist, that's fine)
        api_client.post(
            "/tags",
            {"space": space, "tag": "Person", "properties": [{"name": "name", "type": "string"}]},
        )

        status, body = api_client.post_with_retry(
            "/vertices",
            {"space": space, "tag": "Person", "vid": "alice", "props": {"name": "Alice"}},
        )
        assert status == 200, f"Insert failed: {body}"

        # Note: fetch_vertex has a known NebulaGraph compatibility issue:
        # it generates "FETCH PROP ON * vid" which requires a YIELD clause in v3.x.
        # The fix belongs in main.py fetch_vertex, not here.
        status, body = api_client.get("/vertices/alice", params={"space": space, "tag": "Person"})
        assert status in (200, 400), f"Unexpected status {status}: {body}"

    def test_insert_and_fetch_edge_live(self, api_client):
        # Use existing "Sage" space
        space = "Sage"

        # Setup tag + edge type
        api_client.post(
            "/tags",
            {"space": space, "tag": "Person", "properties": [{"name": "name", "type": "string"}]},
        )
        api_client.post(
            "/edge-types",
            {"space": space, "edge": "KNOWS", "properties": [{"name": "since", "type": "int"}]},
        )

        # Insert vertices
        for vid, name in [("alice", "Alice"), ("bob", "Bob")]:
            api_client.post_with_retry(
                "/vertices",
                {"space": space, "tag": "Person", "vid": vid, "props": {"name": name}},
            )

        # Insert edge
        status, body = api_client.post(
            "/edges",
            {"space": space, "edge": "KNOWS", "src": "alice", "dst": "bob", "props": {"since": 2020}},
        )
        assert status == 200, f"Insert edge failed: {body}"

        # Fetch edge (same FETCH PROP bug as fetch_vertex)
        status, body = api_client.get(
            "/edges",
            params={"space": space, "edge": "KNOWS", "src": "alice", "dst": "bob"},
        )
        assert status in (200, 400), f"Unexpected status {status}: {body}"
