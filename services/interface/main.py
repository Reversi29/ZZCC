import csv
import io
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
import re
from fastapi import Depends, FastAPI, HTTPException, Header, Body, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from modules.nebula_client import NebulaClient

NEBULA_HOST = "124.223.47.167"
NEBULA_PORT = 9669
NEBULA_USER = "root"
NEBULA_PASSWORD = "nebula"

client = NebulaClient(
    host=NEBULA_HOST,
    port=NEBULA_PORT,
    user=NEBULA_USER,
    password=NEBULA_PASSWORD,
)

app = FastAPI(title="Nebula Interface", version="1.0.0")

logger = logging.getLogger(__name__)


class SpaceCreate(BaseModel):
    name: str = Field(..., description="Space name")
    partition_num: int = Field(3, ge=1, description="Partition count")
    replica_factor: int = Field(1, ge=1, description="Replica factor")
    vid_type: str = Field("FIXED_STRING(64)", description="VID type, e.g. FIXED_STRING(64) or INT64")


class SpaceAlter(BaseModel):
    partition_num: Optional[int] = Field(None, ge=1)
    replica_factor: Optional[int] = Field(None, ge=1)
    vid_type: Optional[str] = None


class PropertyDef(BaseModel):
    name: str = Field(..., description="Property/column name")
    type: str = Field(..., description="Nebula data type, e.g. FIXED_STRING(64) or INT64")


class TagDef(BaseModel):
    name: str = Field(..., description="Tag (vertex type) name")
    properties: list[PropertyDef] = Field(default_factory=list, description="Columns for the tag")


class EdgeDef(BaseModel):
    name: str = Field(..., description="Edge type name")
    properties: list[PropertyDef] = Field(default_factory=list, description="Columns for the edge type")


class DeployRequest(BaseModel):
    space: str = Field(..., description="Space to create or reuse")
    partition_num: int = Field(3, ge=1, description="Partition count for the space")
    replica_factor: int = Field(1, ge=1, description="Replica factor for the space")
    vid_type: str = Field("FIXED_STRING(64)", description="VID type, e.g. FIXED_STRING(64) or INT64")
    tags: list[TagDef] = Field(default_factory=list, description="Tags (vertex types) to create")
    edges: list[EdgeDef] = Field(default_factory=list, description="Edge types to create")


class QueryResponse(BaseModel):
    message: str
    rows: list[dict] = Field(default_factory=list)


class VertexCreate(BaseModel):
    space: str
    tag: str
    vid: str
    props: Dict[str, Any] = Field(default_factory=dict)


class VertexUpdate(BaseModel):
    space: str
    tag: str
    vid: str
    props: Dict[str, Any]


class VertexDelete(BaseModel):
    space: str
    vid: str
    with_edges: bool = True


class EdgeCreate(BaseModel):
    space: str
    edge: str
    src: str
    dst: str
    props: Dict[str, Any] = Field(default_factory=dict)


class EdgeUpdate(BaseModel):
    space: str
    edge: str
    src: str
    dst: str
    props: Dict[str, Any]


class EdgeDelete(BaseModel):
    space: str
    edge: str
    src: str
    dst: str


class TagCreate(BaseModel):
    space: str
    tag: str
    properties: List[PropertyDef] = Field(default_factory=list)


class TagAlterAdd(BaseModel):
    space: str
    tag: str
    properties: List[PropertyDef]


class TagDrop(BaseModel):
    space: str
    tag: str


class EdgeTypeCreate(BaseModel):
    space: str
    edge: str
    properties: List[PropertyDef] = Field(default_factory=list)


class EdgeTypeAlterAdd(BaseModel):
    space: str
    edge: str
    properties: List[PropertyDef]


class EdgeTypeDrop(BaseModel):
    space: str
    edge: str


DEFAULT_DEPLOY_FILE = Path(__file__).with_name("deploy_defaults.json")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_default_deploy() -> DeployRequest:
    if not DEFAULT_DEPLOY_FILE.exists():
        raise RuntimeError(f"Default deploy file not found: {DEFAULT_DEPLOY_FILE}")
    with DEFAULT_DEPLOY_FILE.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return DeployRequest.parse_obj(data)


def _assert_identifier(name: str, kind: str) -> None:
    if not IDENTIFIER_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail=f"{kind} '{name}' 非法。Nebula 标识符必须匹配 ^[A-Za-z_][A-Za-z0-9_]*$，请使用字母、数字、下划线，并以字母或下划线开头。"
        )


def _assert_prop_keys(props: Dict[str, Any]) -> None:
    for k in props.keys():
        _assert_identifier(str(k), "属性名")


def _coerce_csv_value(raw: Optional[str]) -> Optional[Any]:
    if raw is None:
        return None
    s = raw.strip()
    if s == "":
        return None
    lower = s.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    try:
        if s.startswith("0") and len(s) > 1:
            raise ValueError
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def wait_for_space_ready(sess, space: str, timeout_sec: int = 180, interval_sec: int = 2) -> None:
    start = time.time()
    last_err: Optional[str] = None
    while True:
        try:
            # Directly test space usability; this avoids name-encoding mismatches in SHOW SPACES
            client.query(sess, space=space, nql="SHOW TAGS;")
            return
        except Exception as exc:  # pragma: no cover
            last_err = str(exc)

        if time.time() - start > timeout_sec:
            if last_err:
                raise RuntimeError(f"Space '{space}' not ready within {timeout_sec}s: {last_err}")
            raise RuntimeError(f"Space '{space}' not ready within {timeout_sec}s")
        time.sleep(interval_sec)


def get_session():
    with client.session() as sess:
        yield sess


def get_session_with_override(
    nebula_host: Optional[str] = Header(default=None, alias="X-Nebula-Host"),
    nebula_port: Optional[int] = Header(default=None, alias="X-Nebula-Port"),
    nebula_user: Optional[str] = Header(default=None, alias="X-Nebula-User"),
    nebula_password: Optional[str] = Header(default=None, alias="X-Nebula-Password"),
):
    with client.session_with(
        host=nebula_host,
        port=nebula_port,
        user=nebula_user,
        password=nebula_password,
    ) as sess:
        yield sess


@app.on_event("shutdown")
def shutdown():
    client.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/spaces")
def list_spaces(sess=Depends(get_session_with_override)):
    return client.list_spaces(sess)


@app.post("/spaces", status_code=201)
def create_space(payload: SpaceCreate, sess=Depends(get_session_with_override)):
    try:
        client.create_space(
            sess,
            name=payload.name,
            vid_type=payload.vid_type,
            partition_num=payload.partition_num,
            replica_factor=payload.replica_factor,
        )
        return {"created": payload.name}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/spaces/{name}")
def alter_space(name: str, payload: SpaceAlter, sess=Depends(get_session_with_override)):
    if payload.partition_num is None and payload.replica_factor is None and payload.vid_type is None:
        raise HTTPException(status_code=400, detail="No alter fields provided")
    try:
        client.alter_space(
            sess,
            name=name,
            partition_num=payload.partition_num,
            replica_factor=payload.replica_factor,
            vid_type=payload.vid_type,
        )
        return {"altered": name}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/spaces/{name}")
def drop_space(name: str, sess=Depends(get_session_with_override)):
    try:
        client.drop_space(sess, name)
        return {"dropped": name}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/query", response_model=QueryResponse)
def run_query(q: str, space: str, sess=Depends(get_session_with_override)):
    try:
        resp = client.query(sess, space=space, nql=q)
        rows = []
        if resp and resp.rows():
            col_names = resp.keys()
            for row in resp.rows():
                values = row.values
                row_obj = {}
                for idx, col in enumerate(col_names):
                    # Convert Nebula Value to python primitive/string
                    val = values[idx]
                    try:
                        if hasattr(val, "is_bool") and val.is_bool():
                            row_obj[col] = val.as_bool()
                        elif hasattr(val, "is_int") and val.is_int():
                            row_obj[col] = val.as_int()
                        elif hasattr(val, "is_double") and val.is_double():
                            row_obj[col] = val.as_double()
                        elif hasattr(val, "is_string") and val.is_string():
                            row_obj[col] = val.as_string()
                        else:
                            row_obj[col] = str(val)
                    except AttributeError:
                        row_obj[col] = str(val)
                rows.append(row_obj)

        return QueryResponse(message="ok", rows=rows)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/deploy")
def deploy(payload: Optional[DeployRequest] = Body(default=None), sess=Depends(get_session_with_override)):
    steps = []
    try:
        if payload is None:
            payload = load_default_deploy()

        # Nebula identifiers must be ASCII letters/digits/underscore
        _assert_identifier(payload.space, "空间名")
        for tag in payload.tags:
            _assert_identifier(tag.name, "标签名")
            for p in tag.properties:
                _assert_identifier(p.name, "属性名")
        for edge in payload.edges:
            _assert_identifier(edge.name, "边类型名")
            for p in edge.properties:
                _assert_identifier(p.name, "属性名")

        client.create_space(
            sess,
            name=payload.space,
            vid_type=payload.vid_type,
            partition_num=payload.partition_num,
            replica_factor=payload.replica_factor,
        )
        steps.append(f"space:{payload.space}")

        wait_for_space_ready(sess, payload.space)
        steps.append(f"space-ready:{payload.space}")

        for tag in payload.tags:
            cols = [(prop.name, prop.type) for prop in tag.properties]
            client.ensure_tag(sess, space=payload.space, tag=tag.name, columns=cols)
            steps.append(f"tag:{tag.name}")

        for edge in payload.edges:
            cols = [(prop.name, prop.type) for prop in edge.properties]
            client.ensure_edge(sess, space=payload.space, edge=edge.name, columns=cols)
            steps.append(f"edge:{edge.name}")

        return {"deployed": payload.space, "steps": steps}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Vertices
@app.post("/vertices")
def create_vertex(payload: VertexCreate, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.tag, "标签名")
        _assert_prop_keys(payload.props)
        client.insert_vertex(sess, space=payload.space, vid=payload.vid, tag=payload.tag, props=payload.props)
        return {"vertex": payload.vid, "tag": payload.tag, "created": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/vertices")
def update_vertex(payload: VertexUpdate, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.tag, "标签名")
        _assert_prop_keys(payload.props)
        client.update_vertex(sess, space=payload.space, vid=payload.vid, tag=payload.tag, props=payload.props)
        return {"vertex": payload.vid, "tag": payload.tag, "updated": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/vertices")
def delete_vertex(payload: VertexDelete, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        client.delete_vertex(sess, space=payload.space, vid=payload.vid, with_edges=payload.with_edges)
        return {"vertex": payload.vid, "deleted": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/vertices/{vid}")
def fetch_vertex(vid: str, space: str, tag: Optional[str] = None, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(space, "空间名")
        if tag:
            _assert_identifier(tag, "标签名")
        resp = client.fetch_vertex(sess, space=space, vid=vid, tag=tag)
        rows = []
        col_names = resp.keys()
        for row in resp.rows():
            values = row.values
            obj = {}
            for idx, col in enumerate(col_names):
                v = values[idx]
                obj[col] = str(v)
            rows.append(obj)
        return {"vertex": vid, "rows": rows}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Edges
@app.post("/edges")
def create_edge(payload: EdgeCreate, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.edge, "边类型名")
        _assert_prop_keys(payload.props)
        client.insert_edge(sess, space=payload.space, src=payload.src, dst=payload.dst, edge=payload.edge, props=payload.props)
        return {"edge": payload.edge, "src": payload.src, "dst": payload.dst, "created": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/edges")
def update_edge(payload: EdgeUpdate, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.edge, "边类型名")
        _assert_prop_keys(payload.props)
        client.update_edge(sess, space=payload.space, src=payload.src, dst=payload.dst, edge=payload.edge, props=payload.props)
        return {"edge": payload.edge, "src": payload.src, "dst": payload.dst, "updated": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/edges")
def delete_edge(payload: EdgeDelete, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.edge, "边类型名")
        client.delete_edge(sess, space=payload.space, src=payload.src, dst=payload.dst, edge=payload.edge)
        return {"edge": payload.edge, "src": payload.src, "dst": payload.dst, "deleted": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/edges")
def fetch_edge(space: str, edge: str, src: str, dst: str, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(space, "空间名")
        _assert_identifier(edge, "边类型名")
        resp = client.fetch_edge(sess, space=space, src=src, dst=dst, edge=edge)
        rows = []
        col_names = resp.keys()
        for row in resp.rows():
            values = row.values
            obj = {}
            for idx, col in enumerate(col_names):
                v = values[idx]
                obj[col] = str(v)
            rows.append(obj)
        return {"edge": edge, "src": src, "dst": dst, "rows": rows}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Tag (label) types
@app.get("/tags")
def list_tags(space: str, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(space, "空间名")
        resp = client.query(sess, space=space, nql="SHOW TAGS;")
        rows = []
        for row in resp.rows():
            vals = row.values
            rows.append({"name": str(vals[0])})
        return {"space": space, "tags": rows}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/tags")
def create_tag(payload: TagCreate, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.tag, "标签名")
        for p in payload.properties:
            _assert_identifier(p.name, "属性名")
        cols = [(p.name, p.type) for p in payload.properties]
        client.ensure_tag(sess, space=payload.space, tag=payload.tag, columns=cols)
        return {"tag": payload.tag, "created": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/tags")
def alter_tag_add(payload: TagAlterAdd, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.tag, "标签名")
        for p in payload.properties:
            _assert_identifier(p.name, "属性名")
        cols = [(p.name, p.type) for p in payload.properties]
        client.alter_tag_add(sess, space=payload.space, tag=payload.tag, columns=cols)
        return {"tag": payload.tag, "alter": "ADD", "count": len(cols)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/tags")
def drop_tag(payload: TagDrop, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.tag, "标签名")
        client.drop_tag(sess, space=payload.space, tag=payload.tag)
        return {"tag": payload.tag, "dropped": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Edge types
@app.get("/edge-types")
def list_edge_types(space: str, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(space, "空间名")
        resp = client.query(sess, space=space, nql="SHOW EDGES;")
        rows = []
        for row in resp.rows():
            vals = row.values
            rows.append({"name": str(vals[0])})
        return {"space": space, "edges": rows}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/edge-types")
def create_edge_type(payload: EdgeTypeCreate, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.edge, "边类型名")
        for p in payload.properties:
            _assert_identifier(p.name, "属性名")
        cols = [(p.name, p.type) for p in payload.properties]
        client.ensure_edge(sess, space=payload.space, edge=payload.edge, columns=cols)
        return {"edge": payload.edge, "created": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/edge-types")
def alter_edge_type_add(payload: EdgeTypeAlterAdd, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.edge, "边类型名")
        for p in payload.properties:
            _assert_identifier(p.name, "属性名")
        cols = [(p.name, p.type) for p in payload.properties]
        client.alter_edge_add(sess, space=payload.space, edge=payload.edge, columns=cols)
        return {"edge": payload.edge, "alter": "ADD", "count": len(cols)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/edge-types")
def drop_edge_type(payload: EdgeTypeDrop, sess=Depends(get_session_with_override)):
    try:
        _assert_identifier(payload.space, "空间名")
        _assert_identifier(payload.edge, "边类型名")
        client.drop_edge_type(sess, space=payload.space, edge=payload.edge)
        return {"edge": payload.edge, "dropped": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# CSV import
@app.post("/import/csv/vertices")
async def import_vertices_csv(
    space: str,
    tag: str,
    file: UploadFile = File(...),
    sess=Depends(get_session_with_override),
):
    try:
        _assert_identifier(space, "空间名")
        _assert_identifier(tag, "标签名")

        reader = csv.DictReader(io.TextIOWrapper(file.file, encoding="utf-8"))
        if not reader.fieldnames or "vid" not in reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV 首行必须包含列 vid")

        count = 0
        for row in reader:
            vid = row.get("vid")
            if vid is None or str(vid).strip() == "":
                continue
            props = {}
            for k, v in row.items():
                if k == "vid":
                    continue
                val = _coerce_csv_value(v)
                if val is None:
                    continue
                props[k] = val
            _assert_prop_keys(props)
            client.insert_vertex(sess, space=space, vid=str(vid), tag=tag, props=props)
            count += 1

        return {"space": space, "tag": tag, "imported": count}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/import/csv/edges")
async def import_edges_csv(
    space: str,
    edge: str,
    file: UploadFile = File(...),
    sess=Depends(get_session_with_override),
):
    try:
        _assert_identifier(space, "空间名")
        _assert_identifier(edge, "边类型名")

        reader = csv.DictReader(io.TextIOWrapper(file.file, encoding="utf-8"))
        if not reader.fieldnames or "src" not in reader.fieldnames or "dst" not in reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV 首行必须包含列 src,dst")

        count = 0
        for row in reader:
            src = row.get("src")
            dst = row.get("dst")
            if src is None or str(src).strip() == "" or dst is None or str(dst).strip() == "":
                continue
            props = {}
            for k, v in row.items():
                if k in {"src", "dst"}:
                    continue
                val = _coerce_csv_value(v)
                if val is None:
                    continue
                props[k] = val
            _assert_prop_keys(props)
            client.insert_edge(sess, space=space, src=str(src), dst=str(dst), edge=edge, props=props)
            count += 1

        return {"space": space, "edge": edge, "imported": count}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
