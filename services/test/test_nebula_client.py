"""NebulaClient unit tests."""
import pytest
from unittest.mock import MagicMock, patch


def _sess():
    resp = MagicMock()
    resp.is_succeeded.return_value = True
    resp.error_msg.return_value = ""
    resp.keys.return_value = []
    resp.rows.return_value = []
    sess = MagicMock()
    sess.execute.return_value = resp
    sess.release = MagicMock()
    return sess, resp


class TestFormatValue:
    def _fmt(self, v):
        from modules.nebula_client import NebulaClient
        return NebulaClient._format_value(v)

    def test_bool_true(self): assert self._fmt(True) == "true"
    def test_bool_false(self): assert self._fmt(False) == "false"
    def test_int(self): assert self._fmt(42) == "42"
    def test_negative_int(self): assert self._fmt(-7) == "-7"
    def test_float(self): assert self._fmt(3.14) == "3.14"
    def test_string_plain(self): assert self._fmt("hello") == '"hello"'
    def test_string_with_quote(self): assert self._fmt("say \"hi\"") == r'"say \"hi\""'
    def test_string_with_backslash(self): assert self._fmt("path\\to\\file") == r'"path\\to\\file"'
    def test_string_with_backslash_and_quote(self): assert self._fmt("a\\\"b") == r'"a\\\"b"'


class TestNebulaError:
    def test_message(self):
        from modules.nebula_client import NebulaError
        e = NebulaError("SpaceNotFound", stmt="DROP SPACE x")
        assert "SpaceNotFound" in str(e)
        assert e.stmt == "DROP SPACE x"


class TestSpaceOps:
    def test_create_space(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").create_space(
            sess, name="s", vid_type="FIXED_STRING(64)", partition_num=10, replica_factor=1)
        s = sess.execute.call_args[0][0]
        assert "CREATE SPACE" in s
        assert "`s`" in s
        assert "partition_num=10" in s

    def test_drop_space(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").drop_space(sess, "old")
        assert "DROP SPACE" in sess.execute.call_args[0][0]

    def test_list_spaces(self):
        from modules.nebula_client import NebulaClient
        sess, resp = _sess()
        row = MagicMock()
        v = MagicMock()
        v.as_string.return_value = "Sage"
        row.values = [v]
        resp.rows.return_value = [row]
        assert "Sage" in NebulaClient("h", 9669, "u", "p").list_spaces(sess)

    def test_list_spaces_empty(self):
        from modules.nebula_client import NebulaClient
        sess, resp = _sess()
        resp.rows.return_value = []
        assert [] == NebulaClient("h", 9669, "u", "p").list_spaces(sess)


class TestTagOps:
    def test_ensure_tag(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").ensure_tag(
            sess, space="S", tag="Person",
            columns=[("name", "string"), ("age", "int")])
        s = sess.execute.call_args[0][0]
        assert "CREATE TAG" in s and "`Person`" in s

    def test_drop_tag(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").drop_tag(sess, space="S", tag="Person")
        assert "DROP TAG" in sess.execute.call_args[0][0]

    def test_alter_tag_add(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").alter_tag_add(
            sess, space="S", tag="Person",
            columns=[("email", "string")])
        s = sess.execute.call_args[0][0]
        assert "ALTER TAG" in s and "ADD" in s


class TestEdgeOps:
    def test_ensure_edge(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").ensure_edge(
            sess, space="S", edge="KNOWS",
            columns=[("since", "int")])
        s = sess.execute.call_args[0][0]
        assert "CREATE EDGE" in s and "`KNOWS`" in s

    def test_drop_edge(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").drop_edge_type(sess, space="S", edge="KNOWS")
        assert "DROP EDGE" in sess.execute.call_args[0][0]

    def test_alter_edge_add(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").alter_edge_add(
            sess, space="S", edge="KNOWS",
            columns=[("weight", "double")])
        s = sess.execute.call_args[0][0]
        assert "ALTER EDGE" in s and "ADD" in s


class TestVertexOps:
    def test_insert_vertex(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").insert_vertex(
            sess, space="S", vid="v1", tag="Person",
            props={"name": "Alice", "active": True})
        s = sess.execute.call_args[0][0]
        assert "INSERT VERTEX" in s and '"v1"' in s and "true" in s

    def test_delete_vertex_with_edges(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").delete_vertex(
            sess, space="S", vid="v1", with_edges=True)
        s = sess.execute.call_args[0][0]
        assert "WITH EDGE" in s

    def test_delete_vertex_no_edges(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").delete_vertex(
            sess, space="S", vid="v1", with_edges=False)
        assert "WITH EDGE" not in sess.execute.call_args[0][0]

    def test_fetch_vertex_has_yield(self):
        """NebulaGraph 3.x requires YIELD clause on FETCH."""
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").fetch_vertex(
            sess, space="S", vid="v1", tag="Person")
        s = sess.execute.call_args[0][0]
        assert "FETCH PROP ON" in s and "YIELD" in s


class TestEdgeDataOps:
    def test_insert_edge(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").insert_edge(
            sess, space="S", src="a", dst="b", edge="KNOWS",
            props={"since": 2020})
        s = sess.execute.call_args[0][0]
        assert "INSERT EDGE" in s and '"a"' in s and '"b"' in s

    def test_fetch_edge_has_yield(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").fetch_edge(
            sess, space="S", src="a", dst="b", edge="KNOWS")
        s = sess.execute.call_args[0][0]
        assert "FETCH PROP ON" in s and "YIELD" in s

    def test_delete_edge(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").delete_edge(
            sess, space="S", src="a", dst="b", edge="KNOWS")
        assert "DELETE EDGE" in sess.execute.call_args[0][0]


class TestQuery:
    def test_query_ok(self):
        from modules.nebula_client import NebulaClient
        sess, _ = _sess()
        NebulaClient("h", 9669, "u", "p").query(sess, space="S", nql="SHOW TAGS")
        assert "USE `S`" in sess.execute.call_args[0][0]

    def test_query_failure_raises(self):
        from modules.nebula_client import NebulaClient, NebulaError
        sess, resp = _sess()
        resp.is_succeeded.return_value = False
        resp.error_msg.return_value = "SpaceNotFound"
        c = NebulaClient("h", 9669, "u", "p")
        with pytest.raises(NebulaError) as exc:
            c.query(sess, space="S", nql="BAD")
        assert "SpaceNotFound" in str(exc.value)


class TestSessionManagement:
    def test_init_pool_success(self):
        from modules.nebula_client import NebulaClient
        with patch("modules.nebula_client.ConnectionPool") as m:
            m.return_value.init.return_value = True
            c = NebulaClient("h", 9669, "u", "p")
            assert c.init_pool() is True

    def test_init_pool_failure(self):
        from modules.nebula_client import NebulaClient
        with patch("modules.nebula_client.ConnectionPool") as m:
            m.return_value.init.return_value = False
            c = NebulaClient("h", 9669, "u", "p")
            assert c.init_pool() is False

    def test_session_defaults(self):
        from modules.nebula_client import NebulaClient
        with patch("modules.nebula_client.ConnectionPool") as m:
            m.return_value.init.return_value = True
            mock_sess = MagicMock()
            m.return_value.get_session.return_value = mock_sess
            c = NebulaClient("h", 9669, "user", "pass")
            c.init_pool()
            with c.session() as _:
                pass
            m.return_value.get_session.assert_called_once_with("user", "pass")
