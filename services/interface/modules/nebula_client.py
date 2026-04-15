"""
NebulaGraph client — wraps nebula3-python with typed errors and safe SQL formatting.

Architecture:
- NebulaError: typed exception for Nebula-side errors (→ HTTP 400)
- RuntimeError (internal): network / pool errors (→ HTTP 500)
- _format_value: escape strings for nGQL, including backslash and double-quote
- fetch_vertex/fetch_edge: always add YIELD clause for NebulaGraph 3.x compatibility
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple

from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool

if TYPE_CHECKING:
    from nebula3.gclient.net.Session import Session

logger = logging.getLogger(__name__)


class NebulaError(Exception):
    """Raised when NebulaGraph returns an error (wrong space, syntax error, etc.)."""

    def __init__(self, msg: str, stmt: str = ""):
        super().__init__(msg)
        self.stmt = stmt


class NebulaClient:
    """Thread-safe NebulaGraph client backed by a connection pool."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        pool_size: int = 20,
    ):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._pool_size = pool_size
        self._pool: ConnectionPool | None = None
        self._pool_config = Config()
        self._pool_config.max_connection_pool_size = pool_size

    # -------------------------------------------------------------------------
    # Pool lifecycle
    # -------------------------------------------------------------------------
    def init_pool(self) -> bool:
        """Initialise the connection pool. Call once at startup."""
        self._pool = ConnectionPool()
        ok = self._pool.init(
            [(self._host, self._port)],
            self._pool_config,
        )
        if not ok:
            logger.error("nebula_pool_init_failed host=%s port=%s", self._host, self._port)
            self._pool = None
            return False
        logger.info("nebula_pool_initialised", host=self._host, port=self._port)
        return True

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None
            logger.info("nebula_pool_closed")

    @contextmanager
    def session(self):
        """Borrow a session from the pool (preferred for production)."""
        if self._pool is None:
            raise RuntimeError("Nebula pool not initialised — call init_pool() first")
        sess = self._pool.get_session(self._user, self._password)
        try:
            yield sess
        finally:
            sess.release()

    @contextmanager
    def session_with(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """Create a short-lived pool for credential override (testing / multi-tenant)."""
        h = host or self._host
        p = port or self._port
        u = user or self._user
        pw = password or self._password

        config = Config()
        config.max_connection_pool_size = 4
        pool = ConnectionPool()
        if not pool.init([(h, p)], config):
            pool.close()
            raise NebulaError(f"Cannot connect to NebulaGraph at {h}:{p}")
        sess = pool.get_session(u, pw)
        try:
            yield sess
        finally:
            sess.release()
            pool.close()

    # -------------------------------------------------------------------------
    # Low-level executor
    # -------------------------------------------------------------------------
    def _run(self, session, stmt: str):
        """Execute a statement, returning the response or raising NebulaError."""
        resp = session.execute(stmt)
        if not resp.is_succeeded():
            msg = resp.error_msg()
            raise NebulaError(msg, stmt=stmt)
        return resp

    # -------------------------------------------------------------------------
    # Space operations
    # -------------------------------------------------------------------------
    def create_space(
        self,
        session,
        name: str,
        vid_type: str,
        partition_num: int,
        replica_factor: int,
    ) -> None:
        stmt = (
            f"CREATE SPACE IF NOT EXISTS `{name}`("
            f"partition_num={partition_num}, "
            f"replica_factor={replica_factor}, "
            f"vid_type={vid_type});"
        )
        self._run(session, stmt)

    def drop_space(self, session, name: str) -> None:
        self._run(session, f"DROP SPACE IF EXISTS `{name}`;")

    def list_spaces(self, session) -> List[str]:
        resp = self._run(session, "SHOW SPACES;")
        names = []
        for row in resp.rows():
            vals = row.values
            if vals:
                v = vals[0]
                try:
                    names.append(v.as_string())
                except AttributeError:
                    # Fallback for wrapped Value objects
                    names.append(str(v).strip())
        return names

    # -------------------------------------------------------------------------
    # Tag operations
    # -------------------------------------------------------------------------
    def ensure_tag(
        self,
        session,
        space: str,
        tag: str,
        columns: Iterable[Tuple[str, str]],
    ) -> None:
        cols = ", ".join(f"`{name}` {ctype}" for name, ctype in columns)
        stmt = f"USE `{space}`; CREATE TAG IF NOT EXISTS `{tag}`({cols});"
        self._run(session, stmt)

    def drop_tag(self, session, space: str, tag: str) -> None:
        stmt = f"USE `{space}`; DROP TAG IF EXISTS `{tag}`;"
        self._run(session, stmt)

    def alter_tag_add(
        self,
        session,
        space: str,
        tag: str,
        columns: Iterable[Tuple[str, str]],
    ) -> None:
        cols = ", ".join(f"`{name}` {ctype}" for name, ctype in columns)
        stmt = f"USE `{space}`; ALTER TAG `{tag}` ADD ({cols});"
        self._run(session, stmt)

    # -------------------------------------------------------------------------
    # Edge type operations
    # -------------------------------------------------------------------------
    def ensure_edge(
        self,
        session,
        space: str,
        edge: str,
        columns: Iterable[Tuple[str, str]],
    ) -> None:
        cols = ", ".join(f"`{name}` {ctype}" for name, ctype in columns)
        stmt = f"USE `{space}`; CREATE EDGE IF NOT EXISTS `{edge}`({cols});"
        self._run(session, stmt)

    def drop_edge_type(self, session, space: str, edge: str) -> None:
        stmt = f"USE `{space}`; DROP EDGE IF EXISTS `{edge}`;"
        self._run(session, stmt)

    def alter_edge_add(
        self,
        session,
        space: str,
        edge: str,
        columns: Iterable[Tuple[str, str]],
    ) -> None:
        cols = ", ".join(f"`{name}` {ctype}" for name, ctype in columns)
        stmt = f"USE `{space}`; ALTER EDGE `{edge}` ADD ({cols});"
        self._run(session, stmt)

    # -------------------------------------------------------------------------
    # Vertex operations
    # -------------------------------------------------------------------------
    def insert_vertex(
        self,
        session,
        space: str,
        vid: str,
        tag: str,
        props: Dict[str, object],
    ) -> None:
        cols = ", ".join(f"`{k}`" for k in props)
        vals = ", ".join(self._format_value(v) for v in props.values())
        stmt = f'USE `{space}`; INSERT VERTEX `{tag}`({cols}) VALUES "{vid}":({vals});'
        self._run(session, stmt)

    def update_vertex(
        self,
        session,
        space: str,
        vid: str,
        tag: str,
        props: Dict[str, object],
    ) -> None:
        sets = ", ".join(f"`{k}`={self._format_value(v)}" for k, v in props.items())
        stmt = f'USE `{space}`; UPDATE VERTEX ON `{tag}` "{vid}" SET {sets};'
        self._run(session, stmt)

    def delete_vertex(
        self,
        session,
        space: str,
        vid: str,
        with_edges: bool = True,
    ) -> None:
        stmt = f'USE `{space}`; DELETE VERTEX "{vid}"{" WITH EDGE" if with_edges else ""};'
        self._run(session, stmt)

    def fetch_vertex(
        self,
        session,
        space: str,
        vid: str,
        tag: str | None = None,
    ):
        """Fetch vertex properties. Always adds YIELD clause for NebulaGraph 3.x."""
        on = f"`{tag}`" if tag else "*"
        stmt = f'USE `{space}`; FETCH PROP ON {on} "{vid}" YIELD VERTEX AS v;'
        return self._run(session, stmt)

    # -------------------------------------------------------------------------
    # Edge operations
    # -------------------------------------------------------------------------
    def insert_edge(
        self,
        session,
        space: str,
        src: str,
        dst: str,
        edge: str,
        props: Dict[str, object],
    ) -> None:
        cols = ", ".join(f"`{k}`" for k in props)
        vals = ", ".join(self._format_value(v) for v in props.values())
        stmt = f'USE `{space}`; INSERT EDGE `{edge}`({cols}) VALUES "{src}"->"{dst}":({vals});'
        self._run(session, stmt)

    def update_edge(
        self,
        session,
        space: str,
        src: str,
        dst: str,
        edge: str,
        props: Dict[str, object],
    ) -> None:
        sets = ", ".join(f"`{k}`={self._format_value(v)}" for k, v in props.items())
        stmt = f'USE `{space}`; UPDATE EDGE ON `{edge}` "{src}"->"{dst}" SET {sets};'
        self._run(session, stmt)

    def delete_edge(
        self,
        session,
        space: str,
        src: str,
        dst: str,
        edge: str,
    ) -> None:
        stmt = f'USE `{space}`; DELETE EDGE `{edge}` "{src}"->"{dst}";'
        self._run(session, stmt)

    def fetch_edge(
        self,
        session,
        space: str,
        src: str,
        dst: str,
        edge: str,
    ):
        """Fetch edge properties. Always adds YIELD clause for NebulaGraph 3.x."""
        stmt = f'USE `{space}`; FETCH PROP ON `{edge}` "{src}"->"{dst}" YIELD EDGE AS e;'
        return self._run(session, stmt)

    # -------------------------------------------------------------------------
    # Raw query
    # -------------------------------------------------------------------------
    def query(self, session, space: str, nql: str):
        stmt = f"USE `{space}`; {nql}"
        return self._run(session, stmt)

    # -------------------------------------------------------------------------
    # Value formatting
    # -------------------------------------------------------------------------
    @staticmethod
    def _format_value(value) -> str:
        """Format a Python value as a safe nGQL literal."""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        # Escape backslash first, then double-quote (order matters)
        s = str(value)
        s = s.replace("\\", "\\\\")   # literal backslash → \\
        s = s.replace('"', '\\"')      # double-quote → \"
        return f'"{s}"'


# -------------------------------------------------------------------------
# Module-level singleton
# -------------------------------------------------------------------------
_client: NebulaClient | None = None


def get_client() -> NebulaClient:
    """Return the singleton NebulaClient instance (lazy init)."""
    global _client
    if _client is None:
        from interface.config import get_settings
        _client = NebulaClient.from_env()
    return _client
