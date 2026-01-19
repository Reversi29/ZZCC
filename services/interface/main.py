import json
import logging
import time
from pathlib import Path
from typing import Optional
from fastapi import Depends, FastAPI, HTTPException, Header
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


DEFAULT_DEPLOY_FILE = Path(__file__).with_name("deploy_defaults.json")


def load_default_deploy() -> DeployRequest:
    if not DEFAULT_DEPLOY_FILE.exists():
        raise RuntimeError(f"Default deploy file not found: {DEFAULT_DEPLOY_FILE}")
    with DEFAULT_DEPLOY_FILE.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return DeployRequest.parse_obj(data)


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
                values = row.as_values()
                row_obj = {}
                for idx, col in enumerate(col_names):
                    # Convert Nebula Value to python primitive/string
                    val = values[idx]
                    if val.is_bool():
                        row_obj[col] = val.as_bool()
                    elif val.is_int():
                        row_obj[col] = val.as_int()
                    elif val.is_double():
                        row_obj[col] = val.as_double()
                    elif val.is_string():
                        row_obj[col] = val.as_string()
                    else:
                        row_obj[col] = str(val)
                rows.append(row_obj)

        return QueryResponse(message="ok", rows=rows)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/deploy")
def deploy(payload: Optional[DeployRequest] = None, sess=Depends(get_session_with_override)):
    steps = []
    try:
        if payload is None:
            payload = load_default_deploy()

        client.create_space(
            sess,
            name=payload.space,
            vid_type=payload.vid_type,
            partition_num=payload.partition_num,
            replica_factor=payload.replica_factor,
        )
        steps.append(f"space:{payload.space}")

        # Wait until space is visible to graphd/metad before issuing USE/DDL
        timeout_sec = 60
        interval_sec = 1
        start = time.time()
        while True:
            spaces = client.list_spaces(sess)
            if payload.space in spaces:
                break
            if time.time() - start > timeout_sec:
                raise RuntimeError(f"Space '{payload.space}' not ready within {timeout_sec}s")
            time.sleep(interval_sec)
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
