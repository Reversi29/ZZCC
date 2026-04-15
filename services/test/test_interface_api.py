"""
FastAPI interface tests — unit + integration.

Run:
    pytest test/ -v -m "not integration"   # unit tests (mocked)
    pytest test/ -v -m integration          # live server
"""
import csv
import io
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import re
import importlib
import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from typing import Annotated

# Tests import from the local interface package
import sys
sys.path.insert(0, "interface")
from modules.nebula_client import NebulaClient, NebulaError
import modules.nebula_client as nb_mod


# ============================================================
# Helpers
# ============================================================

def _mock_session():
    """Return a fresh mock Nebula session."""
    sess = MagicMock()
    resp = MagicMock()
    resp.is_succeeded.return_value = True
    resp.error_msg.return_value = ""
    resp.keys.return_value = []
    resp.rows.return_value = []
    sess.execute.return_value = resp
    sess.release = MagicMock()
    return sess, resp


@contextmanager
def _cm(mock_sess, *args, **kwargs):
    """Context manager wrapping a mock session."""
    yield mock_sess


# ============================================================
# Unit tests — NebulaClient
# ============================================================
class TestFormatValue:
    """Test NebulaClient._format_value() for all value types."""

    @staticmethod
    def _fmt(v):
        return NebulaClient._format_value(v)

    def test_bool_true(self):
        assert self._fmt(True) == "true"

    def test_bool_false(self):
        assert self._fmt(False) == "false"

    def test_int(self):
        assert self._fmt(42) == "42"
        assert self._fmt(0) == "0"

    def test_negative_int(self):
        assert self._fmt(-10) == "-10"

    def test_float(self):
        assert self._fmt(3.14) == "3.14"

    def test_string_plain(self):
        assert self._fmt("hello") == '"hello"'

    def test_string_with_double_quote(self):
        assert self._fmt('say "hi"') == r'"say \"hi\""'

    def test_string_with_backslash(self):
        # Backslash must be escaped (order: \\ first, then \")
        assert self._fmt("path\\to\\file") == r'"path\\to\\file"'
        assert self._fmt("a\\b") == r'"a\\b"'

    def test_string_with_backslash_and_quote(self):
        assert self._fmt('path\\"quote') == r'"path\\\"quote"'


class TestClientSQL:
    """Test SQL generation (by inspecting the stmt passed to execute())."""

    def _stmt(self, name, **kw):
        sess, resp = _mock_session()
        NebulaClient._run.__get__(NebulaClient).__call__(  # pylint: disable=protected-access
            NebulaClient("h", 9669, "u", "p"), sess, name, **kw
        )
        # We actually need to call the real _run to generate the stmt
        # For unit tests: test the public methods which call _run internally
        return sess.execute.call_args[0][0]  # first positional arg to execute()

    def test_create_space(self):
        sess, resp = _mock_session()
        c = NebulaClient("h", 9669, "u", "p")
        c._run(sess, "CREATE SPACE IF NOT EXISTS `test`(partition_num=3, replica_factor=1, vid_type=FIXED_STRING(64));")
        # Just verify _run doesn't raise
        assert sess.execute.called

    def test_drop_space(self):
        sess, resp = _mock_session()
        c = NebulaClient("h", 9669, "u", "p")
        c.drop_space(sess, "my_space")
        call = sess.execute.call_args[0][0]
        assert "DROP SPACE" in call
        assert "`my_space`" in call

    def test_list_spaces(self):
        row = MagicMock()
        v = MagicMock()
        v.as_string.return_value = "Sage"
        row.values = [v]
        sess, resp = _mock_session()
        resp.rows.return_value = [row]
        c = NebulaClient("h", 9669, "u", "p")
        names = c.list_spaces(sess)
        assert "Sage" in names

    def test_insert_vertex(self):
        sess, resp = _mock_session()
        c = NebulaClient("h", 9669, "u", "p")
        c.insert_vertex(sess, space="S", vid="v1", tag="Person", props={"name": "Alice"})
        call = sess.execute.call_args[0][0]
        assert "INSERT VERTEX" in call
        assert '"v1"' in call
        assert '"Alice"' in call

    def test_insert_vertex_bool_true(self):
        sess, resp = _mock_session()
        c = NebulaClient("h", 9669, "u", "p")
        c.insert_vertex(sess, space="S", vid="v1", tag="Tag", props={"active": True})
        call = sess.execute.call_args[0][0]
        assert "true" in call

    def test_insert_edge(self):
        sess, resp = _mock_session()
        c = NebulaClient("h", 9669, "u", "p")
        c.insert_edge(sess, space="S", src="a", dst="b", edge="KNOWS", props={"since": 2020})
        call = sess.execute.call_args[0][0]
        assert "INSERT EDGE" in call
        assert '"a"' in call
        assert '"b"' in call
        assert "2020" in call

    def test_fetch_vertex_yield(self):
        sess, resp = _mock_session()
        c = NebulaClient("h", 9669, "u", "p")
        c.fetch_vertex(sess, space="S", vid="v1", tag="Person")
        call = sess.execute.call_args[0][0]
        assert "FETCH PROP ON" in call
        assert "YIELD" in call  # Must have YIELD for NebulaGraph 3.x

    def test_fetch_edge_yield(self):
        sess, resp = _mock_session()
        c = NebulaClient("h", 9669, "u", "p")
        c.fetch_edge(sess, space="S", src="a", dst="b", edge="KNOWS")
        call = sess.execute.call_args[0][0]
        assert "FETCH PROP ON" in call
        assert "YIELD" in call

    def test_run_raises_nebula_error(self):
        sess, resp = _mock_session()
        resp.is_succeeded.return_value = False
        resp.error_msg.return_value = "SpaceNotFound"
        c = NebulaClient("h", 9669, "u", "p")
        with pytest.raises(NebulaError) as exc_info:
            c._run(sess, "BAD QUERY")
        assert "SpaceNotFound" in str(exc_info.value)


class TestClientPoolInit:
    def test_init_pool_success(self):
        with patch("modules.nebula_client.ConnectionPool") as MockPool:
            mock_instance = MagicMock()
            MockPool.return_value = mock_instance
            mock_instance.init.return_value = True
            c = NebulaClient("h", 9669, "u", "p")
            result = c.init_pool()
            assert result is True

    def test_init_pool_failure(self):
        with patch("modules.nebula_client.ConnectionPool") as MockPool:
            mock_instance = MagicMock()
            MockPool.return_value = mock_instance
            mock_instance.init.return_value = False
            c = NebulaClient("h", 9669, "u", "p")
            result = c.init_pool()
            assert result is False

    def test_session_uses_defaults(self):
        with patch("modules.nebula_client.ConnectionPool") as MockPool:
            mock_instance = MagicMock()
            MockPool.return_value = mock_instance
            mock_instance.init.return_value = True
            mock_sess = MagicMock()
            mock_instance.get_session.return_value = mock_sess
            c = NebulaClient("h", 9669, "user", "pass")
            c.init_pool()
            with c.session() as sess:
                pass
            mock_instance.get_session.assert_called_once_with("user", "pass")


# ============================================================
# Unit tests — FastAPI endpoints (mock client)
# ============================================================
class TestCsvCoercion:
    def _coerce(self, val):
        # _coerce is defined in main.py
        import main
        return main._coerce(val)

    def test_none(self):
        assert self._coerce(None) is None

    def test_empty(self):
        assert self._coerce("") is None

    def test_true(self):
        assert self._coerce("true") is True
        assert self._coerce("True") is True

    def test_false(self):
        assert self._coerce("false") is False
        assert self._coerce("FALSE") is False

    def test_integer(self):
        assert self._coerce("42") == 42
        assert self._coerce("-7") == -7

    def test_leading_zero_becomes_float(self):
        # "01" is not a valid integer literal in nGQL, so it becomes float
        assert self._coerce("01") == 1.0

    def test_float(self):
        assert self._coerce("3.14") == 3.14

    def test_string(self):
        assert self._coerce("hello world") == "hello world"


class TestIdentifierValidation:
    """Test _check_id regex logic (mirrors the RE in main.py)."""
    RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def _ok(self, name):
        return bool(self.RE.match(name) and name)

    def test_valid_lower(self):
        assert self._ok("person")

    def test_valid_upper(self):
        assert self._ok("PERSON")

    def test_valid_underscore(self):
        assert self._ok("_private")

    def test_valid_mixed(self):
        assert self._ok("MyClass_123")

    def test_invalid_digit_start(self):
        assert not self._ok("2invalid")

    def test_invalid_hyphen(self):
        assert not self._ok("my-tag")

    def test_invalid_space(self):
        assert not self._ok("my tag")

    def test_invalid_empty(self):
        assert not self._ok("")

    def test_invalid_chinese(self):
        assert not self._ok("中文")


class TestAPIEndpoints:
    """Test FastAPI endpoint logic with mocked Nebula client."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        from contextlib import contextmanager
        
        # Build the mock session/response objects
        self.mock_sess = MagicMock()
        self.mock_resp = MagicMock()
        self.mock_resp.is_succeeded.return_value = True  # default; override per test
        self.mock_resp.error_msg.return_value = ""
        self.mock_resp.keys.return_value = ["Name"]
        self.mock_resp.rows.return_value = []
        self.mock_sess.execute.return_value = self.mock_resp
        class _MockSession:
            def __init__(self, real):
                self._real = real
            async def __aenter__(self):
                return self._real
            async def __aexit__(self, *a):
                pass
            def __getattr__(self, name):
                return getattr(self._real, name)
        _mock_sess_cm = lambda *a, **kw: _MockSession(self.mock_sess)

        # Create a mock NebulaClient
        # _run must call real _run logic so is_succeeded() check works
        # Use side_effect so it calls the real method when needed
        mock_client = MagicMock()
        mock_client.list_spaces = MagicMock(return_value=[])
        # Return a simple sync context manager that yields mock_sess
        class _SyncCM:
            def __init__(self, sess):
                self._sess = sess
            def __enter__(self):
                return self._sess
            def __exit__(self, *a):
                pass
        mock_client.session_with = MagicMock(side_effect=lambda *a, **kw: _SyncCM(self.mock_sess))

        # _run side_effect: check is_succeeded and raise if False
        def _run_side_effect(sess, stmt):
            if not self.mock_resp.is_succeeded():
                raise NebulaError(self.mock_resp.error_msg(), stmt=stmt)
            return self.mock_resp
        mock_client._run = MagicMock(side_effect=_run_side_effect)

        import modules.nebula_client as nb_mod
        import dependencies
        with patch("modules.nebula_client.ConnectionPool") as MockPool, \
             patch.object(nb_mod, "get_client", return_value=mock_client):
            mock_pool_instance = MagicMock()
            mock_pool_instance.init.return_value = True
            mock_pool_instance.get_session.return_value = self.mock_sess
            MockPool.return_value = mock_pool_instance

            import main as m
            importlib.reload(m)

            # Patch _client so get_client() returns our mock.
            nb_mod._client = mock_client

            # Override get_session dependency so endpoints get our mock session
            # Must match exact signature to avoid FastAPI treating *args/**kwargs as query params
            async def fake_get_session(                nebula_host: Annotated[str | None, Header(alias="X-Nebula-Host")] = None,
                nebula_port: Annotated[int | None, Header(alias="X-Nebula-Port")] = None,
                nebula_user: Annotated[str | None, Header(alias="X-Nebula-User")] = None,
                nebula_password: Annotated[str | None, Header(alias="X-Nebula-Password")] = None,
            ):
                yield self.mock_sess

            m.app.dependency_overrides[dependencies.get_session] = fake_get_session

            # Override verify_api_key to bypass API key check in tests
            m.app.dependency_overrides[dependencies.verify_api_key] = lambda x=None: "test-key"

            self.app = m.app
            self.client = TestClient(self.app, raise_server_exceptions=False)
            yield

    # -- Health -----------------------------------------------------------
    def test_health_returns_ok(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert data["status"] == "ok"

    # -- Spaces -----------------------------------------------------------
    def test_list_spaces(self):
        row = MagicMock()
        v = MagicMock()
        v.as_string.return_value = "Sage"
        row.values = [v]
        self.mock_resp.rows.return_value = [row]

        resp = self.client.get("/api/v1/spaces")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert any(s["Name"] == "Sage" for s in body["data"]["spaces"])

    def test_create_space_success(self):
        resp = self.client.post("/api/v1/spaces", json={
            "name": "test_space",
            "vid_type": "FIXED_STRING(64)",
        })
        assert resp.status_code == 201
        assert resp.json()["ok"] is True

    def test_create_space_invalid_name(self):
        resp = self.client.post("/api/v1/spaces", json={
            "name": "bad name",
            "vid_type": "FIXED_STRING(64)",
        })
        assert resp.status_code == 422  # Pydantic validation failure

    def test_create_space_empty_name(self):
        resp = self.client.post("/api/v1/spaces", json={"name": ""})
        assert resp.status_code == 422

    def test_drop_space(self):
        resp = self.client.delete("/api/v1/spaces/test_space")
        assert resp.status_code == 200

    # -- Tags -------------------------------------------------------------
    def test_create_tag(self):
        resp = self.client.post("/api/v1/tags", json={
            "space": "S", "tag": "Person",
            "properties": [{"name": "name", "type": "string"}],
        })
        assert resp.status_code == 201

    def test_create_tag_invalid_name(self):
        resp = self.client.post("/api/v1/tags", json={
            "space": "S", "tag": "bad-name",
            "properties": [],
        })
        assert resp.status_code == 400

    def test_drop_tag(self):
        resp = self.client.request("DELETE", "/api/v1/tags", json={"space": "S", "tag": "Person"})
        assert resp.status_code == 200

    # -- Edges ------------------------------------------------------------
    def test_create_edge_type(self):
        resp = self.client.post("/api/v1/edge-types", json={
            "space": "S", "edge": "KNOWS",
            "properties": [{"name": "since", "type": "int"}],
        })
        assert resp.status_code == 201

    # -- Vertices ----------------------------------------------------------
    def test_insert_vertex(self):
        resp = self.client.post("/api/v1/vertices", json={
            "space": "S", "tag": "Person", "vid": "alice",
            "props": {"name": "Alice"},
        })
        assert resp.status_code == 201

    def test_insert_vertex_invalid_vid(self):
        resp = self.client.post("/api/v1/vertices", json={
            "space": "S", "tag": "Person", "vid": "2bad",
            "props": {},
        })
        assert resp.status_code == 400

    def test_insert_vertex_empty_vid(self):
        resp = self.client.post("/api/v1/vertices", json={
            "space": "S", "tag": "Person", "vid": "",
            "props": {},
        })
        # Pydantic min_length=1 → 422
        assert resp.status_code == 422

    def test_delete_vertex(self):
        resp = self.client.request("DELETE", "/api/v1/vertices", json={
            "space": "S", "vid": "alice",
        })
        assert resp.status_code == 200

    # -- Query -------------------------------------------------------------
    def test_query_success(self):
        row = MagicMock()
        v = MagicMock()
        v.is_string.return_value = True
        v.as_string.return_value = "Alice"
        row.values = [v]
        self.mock_resp.rows.return_value = [row]
        self.mock_resp.keys.return_value = ["name"]

        resp = self.client.get("/api/v1/query", params={"q": "MATCH (n) RETURN n", "space": "Sage"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["rows"][0]["name"] == "Alice"

    def test_query_empty_result(self):
        self.mock_resp.rows.return_value = []
        resp = self.client.get("/api/v1/query", params={"q": "SHOW TAGS", "space": "S"})
        assert resp.status_code == 200
        assert resp.json()["data"]["rows"] == []

    def test_query_syntax_error(self):
        self.mock_resp.is_succeeded.return_value = False
        self.mock_resp.error_msg.return_value = "SyntaxError: ..."

        resp = self.client.get("/api/v1/query", params={"q": "BAD QUERY", "space": "S"})
        assert resp.status_code == 400

    # -- Response envelope -------------------------------------------------
    def test_response_envelope(self):
        """All endpoints return {ok: bool, data: ...}."""
        resp = self.client.get("/api/v1/spaces")
        body = resp.json()
        assert "ok" in body
        assert "data" in body


# ============================================================
# ============================================================
# PATCH endpoints — partial update (fetch-merge-delete-reinsert)
# ============================================================
class TestPatchEndpoints:
    """PATCH /vertices/{vid}, /edges, /tags, /edge-types."""

    @pytest.fixture(autouse=True)
    def setup(self):
        import sys
        # Import at fixture level so they live beyond the `with` block scope
        import routers.vertices as rv_mod
        import routers.edges as re_mod

        def fetch_v(client, sess, space, vid, tag=None):
            return [] if vid == "ghost" else [{"Name": "Alice", "Age": 30}]

        def fetch_e(client, sess, space, src, dst, edge):
            return [{"_src": src, "_dst": dst, "since": 2020}]

        def ins_v(client, sess, space, vid, tag, props):
            mr = MagicMock()
            mr.is_succeeded.return_value = True
            mr.error_msg.return_value = ""
            return mr

        def del_v(client, sess, space, vid, with_edges):
            mr = MagicMock()
            mr.is_succeeded.return_value = True
            mr.error_msg.return_value = ""
            return mr

        def ins_e(client, sess, space, src, dst, edge, props):
            mr = MagicMock()
            mr.is_succeeded.return_value = True
            mr.error_msg.return_value = ""
            return mr

        def del_e(client, sess, space, src, dst, edge):
            mr = MagicMock()
            mr.is_succeeded.return_value = True
            mr.error_msg.return_value = ""
            return mr

        # Save originals for cleanup
        origs = {
            "fv": rv_mod.fetch_vertex,
            "iv": rv_mod.insert_vertex,
            "dv": rv_mod.delete_vertex,
            "fe": re_mod.fetch_edge,
            "ie": re_mod.insert_edge,
            "de": re_mod.delete_edge,
        }

        # Apply patches to router module namespaces
        rv_mod.fetch_vertex = fetch_v
        rv_mod.insert_vertex = ins_v
        rv_mod.delete_vertex = del_v
        re_mod.fetch_edge = fetch_e
        re_mod.insert_edge = ins_e
        re_mod.delete_edge = del_e

        # Build mock client
        sys.path.insert(0, "interface")
        self.mock_sess = MagicMock()
        self.mock_resp = MagicMock()
        self.mock_resp.is_succeeded.return_value = True
        self.mock_resp.error_msg.return_value = ""
        self.mock_resp.keys.return_value = ["Name"]
        self.mock_resp.rows.return_value = []
        self.mock_sess.execute.return_value = self.mock_resp
        mock_client = MagicMock()
        mock_client.list_spaces = MagicMock(return_value=[])

        with patch("modules.nebula_client.ConnectionPool") as MockPool, \
                 patch.object(nb_mod, "get_client", return_value=mock_client):
            MockPool.return_value.init.return_value = True
            MockPool.return_value.get_session.return_value = self.mock_sess

            import main as m
            importlib.reload(m)
            import dependencies
            import modules.nebula_client as nb_mod
            nb_mod._client = mock_client

            async def fake_sess(
                nebula_host: Annotated[str | None, Header(alias="X-Nebula-Host")] = None,
                nebula_port: Annotated[int | None, Header(alias="X-Nebula-Port")] = None,
                nebula_user: Annotated[str | None, Header(alias="X-Nebula-User")] = None,
                nebula_password: Annotated[str | None, Header(alias="X-Nebula-Password")] = None,
            ):
                return self.mock_sess

            m.app.dependency_overrides[m.get_session] = fake_sess
            self.client = TestClient(m.app, raise_server_exceptions=False)

        yield
        # Restore original functions
        rv_mod.fetch_vertex = origs["fv"]
        rv_mod.insert_vertex = origs["iv"]
        rv_mod.delete_vertex = origs["dv"]
        re_mod.fetch_edge = origs["fe"]
        re_mod.insert_edge = origs["ie"]
        re_mod.delete_edge = origs["de"]
        m.app.dependency_overrides.clear()

    # Vertex PATCH
    def test_patch_vertex_partial_update(self):
        resp = self.client.patch("/api/v1/vertices/alice",
                                 json={"space": "S", "tag": "Person",
                                       "props": {"Age": 31}})
        assert resp.status_code == 200, resp.text

    def test_patch_vertex_not_found(self):
        resp = self.client.patch("/api/v1/vertices/ghost",
                                 json={"space": "S", "tag": "Person",
                                       "props": {"Age": 31}})
        assert resp.status_code == 404, resp.text

    def test_patch_vertex_invalid_vid(self):
        resp = self.client.patch("/api/v1/vertices/2bad",
                                 json={"space": "S", "tag": "Person", "props": {}})
        assert resp.status_code == 400  # check_identifier

    # Edge PATCH
    def test_patch_edge_partial_update(self):
        resp = self.client.patch("/api/v1/edges",
                                 json={"space": "S", "edge": "KNOWS",
                                       "src": "alice", "dst": "bob",
                                       "props": {"since": 2021}})
        assert resp.status_code == 200, resp.text

    # Tag PATCH
    def test_patch_tag_add_properties(self):
        resp = self.client.patch("/api/v1/tags",
                                 json={"space": "S", "tag": "Person",
                                       "properties": [{"name": "email", "type": "string"}]})
        assert resp.status_code == 200

    def test_patch_tag_invalid_name(self):
        resp = self.client.patch("/api/v1/tags",
                                 json={"space": "S", "tag": "bad-name", "properties": []})
        assert resp.status_code == 400

    # Edge-type PATCH
    def test_patch_edge_type_add_properties(self):
        resp = self.client.patch("/api/v1/edge-types",
                                 json={"space": "S", "edge": "KNOWS",
                                       "properties": [{"name": "weight", "type": "double"}]})
        assert resp.status_code == 200

    def test_patch_edge_type_invalid_name(self):
        resp = self.client.patch("/api/v1/edge-types",
                                 json={"space": "S", "edge": "bad-edge", "properties": []})
        assert resp.status_code == 400



class TestDocumentConvert:
    """POST /convert/pdf/to-csv/* and /convert/docx/to-csv/*."""

    @pytest.fixture(autouse=True)
    def setup(self):
        sys.path.insert(0, "interface")
        self.mock_sess = MagicMock()
        self.mock_resp = MagicMock()
        self.mock_resp.is_succeeded.return_value = True
        self.mock_resp.error_msg.return_value = ""
        self.mock_sess.execute.return_value = self.mock_resp

        mock_client = MagicMock()
        mock_client.list_spaces = MagicMock(return_value=[])

        @contextmanager
        def _scm(*args, **kw):
            yield self.mock_sess
        mock_client.session_with = MagicMock(side_effect=lambda *a, **kw: _scm(*a, **kw))
        mock_client._run = MagicMock(return_value=self.mock_resp)

        with patch("modules.nebula_client.ConnectionPool") as MockPool, \
                 patch.object(nb_mod, "get_client", return_value=mock_client):
            MockPool.return_value.init.return_value = True
            MockPool.return_value.get_session.return_value = self.mock_sess

            import main as m
            importlib.reload(m)
            import dependencies
            import modules.nebula_client as nb_mod
            nb_mod._client = mock_client

            async def fake_sess(
                nebula_host: Annotated[str | None, Header(alias="X-Nebula-Host")] = None,
                nebula_port: Annotated[int | None, Header(alias="X-Nebula-Port")] = None,
                nebula_user: Annotated[str | None, Header(alias="X-Nebula-User")] = None,
                nebula_password: Annotated[str | None, Header(alias="X-Nebula-Password")] = None,
            ):
                return self.mock_sess

            m.app.dependency_overrides[m.get_session] = fake_sess
            self.client = TestClient(m.app, raise_server_exceptions=False)

        yield
        m.app.dependency_overrides.clear()

    def test_convert_pdf_vertices_csv(self):
        # Patch the text extractor at the router module level
        with patch("routers.documents._extract_pdf_text",
                   return_value=[(1, "Alice"), (2, "Bob")]):
            from io import BytesIO
            resp = self.client.post(
                "/api/v1/convert/pdf/to-csv/vertices",
                params={"space": "S", "tag": "Doc"},
                files={"file": ("doc.pdf", BytesIO(b"x"), "application/pdf")},
            )
        assert resp.status_code == 200, resp.text
        csv_text = resp.json()["data"]["csv"]
        assert "vid" in csv_text
        assert "Alice" in csv_text

    def test_convert_pdf_vertices_import_now(self):
        with patch("routers.documents._extract_pdf_text",
                   return_value=[(1, "Line1")]):
            from io import BytesIO
            resp = self.client.post(
                "/api/v1/convert/pdf/to-csv/vertices",
                params={"space": "S", "tag": "Doc", "import_now": "true"},
                files={"file": ("doc.pdf", BytesIO(b"x"), "application/pdf")},
            )
        assert resp.status_code == 200, resp.text
        assert "imported" in resp.json()["data"]
        assert "csv" not in resp.json()["data"]

    def test_convert_docx_vertices_csv(self):
        with patch("routers.documents._extract_docx_text",
                   return_value=[(1, "Para one")]):
            from io import BytesIO
            resp = self.client.post(
                "/api/v1/convert/docx/to-csv/vertices",
                params={"space": "S", "tag": "Doc"},
                files={"file": ("doc.docx", BytesIO(b"x"),
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert resp.status_code == 200, resp.text
        assert "csv" in resp.json()["data"]

    def test_convert_pdf_edges_csv(self):
        with patch("routers.documents._extract_pdf_text",
                   return_value=[(1, "alice,bob,FRIEND")]):
            from io import BytesIO
            resp = self.client.post(
                "/api/v1/convert/pdf/to-csv/edges",
                params={"space": "S", "edge": "REL"},
                files={"file": ("e.pdf", BytesIO(b"x"), "application/pdf")},
            )
        assert resp.status_code == 200, resp.text
        assert "alice" in resp.json()["data"]["csv"]


# ============================================================
# PDF / DOCX — import into Nebula
# ============================================================
class TestDocumentImport:
    """POST /import/pdf/* and /import/docx/* (direct to Nebula)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        sys.path.insert(0, "interface")
        self.mock_sess = MagicMock()
        self.mock_resp = MagicMock()
        self.mock_resp.is_succeeded.return_value = True
        self.mock_resp.error_msg.return_value = ""
        self.mock_sess.execute.return_value = self.mock_resp

        mock_client = MagicMock()
        mock_client.list_spaces = MagicMock(return_value=[])
        mock_client.insert_vertex = MagicMock(return_value=None)
        mock_client.insert_edge = MagicMock(return_value=None)

        @contextmanager
        def _scm(*args, **kw):
            yield self.mock_sess
        mock_client.session_with = MagicMock(side_effect=lambda *a, **kw: _scm(*a, **kw))

        with patch("modules.nebula_client.ConnectionPool") as MockPool, \
                 patch.object(nb_mod, "get_client", return_value=mock_client):
            MockPool.return_value.init.return_value = True
            MockPool.return_value.get_session.return_value = self.mock_sess

            import main as m
            importlib.reload(m)
            import dependencies
            import modules.nebula_client as nb_mod
            nb_mod._client = mock_client

            async def fake_sess(
                nebula_host: Annotated[str | None, Header(alias="X-Nebula-Host")] = None,
                nebula_port: Annotated[int | None, Header(alias="X-Nebula-Port")] = None,
                nebula_user: Annotated[str | None, Header(alias="X-Nebula-User")] = None,
                nebula_password: Annotated[str | None, Header(alias="X-Nebula-Password")] = None,
            ):
                return self.mock_sess

            m.app.dependency_overrides[m.get_session] = fake_sess
            self.client = TestClient(m.app, raise_server_exceptions=False)

        yield
        m.app.dependency_overrides.clear()

    def test_import_pdf_vertices(self):
        with patch("routers.documents._extract_pdf_text",
                   return_value=[(1, "P1"), (2, "P2")]):
            from io import BytesIO
            resp = self.client.post(
                "/api/v1/import/pdf/vertices",
                params={"space": "S", "tag": "Doc"},
                files={"file": ("doc.pdf", BytesIO(b"x"), "application/pdf")},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["imported"] == 2

    def test_import_docx_vertices(self):
        with patch("routers.documents._extract_docx_text",
                   return_value=[(1, "Para one")]):
            from io import BytesIO
            resp = self.client.post(
                "/api/v1/import/docx/vertices",
                params={"space": "S", "tag": "Doc"},
                files={"file": ("doc.docx", BytesIO(b"x"),
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["imported"] == 1

    def test_import_pdf_edges(self):
        with patch("routers.documents._extract_pdf_text",
                   return_value=[(1, "alice,bob,F1"), (2, "charlie,dave,F2")]):
            from io import BytesIO
            resp = self.client.post(
                "/api/v1/import/pdf/edges",
                params={"space": "S", "edge": "REL"},
                files={"file": ("e.pdf", BytesIO(b"x"), "application/pdf")},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["imported"] == 2

    def test_import_docx_edges(self):
        with patch("routers.documents._extract_docx_text",
                   return_value=[(1, "alice,bob")]):
            from io import BytesIO
            resp = self.client.post(
                "/api/v1/import/docx/edges",
                params={"space": "S", "edge": "REL"},
                files={"file": ("e.docx", BytesIO(b"x"),
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["imported"] == 1



# Integration tests (against live server)
# ============================================================
@pytest.mark.integration
class TestInterfaceIntegration:
    """Live integration tests against the server at ZZCC_SERVER_HOST."""

    BASE = "http://124.223.47.167:8001"

    def _req(self, method, path, data=None, params=None):
        import urllib.request, urllib.error, json
        url = self.BASE + path
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{qs}"
        body = json.dumps(data).encode() if data else None
        hdrs = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode())
            except json.JSONDecodeError:
                return e.code, e.read().decode()
        except urllib.error.URLError as e:
            return 0, str(e.reason)

    def _post(self, path, data):
        return self._req("POST", path, data)

    def _get(self, path, params=None):
        return self._req("GET", path, params=params)

    def _delete(self, path, data=None):
        return self._req("DELETE", path, data=data)

    def test_health(self):
        status, body = self._get("/health")
        assert status == 200, body
        assert body["status"] == "ok"

    def test_root(self):
        status, body = self._get("/")
        assert status == 200, body
        assert "NebulaGraph" in body["service"]

    def test_list_spaces(self):
        status, body = self._get("/api/v1/spaces")
        assert status == 200, body
        assert body["ok"] is True

    def test_insert_and_fetch_vertex(self):
        """Use existing 'Sage' space; tag may already exist."""
        space = "Sage"
        tag = "Person"

        # Create tag (may exist already)
        self._post("/api/v1/tags", {
            "space": space, "tag": tag,
            "properties": [{"name": "name", "type": "string"}],
        })

        # Insert vertex
        status, body = self._post("/api/v1/vertices", {
            "space": space, "tag": tag, "vid": f"test_{int(time.time())}",
            "props": {"name": "IntegrationTest"},
        })
        assert status == 201, body

        # Fetch vertex (with tag specified to avoid FETCH * issue)
        vid = "test_integration_person"
        self._post("/api/v1/vertices", {
            "space": space, "tag": tag, "vid": vid,
            "props": {"name": "TestVertex"},
        })
        status, body = self._get("/api/v1/vertices/test_integration_person",
                                  params={"space": space, "tag": tag})
        assert status == 200, body

    def test_edge_flow(self):
        space = "Sage"
        tag = "Person"
        edge = "KNOWS"
        vid_a = f"test_a_{int(time.time())}"
        vid_b = f"test_b_{int(time.time())}"

        # Ensure tag and edge
        self._post("/api/v1/tags", {
            "space": space, "tag": tag,
            "properties": [{"name": "name", "type": "string"}],
        })
        self._post("/api/v1/edge-types", {
            "space": space, "edge": edge,
            "properties": [{"name": "since", "type": "int"}],
        })

        # Insert two vertices
        for vid in (vid_a, vid_b):
            self._post("/api/v1/vertices", {
                "space": space, "tag": tag, "vid": vid,
                "props": {"name": vid},
            })

        # Insert edge
        status, body = self._post("/api/v1/edges", {
            "space": space, "edge": edge,
            "src": vid_a, "dst": vid_b,
            "props": {"since": 2024},
        })
        assert status == 201, body
