"""
Router: /api/v1/vertices
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies import get_client, get_session, require_api_key
from models.schemas import VertexCreate, VertexDelete, VertexResp, check_identifier
from modules.nebula_client import NebulaError
from services.graph import delete_vertex, fetch_vertex, insert_vertex

router = APIRouter(prefix="/vertices", tags=["vertices"])


@router.post("", response_model=VertexResp, status_code=status.HTTP_201_CREATED)
async def insert_vertex_endpoint(
    payload: VertexCreate,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.tag, "标签名")
    check_identifier(payload.vid, "VID")
    for k in payload.props:
        check_identifier(k, "属性名")
    try:
        insert_vertex(
            get_client(), sess,
            space=payload.space, vid=payload.vid,
            tag=payload.tag, props=payload.props,
        )
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"vid": payload.vid, "tag": payload.tag}}


@router.get("/{vid}", response_model=VertexResp)
async def fetch_vertex_endpoint(
    vid: str,
    space: str = Query(...),
    tag: str | None = None,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    if tag:
        check_identifier(tag, "标签名")
    try:
        rows = fetch_vertex(get_client(), sess, space=space, vid=vid, tag=tag)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"vid": vid, "tag": tag, "rows": rows}}


@router.delete("", response_model=VertexResp)
async def delete_vertex_endpoint(
    payload: VertexDelete,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    try:
        delete_vertex(
            get_client(), sess,
            space=payload.space, vid=payload.vid,
            with_edges=payload.with_edges,
        )
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"vid": payload.vid}}

@router.patch("/{vid}", response_model=VertexResp)
async def update_vertex_endpoint(
    vid: str,
    payload: VertexCreate,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(vid, "VID")
    check_identifier(payload.tag, "标签名")
    for k in payload.props:
        check_identifier(k, "属性名")
    try:
        from services.graph import insert_vertex
        insert_vertex(
            get_client(), sess,
            space=payload.space, vid=vid, tag=payload.tag, props=payload.props,
        )
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"vid": vid, "tag": payload.tag}}

