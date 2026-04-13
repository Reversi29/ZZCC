"""
Router: /api/v1/edges — actual edge data (INSERT / DELETE / FETCH).
Edge type schema is in routers/edge_types.py.
"""
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_client, get_session, require_api_key
from models.schemas import EdgeCreate, EdgeDelete, EdgeResp, check_identifier
from modules.nebula_client import NebulaError
from services.graph import delete_edge, fetch_edge, insert_edge

router = APIRouter(prefix="/edges", tags=["edges"])


@router.post("", response_model=EdgeResp, status_code=201)
async def insert_edge_endpoint(
    payload: EdgeCreate,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.edge, "边类型名")
    for k in payload.props:
        check_identifier(k, "属性名")
    try:
        insert_edge(
            get_client(), sess,
            space=payload.space, src=payload.src, dst=payload.dst,
            edge=payload.edge, props=payload.props,
        )
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {
        "edge": payload.edge,
        "src": payload.src,
        "dst": payload.dst,
    }}


@router.get("", response_model=EdgeResp)
async def fetch_edge_endpoint(
    space: str,
    edge: str,
    src: str,
    dst: str,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")
    try:
        rows = fetch_edge(get_client(), sess, space=space, src=src, dst=dst, edge=edge)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"edge": edge, "src": src, "dst": dst, "rows": rows}}


@router.delete("", response_model=EdgeResp)
async def delete_edge_endpoint(
    payload: EdgeDelete,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.edge, "边类型名")
    try:
        delete_edge(
            get_client(), sess,
            space=payload.space, src=payload.src,
            dst=payload.dst, edge=payload.edge,
        )
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {
        "edge": payload.edge,
        "src": payload.src,
        "dst": payload.dst,
    }}

@router.patch("", response_model=EdgeResp)
async def update_edge_endpoint(
    payload: EdgeCreate,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.edge, "边类型名")
    for k in payload.props:
        check_identifier(k, "属性名")
    try:
        from services.graph import insert_edge
        insert_edge(
            get_client(), sess,
            space=payload.space, src=payload.src, dst=payload.dst,
            edge=payload.edge, props=payload.props,
        )
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {
        "edge": payload.edge, "src": payload.src, "dst": payload.dst}}

