"""
Router: /api/v1/edges — edge CRUD.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Annotated, Any

from dependencies import get_client, get_session, require_api_key
from models.schemas import EdgeResp, EdgeCreate, EdgeDelete, check_identifier
from modules.nebula_client import NebulaError
from services.graph import delete_edge, fetch_edge, insert_edge

router = APIRouter(prefix="/edges", tags=["edges"])


@router.get("", response_model=EdgeResp)
async def get_edge_endpoint(
    space: str = Query(..., description="Space name"),
    edge: str = Query(..., description="Edge type name"),
    src: str = Query(..., description="Source vertex ID"),
    dst: str = Query(..., description="Destination vertex ID"),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")
    check_identifier(src, "SRC VID")
    check_identifier(dst, "DST VID")
    try:
        rows = fetch_edge(get_client(), sess, space=space, src=src, dst=dst, edge=edge)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Edge {src}->{dst} not found")
        return {"ok": True, "data": rows}
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("", response_model=EdgeResp, status_code=201)
async def create_edge_endpoint(
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
        "edge": payload.edge, "src": payload.src, "dst": payload.dst}}


@router.patch("", response_model=EdgeResp)
async def update_edge_endpoint(
    payload: EdgeCreate,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    """
    Partial update: fetch existing props, merge, delete+re-insert.
    Only attributes in the request body are updated; others are preserved.
    """
    check_identifier(payload.space, "空间名")
    check_identifier(payload.edge, "边类型名")
    check_identifier(payload.src, "SRC VID")
    check_identifier(payload.dst, "DST VID")
    for k in payload.props:
        check_identifier(k, "属性名")

    client = get_client()
    try:
        existing = fetch_edge(client, sess, space=payload.space,
                              src=payload.src, dst=payload.dst, edge=payload.edge)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Edge {payload.src}->{payload.dst} not found")

        base: dict[str, Any] = dict(existing[0])
        base.update(payload.props)

        delete_edge(client, sess, space=payload.space,
                    src=payload.src, dst=payload.dst, edge=payload.edge)
        insert_edge(client, sess, space=payload.space,
                   src=payload.src, dst=payload.dst, edge=payload.edge, props=base)

    except HTTPException:
        raise
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True, "data": {
        "edge": payload.edge, "src": payload.src, "dst": payload.dst}}


@router.delete("", response_model=EdgeResp)
async def delete_edge_endpoint(
    payload: EdgeDelete,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.edge, "边类型名")
    check_identifier(payload.src, "SRC VID")
    check_identifier(payload.dst, "DST VID")
    try:
        delete_edge(get_client(), sess, space=payload.space,
                    src=payload.src, dst=payload.dst, edge=payload.edge)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {
        "edge": payload.edge, "src": payload.src, "dst": payload.dst}}
