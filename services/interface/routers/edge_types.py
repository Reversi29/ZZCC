"""
Router: /api/v1/edge-types — edge type schema management.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from typing import Annotated

from dependencies import get_client, get_session, require_api_key
from models.schemas import EdgeListResp, SpaceResp, check_identifier
from modules.nebula_client import NebulaError

router = APIRouter(prefix="/edge-types", tags=["edge-types"])


@router.get("", response_model=EdgeListResp)
async def list_edge_types_endpoint(
    space: str = Query(..., description="Space name"),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    try:
        from services.graph import list_edge_types
        edges = list_edge_types(get_client(), sess, space)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"edges": edges}}


@router.post("", response_model=SpaceResp, status_code=status.HTTP_201_CREATED)
async def create_edge_type_endpoint(
    body: dict = Body(
        default=None,
        description='{"space": "S", "edge": "KNOWS", "properties": [{"name": "since", "type": "int"}]}',
    ),
    # Support query params too
    space: str | None = Query(default=None),
    edge: str | None = Query(default=None),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    # Accept either body or query params
    if body is not None:
        space = body.get("space", space)
        edge = body.get("edge", edge)
        properties = body.get("properties", [])
    else:
        properties = []

    if not space:
        raise HTTPException(status_code=422, detail="space is required")
    if not edge:
        raise HTTPException(status_code=422, detail="edge is required")

    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")
    for p in properties:
        check_identifier(p.get("name", ""), "属性名")
    cols = [(p["name"], p["type"]) for p in properties]
    try:
        from services.graph import create_edge_type as _create_edge_type
        _create_edge_type(get_client(), sess, space=space, edge=edge, columns=cols)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"edge": edge}}


@router.delete("", response_model=SpaceResp)
async def drop_edge_type_endpoint(
    space: str = Query(..., description="Space name"),
    edge: str = Query(..., description="Edge type name"),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")
    try:
        from services.graph import drop_edge_type as _drop_edge_type
        _drop_edge_type(get_client(), sess, space=space, edge=edge)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"edge": edge}}

@router.patch("", response_model=SpaceResp)
async def alter_edge_type_endpoint(
    space: str = Query(..., description="Space name"),
    edge: str = Query(..., description="Edge type name"),
    properties: list = Body(..., description='[{"name": "prop", "type": "type"}]'),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")
    for p in properties:
        check_identifier(p.get("name", ""), "属性名")
    cols = [(p["name"], p["type"]) for p in properties]
    try:
        from services.graph import alter_edge_type
        alter_edge_type(get_client(), sess, space=space, edge=edge, columns=cols)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"edge": edge}}

