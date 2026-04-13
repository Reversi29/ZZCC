"""
Router: /api/v1/vertices — vertex CRUD.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from typing import Annotated, Any

from dependencies import get_client, get_session, require_api_key
from models.schemas import VertexResp, VertexCreate, VertexDelete, check_identifier
from modules.nebula_client import NebulaError
from services.graph import delete_vertex, fetch_vertex, insert_vertex

router = APIRouter(prefix="/vertices", tags=["vertices"])


@router.get("/{vid}", response_model=VertexResp)
async def get_vertex_endpoint(
    vid: str,
    space: str = Query(..., description="Space name"),
    tag: str | None = Query(default=None),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(vid, "VID")
    if tag:
        check_identifier(tag, "标签名")
    try:
        rows = fetch_vertex(get_client(), sess, space=space, vid=vid, tag=tag)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Vertex '{vid}' not found")
        return {"ok": True, "data": rows}
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("", response_model=VertexResp, status_code=201)
async def create_vertex_endpoint(
    payload: VertexCreate,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.vid, "VID")
    check_identifier(payload.tag, "标签名")
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


@router.patch("/{vid}", response_model=VertexResp)
async def update_vertex_endpoint(
    vid: str,
    payload: VertexCreate,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    """
    Partial update — fetch existing props, merge, delete+re-insert.
    Only attributes present in the request body are updated; others are preserved.
    """
    check_identifier(payload.space, "空间名")
    check_identifier(vid, "VID")
    check_identifier(payload.tag, "标签名")
    for k in payload.props:
        check_identifier(k, "属性名")

    client = get_client()
    try:
        existing = fetch_vertex(client, sess, space=payload.space, vid=vid, tag=payload.tag)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Vertex '{vid}' not found in space '{payload.space}'")

        # Merge: existing props + new props (new props take precedence)
        base: dict[str, Any] = dict(existing[0])
        base.update(payload.props)

        # Delete then re-insert with merged props
        delete_vertex(client, sess, space=payload.space, vid=vid, with_edges=False)
        insert_vertex(client, sess, space=payload.space, vid=vid, tag=payload.tag, props=base)

    except HTTPException:
        raise
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True, "data": {"vid": vid, "tag": payload.tag}}


@router.delete("", response_model=VertexResp)
async def delete_vertex_by_body(
    payload: VertexDelete,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    """DELETE with body: {"space": "...", "vid": "...", "with_edges": true}"""
    check_identifier(payload.space, "空间名")
    check_identifier(payload.vid, "VID")
    try:
        delete_vertex(get_client(), sess, space=payload.space, vid=payload.vid,
                      with_edges=payload.with_edges)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"vid": payload.vid}}


@router.delete("/{vid}", response_model=VertexResp)
async def delete_vertex_endpoint(
    vid: str,
    space: str = Query(...),
    with_edges: bool = Query(True),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.vid, "VID")
    try:
        delete_vertex(get_client(), sess, space=payload.space, vid=payload.vid,
                      with_edges=payload.with_edges)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"vid": payload.vid}}

