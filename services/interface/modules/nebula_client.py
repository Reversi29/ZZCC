import logging
from contextlib import contextmanager
from typing import Dict, Iterable, Optional, Tuple

from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool


logger = logging.getLogger(__name__)


class NebulaClient:
    """Thin wrapper over nebula3-python for space and schema ops."""

    def __init__(self, host: str, port: int, user: str, password: str, pool_size: int = 10):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._pool = ConnectionPool()
        self._pool_size = pool_size
        self._initialized = False

    def init_pool(self) -> bool:
        config = Config()
        config.max_connection_pool_size = self._pool_size
        if not self._pool.init([(self._host, self._port)], config):
            logger.warning("Failed to init Nebula connection pool (host=%s, port=%s)", self._host, self._port)
            self._initialized = False
            return False
        self._initialized = True
        return True

    def close(self) -> None:
        self._pool.close()

    @contextmanager
    def session(self):
        """Session using the default configured host/port/user/password."""
        yield from self.session_with()

    @contextmanager
    def session_with(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """Session using provided credentials (falls back to defaults). Creates a short-lived pool."""
        h = host or self._host
        p = port or self._port
        u = user or self._user
        pw = password or self._password

        config = Config()
        config.max_connection_pool_size = 4
        pool = ConnectionPool()
        if not pool.init([(h, p)], config):
            raise RuntimeError(f"Failed to init Nebula pool for {h}:{p}")
        sess = pool.get_session(u, pw)
        try:
            yield sess
        finally:
            sess.release()
            pool.close()

    @staticmethod
    def _run(session, stmt: str):
        resp = session.execute(stmt)
        if not resp.is_succeeded():
            raise RuntimeError(f"Nebula error: {resp.error_msg()}, stmt: {stmt}")
        return resp

    def create_space(self, session, name: str, vid_type: str, partition_num: int, replica_factor: int) -> None:
        stmt = (
            f"CREATE SPACE IF NOT EXISTS `{name}`("
            f"partition_num={partition_num}, replica_factor={replica_factor}, vid_type={vid_type});"
        )
        self._run(session, stmt)

    def drop_space(self, session, name: str) -> None:
        self._run(session, f"DROP SPACE IF EXISTS `{name}`;")

    def alter_space(
        self,
        session,
        name: str,
        partition_num: Optional[int] = None,
        replica_factor: Optional[int] = None,
        vid_type: Optional[str] = None,
    ) -> None:
        parts = []
        if partition_num is not None:
            parts.append(f"partition_num = {partition_num}")
        if replica_factor is not None:
            parts.append(f"replica_factor = {replica_factor}")
        if vid_type is not None:
            parts.append(f"vid_type = {vid_type}")
        if not parts:
            return
        stmt = f"ALTER SPACE `{name}` {', '.join(parts)};"
        self._run(session, stmt)

    def list_spaces(self, session) -> Dict[str, Dict[str, object]]:
        resp = self._run(session, "SHOW SPACES;")
        spaces = {}
        for row in resp.rows():
            values = row.values
            if values:
                v = values[0]
                try:
                    name = v.as_string()
                except AttributeError:
                    name = str(v)
                spaces[name] = {"name": name}
        return spaces

    def ensure_tag(self, session, space: str, tag: str, columns: Iterable[Tuple[str, str]]):
        cols = ", ".join(f"`{name}` {ctype}" for name, ctype in columns)
        stmt = f"USE `{space}`; CREATE TAG IF NOT EXISTS `{tag}`({cols});"
        self._run(session, stmt)

    def ensure_edge(self, session, space: str, edge: str, columns: Iterable[Tuple[str, str]]):
        cols = ", ".join(f"`{name}` {ctype}" for name, ctype in columns)
        stmt = f"USE `{space}`; CREATE EDGE IF NOT EXISTS `{edge}`({cols});"
        self._run(session, stmt)

    def drop_tag(self, session, space: str, tag: str):
        stmt = f"USE `{space}`; DROP TAG IF EXISTS `{tag}`;"
        self._run(session, stmt)

    def drop_edge_type(self, session, space: str, edge: str):
        stmt = f"USE `{space}`; DROP EDGE IF EXISTS `{edge}`;"
        self._run(session, stmt)

    def alter_tag_add(self, session, space: str, tag: str, columns: Iterable[Tuple[str, str]]):
        cols = ", ".join(f"`{name}` {ctype}" for name, ctype in columns)
        stmt = f"USE `{space}`; ALTER TAG `{tag}` ADD ({cols});"
        self._run(session, stmt)

    def alter_edge_add(self, session, space: str, edge: str, columns: Iterable[Tuple[str, str]]):
        cols = ", ".join(f"`{name}` {ctype}" for name, ctype in columns)
        stmt = f"USE `{space}`; ALTER EDGE `{edge}` ADD ({cols});"
        self._run(session, stmt)

    def insert_vertex(self, session, space: str, vid: str, tag: str, props: Dict[str, object]):
        cols = ", ".join(f"`{k}`" for k in props.keys())
        vals = ", ".join(self._format_value(v) for v in props.values())
        stmt = f"USE `{space}`; INSERT VERTEX `{tag}`({cols}) VALUES \"{vid}\":({vals});"
        self._run(session, stmt)

    def update_vertex(self, session, space: str, vid: str, tag: str, props: Dict[str, object]):
        sets = ", ".join(f"`{k}`={self._format_value(v)}" for k, v in props.items())
        stmt = f"USE `{space}`; UPDATE VERTEX ON `{tag}` \"{vid}\" SET {sets};"
        self._run(session, stmt)

    def delete_vertex(self, session, space: str, vid: str, with_edges: bool = True):
        stmt = f"USE `{space}`; DELETE VERTEX \"{vid}\"{' WITH EDGE' if with_edges else ''};"
        self._run(session, stmt)

    def fetch_vertex(self, session, space: str, vid: str, tag: Optional[str] = None):
        on = f"`{tag}`" if tag else "*"
        stmt = f"USE `{space}`; FETCH PROP ON {on} \"{vid}\";"
        return self._run(session, stmt)

    def insert_edge(self, session, space: str, src: str, dst: str, edge: str, props: Dict[str, object]):
        cols = ", ".join(f"`{k}`" for k in props.keys())
        vals = ", ".join(self._format_value(v) for v in props.values())
        stmt = f"USE `{space}`; INSERT EDGE `{edge}`({cols}) VALUES \"{src}\"->\"{dst}\":({vals});"
        self._run(session, stmt)

    def update_edge(self, session, space: str, src: str, dst: str, edge: str, props: Dict[str, object]):
        sets = ", ".join(f"`{k}`={self._format_value(v)}" for k, v in props.items())
        stmt = f"USE `{space}`; UPDATE EDGE ON `{edge}` \"{src}\"->\"{dst}\" SET {sets};"
        self._run(session, stmt)

    def delete_edge(self, session, space: str, src: str, dst: str, edge: str):
        stmt = f"USE `{space}`; DELETE EDGE `{edge}` \"{src}\"->\"{dst}\";"
        self._run(session, stmt)

    def fetch_edge(self, session, space: str, src: str, dst: str, edge: str):
        stmt = f"USE `{space}`; FETCH PROP ON `{edge}` \"{src}\"->\"{dst}\";"
        return self._run(session, stmt)

    def query(self, session, space: str, nql: str):
        stmt = f"USE `{space}`; {nql}"
        return self._run(session, stmt)

    @staticmethod
    def _format_value(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        # Escape double quotes inside string values without backslash in f-string expression
        s = str(value).replace('"', '\\"')
        return f'"{s}"'
