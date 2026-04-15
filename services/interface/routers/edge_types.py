"""
Router: /api/v1/edge-types — edge type schema management.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from dependencies import get_client, get_session, verify_api_key
from models.schemas import EdgeListResp, EdgeTypeAlter, SpaceResp, check_identifier
from modules.nebula_client import NebulaError

router = APIRouter(prefix="/edge-types", tags=["edge-types"])


@router.get("", response_model=EdgeListResp)
async def list_edge_types_endpoint(
    space: str = Query(..., description="Space name"),
    sess=Depends(get_session),
    auth: str = Depends(verify_api_key),
):
    check_identifier(space, "空间名")
    try:
        from services.graph import list_edge_types
        edges = list_edge_types(get_client(), sess, space)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"edges": edges}}


@router.post("", response_model=SpaceResp, status_code=status.HTTP_201_CREATED)
async def create_edge_type_endpoint(
    body: dict | None = None,
    # Support query params too (for backwards compatibility)
    space: str | None = Query(default=None),
    edge: str | None = Query(default=None),
    sess=Depends(get_session),
    auth: str = Depends(verify_api_key),
):
    # Accept either body or query params
    if body is not None:
        space = body.get("space", space)
        edge = body.get("edge", edge)
        props_list = body.get("properties", [])
    else:
        props_list = properties or []

    if not space:
        raise HTTPException(status_code=422, detail="space is required")
    if not edge:
        raise HTTPException(status_code=422, detail="edge is required")

    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")
    for p in props_list:
        check_identifier(p.get("name", ""), "属性名")
    cols = [(p["name"], p["type"]) for p in props_list]
    try:
        from services.graph import create_edge_type as _create_edge_type
        _create_edge_type(get_client(), sess, space=space, edge=edge, columns=cols)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"edge": edge}}


@router.patch("", response_model=SpaceResp)
async def alter_edge_type_endpoint(
    payload: EdgeTypeAlter,
    sess=Depends(get_session),
    auth: str = Depends(verify_api_key),
):
    """Add properties to an existing edge type (ALTER EDGE ... ADD)."""
    check_identifier(payload.space, "空间名")
    check_identifier(payload.edge, "边类型名")
    for p in payload.properties:
        check_identifier(p.get("name", ""), "属性名")
    cols = [(p["name"], p["type"]) for p in payload.properties]
    try:
        from services.graph import alter_edge_type as _alter_edge_type
        _alter_edge_type(get_client(), sess, space=payload.space, edge=payload.edge, columns=cols)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"edge": payload.edge}}


@router.delete("", response_model=SpaceResp)
async def drop_edge_type_endpoint(
    space: str = Query(..., description="Space name"),
    edge: str = Query(..., description="Edge type name"),
    sess=Depends(get_session),
    auth: str = Depends(verify_api_key),
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
