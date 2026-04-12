"""
Unit tests for NebulaClient (modules/nebula_client.py).

Tests cover:
- Connection pool init / close
- Space CRUD SQL generation
- Tag / edge schema ops
- Vertex / edge insert / fetch / update / delete
- Query execution
- Value formatting (_format_value)

Run:
    pytest test_nebula_client.py -v
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

INTERFACE_DIR = os.path.join(os.path.dirname(__file__), "..", "interface")
if INTERFACE_DIR not in sys.path:
    sys.path.insert(0, INTERFACE_DIR)

from modules.nebula_client import NebulaClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """NebulaClient instance without connecting to real server."""
    c = NebulaClient(
        host="127.0.0.1",
        port=9669,
        user="root",
        password="nebula",
    )
    return c


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------

class TestFormatValue:
    def test_bool_true(self, client):
        assert client._format_value(True) == "true"

    def test_bool_false(self, client):
        assert client._format_value(False) == "false"

    def test_int(self, client):
        assert client._format_value(42) == "42"

    def test_negative_int(self, client):
        assert client._format_value(-10) == "-10"

    def test_float(self, client):
        assert client._format_value(3.14) == "3.14"

    def test_string_plain(self, client):
        assert client._format_value("Alice") == '"Alice"'

    def test_string_with_quotes_escaped(self, client):
        assert client._format_value('say "hi"') == r'"say \"hi\""'

    def test_string_with_backslash(self, client):
        """Backslashes are preserved; only double-quotes are escaped."""
        # Input: Python string with literal backslashes: path\to\file
        # str() returns it as-is, then the value gets wrapped in quotes
        val = "path\\to\\file"
        result = client._format_value(val)
        # Output is the string wrapped in double-quotes, backslashes unchanged
        assert result == '"path\\to\\file"'


# ---------------------------------------------------------------------------
# Space operations
# ---------------------------------------------------------------------------

class TestSpaceOps:
    def test_create_space_sql(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.create_space(sess, name="test_space", vid_type="FIXED_STRING(64)",
                            partition_num=10, replica_factor=1)
        sess.execute.assert_called_once()
        call_args = sess.execute.call_args[0][0]
        assert "CREATE SPACE IF NOT EXISTS `test_space`" in call_args
        assert "partition_num=10" in call_args
        assert "replica_factor=1" in call_args
        assert "vid_type=FIXED_STRING(64)" in call_args

    def test_drop_space_sql(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.drop_space(sess, name="test_space")
        sess.execute.assert_called_once()
        assert "DROP SPACE IF EXISTS `test_space`" in sess.execute.call_args[0][0]

    def test_list_spaces(self, client):
        mock_row = MagicMock()
        mock_row.values = [MagicMock(as_string=MagicMock(return_value="space1"))]
        resp = MagicMock()
        resp.is_succeeded.return_value = True
        resp.rows.return_value = [mock_row]
        sess = MagicMock()
        sess.execute = MagicMock(return_value=resp)
        result = client.list_spaces(sess)
        assert "space1" in result
        assert result["space1"]["name"] == "space1"

    def test_list_spaces_empty(self, client):
        resp = MagicMock()
        resp.is_succeeded.return_value = True
        resp.rows.return_value = []
        sess = MagicMock()
        sess.execute = MagicMock(return_value=resp)
        result = client.list_spaces(sess)
        assert result == {}

    def test_alter_space_all_fields(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.alter_space(sess, name="test_space",
                           partition_num=20, replica_factor=2, vid_type="INT64")
        call_args = sess.execute.call_args[0][0]
        assert "ALTER SPACE `test_space`" in call_args
        assert "partition_num = 20" in call_args
        assert "replica_factor = 2" in call_args
        assert "vid_type = INT64" in call_args

    def test_alter_space_no_fields(self, client):
        sess = MagicMock()
        client.alter_space(sess, name="test_space")
        sess.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Tag operations
# ---------------------------------------------------------------------------

class TestTagOps:
    def test_ensure_tag(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.ensure_tag(sess, space="s", tag="Person", columns=[("name", "string")])
        call_args = sess.execute.call_args[0][0]
        assert "CREATE TAG IF NOT EXISTS `Person`" in call_args
        assert "`name` string" in call_args

    def test_drop_tag(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.drop_tag(sess, space="s", tag="Person")
        assert "DROP TAG IF EXISTS `Person`" in sess.execute.call_args[0][0]

    def test_alter_tag_add(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.alter_tag_add(sess, space="s", tag="Person",
                             columns=[("age", "int"), ("score", "double")])
        call_args = sess.execute.call_args[0][0]
        assert "ALTER TAG `Person` ADD" in call_args
        assert "`age` int" in call_args
        assert "`score` double" in call_args


# ---------------------------------------------------------------------------
# Edge operations
# ---------------------------------------------------------------------------

class TestEdgeOps:
    def test_ensure_edge(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.ensure_edge(sess, space="s", edge="KNOWS", columns=[("since", "int")])
        call_args = sess.execute.call_args[0][0]
        assert "CREATE EDGE IF NOT EXISTS `KNOWS`" in call_args
        assert "`since` int" in call_args

    def test_drop_edge_type(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.drop_edge_type(sess, space="s", edge="KNOWS")
        assert "DROP EDGE IF EXISTS `KNOWS`" in sess.execute.call_args[0][0]

    def test_alter_edge_add(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.alter_edge_add(sess, space="s", edge="KNOWS", columns=[("weight", "double")])
        call_args = sess.execute.call_args[0][0]
        assert "ALTER EDGE `KNOWS` ADD" in call_args
        assert "`weight` double" in call_args


# ---------------------------------------------------------------------------
# Vertex operations
# ---------------------------------------------------------------------------

class TestVertexOps:
    def test_insert_vertex_single_prop(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.insert_vertex(sess, space="s", vid="alice", tag="Person", props={"name": "Alice"})
        call_args = sess.execute.call_args[0][0]
        assert "INSERT VERTEX `Person`" in call_args
        assert "`name`" in call_args
        assert '"alice"' in call_args
        assert '"Alice"' in call_args

    def test_insert_vertex_multiple_props(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.insert_vertex(sess, space="s", vid="alice", tag="Person",
                            props={"name": "Alice", "age": 30, "active": True})
        call_args = sess.execute.call_args[0][0]
        assert '"Alice"' in call_args
        assert "30" in call_args
        assert "true" in call_args  # bool formatted as true/false

    def test_update_vertex(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.update_vertex(sess, space="s", vid="alice", tag="Person", props={"age": 31})
        call_args = sess.execute.call_args[0][0]
        assert "UPDATE VERTEX ON `Person`" in call_args
        assert "`age`" in call_args

    def test_delete_vertex_with_edges(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.delete_vertex(sess, space="s", vid="alice", with_edges=True)
        call_args = sess.execute.call_args[0][0]
        assert "DELETE VERTEX" in call_args
        assert "WITH EDGE" in call_args

    def test_delete_vertex_no_edges(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.delete_vertex(sess, space="s", vid="alice", with_edges=False)
        call_args = sess.execute.call_args[0][0]
        assert "DELETE VERTEX" in call_args
        assert "WITH EDGE" not in call_args

    def test_fetch_vertex_with_tag(self, client):
        sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.is_succeeded.return_value = True
        sess.execute = MagicMock(return_value=mock_resp)
        resp = client.fetch_vertex(sess, space="s", vid="alice", tag="Person")
        call_args = sess.execute.call_args[0][0]
        assert "FETCH PROP ON `Person`" in call_args
        assert '"alice"' in call_args
        assert resp.is_succeeded()

    def test_fetch_vertex_all_tags(self, client):
        sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.is_succeeded.return_value = True
        sess.execute = MagicMock(return_value=mock_resp)
        client.fetch_vertex(sess, space="s", vid="alice", tag=None)
        call_args = sess.execute.call_args[0][0]
        assert "FETCH PROP ON *" in call_args


# ---------------------------------------------------------------------------
# Edge data operations
# ---------------------------------------------------------------------------

class TestEdgeDataOps:
    def test_insert_edge(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.insert_edge(sess, space="s", src="alice", dst="bob",
                           edge="KNOWS", props={"since": 2020})
        call_args = sess.execute.call_args[0][0]
        assert "INSERT EDGE `KNOWS`" in call_args
        assert '"alice"' in call_args
        assert '"bob"' in call_args
        assert "2020" in call_args

    def test_update_edge(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.update_edge(sess, space="s", src="alice", dst="bob",
                           edge="KNOWS", props={"since": 2021})
        call_args = sess.execute.call_args[0][0]
        assert "UPDATE EDGE ON `KNOWS`" in call_args
        assert "`since`" in call_args

    def test_delete_edge(self, client):
        sess = MagicMock()
        sess.execute = MagicMock(return_value=MagicMock(is_succeeded=MagicMock(return_value=True)))
        client.delete_edge(sess, space="s", src="alice", dst="bob", edge="KNOWS")
        call_args = sess.execute.call_args[0][0]
        assert "DELETE EDGE `KNOWS`" in call_args
        assert '"alice"' in call_args
        assert '"bob"' in call_args

    def test_fetch_edge(self, client):
        sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.is_succeeded.return_value = True
        sess.execute = MagicMock(return_value=mock_resp)
        client.fetch_edge(sess, space="s", src="alice", dst="bob", edge="KNOWS")
        call_args = sess.execute.call_args[0][0]
        assert "FETCH PROP ON `KNOWS`" in call_args
        assert '"alice"' in call_args
        assert '"bob"' in call_args


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

class TestQuery:
    def test_query(self, client):
        sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.is_succeeded.return_value = True
        sess.execute = MagicMock(return_value=mock_resp)
        resp = client.query(sess, space="s", nql="MATCH (n) RETURN n LIMIT 10")
        assert resp.is_succeeded()

    def test_query_failure_raises(self, client):
        sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.is_succeeded.return_value = False
        mock_resp.error_msg.return_value = "Space not found"
        sess.execute = MagicMock(return_value=mock_resp)
        with pytest.raises(RuntimeError) as exc_info:
            client.query(sess, space="s", nql="SHOW SPACES")
        assert "Space not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class TestSessionManagement:
    def test_session_uses_defaults(self, client):
        with patch("modules.nebula_client.ConnectionPool") as MockPool:
            mock_pool_instance = MagicMock()
            MockPool.return_value = mock_pool_instance
            mock_pool_instance.init.return_value = True
            mock_sess = MagicMock()
            mock_pool_instance.get_session.return_value = mock_sess
            with client.session() as sess:
                pass
            mock_pool_instance.get_session.assert_called_once_with("root", "nebula")

    def test_session_with_override(self, client):
        with patch("modules.nebula_client.ConnectionPool") as MockPool:
            mock_pool_instance = MagicMock()
            MockPool.return_value = mock_pool_instance
            mock_pool_instance.init.return_value = True
            mock_sess = MagicMock()
            mock_pool_instance.get_session.return_value = mock_sess
            with client.session_with(host="10.0.0.1", user="admin", password="secret") as sess:
                pass
            mock_pool_instance.get_session.assert_called_once_with("admin", "secret")

    def test_init_pool_failure(self, client):
        # Patch the instance-level _pool attribute so no real network call is made
        mock_instance = MagicMock()
        mock_instance.init.return_value = False
        client._pool = mock_instance
        result = client.init_pool()
        assert result is False
        assert client._initialized is False

    def test_init_pool_success(self, client):
        # Patch the instance-level _pool attribute so no real network call is made
        mock_instance = MagicMock()
        mock_instance.init.return_value = True
        client._pool = mock_instance
        result = client.init_pool()
        assert result is True
        assert client._initialized is True
