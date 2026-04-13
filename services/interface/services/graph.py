"""
Graph service — thin wrapper around NebulaClient.
Adds: logging, SpaceNotFound retry, error translation.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from tenacity import retry, stop_after_attempt, wait_fixed

from modules.nebula_client import NebulaClient, NebulaError

if TYPE_CHECKING:
    pass

_log = logging.getLogger(__name__)
_MAX_RETRIES = 5
_RETRY_WAIT = 2.0  # seconds


def run_with_retry(client: NebulaClient, sess, stmt: str) -> Any:
    """Execute nGQL with SpaceNotFound retry."""
    attempt = 0
    while attempt < _MAX_RETRIES:
        try:
            return client._run(sess, stmt)
        except NebulaError as exc:
            if "SpaceNotFound" in str(exc) and attempt < _MAX_RETRIES - 1:
                attempt += 1
                _log.warning("space_not_found_retry", attempt=attempt, max=_MAX_RETRIES, stmt=stmt[:80])
                time.sleep(_RETRY_WAIT)
                continue
            raise


def create_space(client: NebulaClient, sess, name: str, partition_num: int = 3, replica_factor: int = 1, vid_type: str = "FIXED_STRING(64)") -> None:
    client.create_space(sess, name=name, vid_type=vid_type, partition_num=partition_num, replica_factor=replica_factor)
    _log.info("space_created", space=name)


def wait_space(client: NebulaClient, sess, space: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            client._run(sess, f"USE `{space}`; YIELD 1;")
            _log.info("space_ready", space=space)
            return
        except NebulaError:
            time.sleep(1)
    raise NebulaError(f"Space '{space}' did not become ready within {timeout}s")


def drop_space(client: NebulaClient, sess, name: str) -> None:
    client.drop_space(sess, name)
    _log.info("space_dropped", space=name)


def list_spaces(client: NebulaClient, sess) -> List[Dict[str, Any]]:
    resp = run_with_retry(client, sess, "SHOW SPACES;")
    return _rows_to_dicts(resp)


def create_tag(client: NebulaClient, sess, space: str, tag: str, columns: List[Tuple[str, str]]) -> None:
    client.ensure_tag(sess, space=space, tag=tag, columns=columns)
    _log.info("tag_created", space=space, tag=tag)


def drop_tag(client: NebulaClient, sess, space: str, tag: str) -> None:
    client.drop_tag(sess, space=space, tag=tag)
    _log.info("tag_dropped", space=space, tag=tag)


def list_tags(client: NebulaClient, sess, space: str) -> List[Dict[str, Any]]:
    resp = run_with_retry(client, sess, f"USE `{space}`; SHOW TAGS;")
    return _rows_to_dicts(resp)


def create_edge_type(client: NebulaClient, sess, space: str, edge: str, columns: List[Tuple[str, str]]) -> None:
    client.ensure_edge(sess, space=space, edge=edge, columns=columns)
    _log.info("edge_created", space=space, edge=edge)


def drop_edge_type(client: NebulaClient, sess, space: str, edge: str) -> None:
    client.drop_edge_type(sess, space=space, edge=edge)
    _log.info("edge_dropped", space=space, edge=edge)


def list_edge_types(client: NebulaClient, sess, space: str) -> List[Dict[str, Any]]:
    resp = run_with_retry(client, sess, f"USE `{space}`; SHOW EDGES;")
    return _rows_to_dicts(resp)


def insert_vertex(client: NebulaClient, sess, space: str, vid: str, tag: str, props: Dict[str, Any]) -> None:
    client.insert_vertex(sess, space=space, vid=vid, tag=tag, props=props)
    _log.info("vertex_inserted", space=space, vid=vid, tag=tag)


def delete_vertex(client: NebulaClient, sess, space: str, vid: str, with_edges: bool = True) -> None:
    client.delete_vertex(sess, space=space, vid=vid, with_edges=with_edges)
    _log.info("vertex_deleted", space=space, vid=vid, with_edges=with_edges)


def fetch_vertex(client: NebulaClient, sess, space: str, vid: str, tag: str | None = None) -> List[Dict[str, Any]]:
    resp = client.fetch_vertex(sess, space=space, vid=vid, tag=tag)
    return _rows_to_dicts(resp)


def insert_edge(client: NebulaClient, sess, space: str, src: str, dst: str, edge: str, props: Dict[str, Any]) -> None:
    client.insert_edge(sess, space=space, src=src, dst=dst, edge=edge, props=props)
    _log.info("edge_inserted", space=space, edge=edge, src=src, dst=dst)


def delete_edge(client: NebulaClient, sess, space: str, src: str, dst: str, edge: str) -> None:
    client.delete_edge(sess, space=space, src=src, dst=dst, edge=edge)
    _log.info("edge_deleted", space=space, edge=edge, src=src, dst=dst)


def fetch_edge(client: NebulaClient, sess, space: str, src: str, dst: str, edge: str) -> List[Dict[str, Any]]:
    resp = client.fetch_edge(sess, space=space, src=src, dst=dst, edge=edge)
    return _rows_to_dicts(resp)


def run_query(client: NebulaClient, sess, space: str, q: str) -> List[Dict[str, Any]]:
    resp = run_with_retry(client, sess, f"USE `{space}`; {q}")
    return _rows_to_dicts(resp)


def _rows_to_dicts(resp) -> List[Dict[str, Any]]:
    if not resp.rows():
        return []
    keys = list(resp.keys())
    out = []
    for row in resp.rows():
        obj = {}
        for idx, col in enumerate(keys):
            v = row.values[idx]
            try:
                if v.is_string():
                    obj[col] = v.as_string()
                elif v.is_int():
                    obj[col] = v.as_int()
                elif v.is_double():
                    obj[col] = v.as_double()
                elif v.is_bool():
                    obj[col] = v.as_bool()
                else:
                    obj[col] = str(v)
            except AttributeError:
                obj[col] = str(v)
        out.append(obj)
    return out

def alter_tag(client: NebulaClient, sess, space: str, tag: str, columns: List[Tuple[str, str]]) -> None:
    client.alter_tag_add(sess, space=space, tag=tag, columns=columns)
    _log.info("tag_altered", space=space, tag=tag)


def alter_edge_type(client: NebulaClient, sess, space: str, edge: str, columns: List[Tuple[str, str]]) -> None:
    client.alter_edge_add(sess, space=space, edge=edge, columns=columns)
    _log.info("edge_altered", space=space, edge=edge)

