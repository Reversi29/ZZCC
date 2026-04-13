"""
Router: /api/v1/tags
"""
from fastapi import APIRouter, Body, Depends, HTTPException, status

from dependencies import get_client, get_session, require_api_key
from models.schemas import SpaceResp, TagCreate, TagDrop, TagListResp, check_identifier
from modules.nebula_client import NebulaError
from services.graph import create_tag, drop_tag, list_tags

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=TagListResp)
async def list_tags_endpoint(
    space: str,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    tags = list_tags(get_client(), sess, space)
    return {"ok": True, "data": {"tags": tags}}


@router.post("", response_model=SpaceResp, status_code=status.HTTP_201_CREATED)
async def create_tag_endpoint(
    payload: TagCreate,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.tag, "标签名")
    for p in payload.properties:
        check_identifier(p.name, "属性名")
    cols = [(p.name, p.type) for p in payload.properties]
    try:
        create_tag(get_client(), sess, space=payload.space, tag=payload.tag, columns=cols)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"tag": payload.tag}}


@router.delete("", response_model=SpaceResp)
async def drop_tag_endpoint(
    payload: TagDrop,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.tag, "标签名")
    try:
        drop_tag(get_client(), sess, space=payload.space, tag=payload.tag)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"tag": payload.tag}}

@router.patch("", response_model=SpaceResp)
async def alter_tag_endpoint(
    payload: TagCreate,
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(payload.space, "空间名")
    check_identifier(payload.tag, "标签名")
    for p in payload.properties:
        check_identifier(p.name, "属性名")
    cols = [(p.name, p.type) for p in payload.properties]
    try:
        from services.graph import alter_tag
        alter_tag(get_client(), sess, space=payload.space, tag=payload.tag, columns=cols)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"tag": payload.tag}}

