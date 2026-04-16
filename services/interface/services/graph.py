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
            obj[col] = _unwrap_value(v)
        out.append(obj)
    return out


def _unwrap_value(v) -> Any:
    """Recursively unwrap a NebulaGraph Value into a plain Python object."""
    # nebula3-python thrift Union: v.field is type tag, v.__dict__['value'] holds raw data
    # field IDs: nVal=1, bVal=2, iVal=3, fVal=4, sVal=5, dVal=6, tVal=7, dtVal=8,
    #            vVal=9, eVal=10, pVal=11, lVal=12, mVal=13, uVal=14, gVal=15, ggVal=16, duVal=17
    _FIELD_NULL = 1
    _FIELD_BOOL = 2
    _FIELD_INT = 3
    _FIELD_FLOAT = 4
    _FIELD_STRING = 5
    _FIELD_DATE = 6
    _FIELD_TIME = 7
    _FIELD_DATETIME = 8
    _FIELD_VERTEX = 9
    _FIELD_EDGE = 10
    _FIELD_PATH = 11
    _FIELD_LIST = 12
    _FIELD_MAP = 13
    _FIELD_SET = 14

    raw = v.__dict__ if hasattr(v, '__dict__') else {}
    field = raw.get('field')
    value = raw.get('value')

    # Primary: direct field+value lookup (all nebula3-python Value types)
    if field is not None and value is not None:
        if field == _FIELD_NULL:
            return None
        if field == _FIELD_BOOL:
            return bool(value)
        if field == _FIELD_INT:
            return int(value)
        if field == _FIELD_FLOAT:
            return float(value)
        if field == _FIELD_STRING:
            return value.decode() if isinstance(value, bytes) else str(value)
        if field == _FIELD_DATE:
            return str(value) if value else None
        if field == _FIELD_TIME:
            return str(value) if value else None
        if field == _FIELD_DATETIME:
            return str(value) if value else None

        if field == _FIELD_VERTEX:
            try:
                vtx = v.value  # Value.v -> Vertex
                vid_raw = vtx.__dict__.get('vid')
                tags_list = vtx.__dict__.get('tags', [])
                vid = _unwrap_value(vid_raw) if vid_raw is not None else str(vid_raw)
                tags = {}
                for tag in tags_list:
                    key = tag.name.decode() if isinstance(tag.name, bytes) else str(tag.name)
                    props = {}
                    if hasattr(tag, 'props') and tag.props:
                        for k, pv in tag.props.items():
                            k_str = k.decode() if isinstance(k, bytes) else str(k)
                            props[k_str] = _unwrap_value(pv)
                    tags[key] = props
                return {"vid": vid, "tags": tags}
            except Exception:
                return str(v)
        if field == _FIELD_EDGE:
            try:
                edge_obj = v.value  # Value.e -> Edge
                src_raw = edge_obj.__dict__.get('src')
                dst_raw = edge_obj.__dict__.get('dst')
                type_ = edge_obj.__dict__.get('type', 0)
                rank = edge_obj.__dict__.get('ranking', 0)
                props_data = edge_obj.__dict__.get('props', {})
                name_raw = edge_obj.__dict__.get('name', b'')
                edge_name = name_raw.decode() if isinstance(name_raw, bytes) else str(name_raw)
                # type > 0 means outgoing, < 0 means incoming
                if type_ < 0:
                    src, dst = _unwrap_value(dst_raw), _unwrap_value(src_raw)
                else:
                    src, dst = _unwrap_value(src_raw), _unwrap_value(dst_raw)
                return {
                    "src": src, "dst": dst, "edge": edge_name, "rank": rank,
                    "props": {
                        k.decode() if isinstance(k, bytes) else k: _unwrap_value(pv)
                        for k, pv in props_data.items()
                    }
                }
            except Exception:
                return str(v)
        if field == _FIELD_LIST:
            try:
                return [_unwrap_value(item) for item in v.as_list()]
            except Exception:
                return str(v)
        if field == _FIELD_MAP:
            try:
                m = v.as_map()
                return {
                    k.decode() if isinstance(k, bytes) else k: _unwrap_value(val)
                    for k, val in m.items()
                }
            except Exception:
                return str(v)
        if field == _FIELD_SET:
            try:
                return [_unwrap_value(item) for item in v.as_set()]
            except Exception:
                return str(v)
        if field == _FIELD_PATH:
            try:
                return {"path": str(v.as_path())}
            except Exception:
                return str(v)

    # Fallback: getter methods (for non-field-based Values)
    try:
        getters = [
            ('get_sVal', lambda x: x.decode() if isinstance(x, bytes) else str(x)),
            ('get_iVal', int),
            ('get_fVal', float),
            ('get_bVal', bool),
            ('get_lVal', list),
            ('get_mVal', dict),
        ]
        for getter, decoder in getters:
            if hasattr(v, getter):
                try:
                    result = getattr(v, getter)()
                    if result is not None and result is not False:
                        return decoder(result)
                except (AssertionError, AttributeError, TypeError):
                    pass
    except Exception:
        pass

    return str(v)

def alter_tag(client: NebulaClient, sess, space: str, tag: str, columns: List[Tuple[str, str]]) -> None:
    client.alter_tag_add(sess, space=space, tag=tag, columns=columns)
    _log.info("tag_altered", space=space, tag=tag)


def alter_edge_type(client: NebulaClient, sess, space: str, edge: str, columns: List[Tuple[str, str]]) -> None:
    client.alter_edge_add(sess, space=space, edge=edge, columns=columns)
    _log.info("edge_altered", space=space, edge=edge)

