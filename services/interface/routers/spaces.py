"""
Router: /api/v1/spaces
"""
from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import get_client, get_session, verify_api_key
from models.schemas import SpaceCreate, SpaceListResp, SpaceResp
from modules.nebula_client import NebulaError
from services.graph import create_space, drop_space, list_spaces, wait_space

router = APIRouter(prefix="/spaces", tags=["spaces"])


@router.post("", response_model=SpaceResp, status_code=status.HTTP_201_CREATED)
async def create_space_endpoint(
    payload: SpaceCreate,
    sess=Depends(get_session),
    auth: str = Depends(verify_api_key),
):
    try:
        create_space(
            get_client(), sess,
            name=payload.name,
            partition_num=payload.partition_num,
            replica_factor=payload.replica_factor,
            vid_type=payload.vid_type,
        )
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    wait_space(get_client(), sess, payload.name)
    return {"ok": True, "data": {"space": payload.name}}


@router.get("", response_model=SpaceListResp)
async def list_spaces_endpoint(
    sess=Depends(get_session),
    auth: str = Depends(verify_api_key),
):
    spaces = list_spaces(get_client(), sess)
    return {"ok": True, "data": {"spaces": spaces}}


@router.delete("/{name}", response_model=SpaceResp)
async def drop_space_endpoint(
    name: str,
    sess=Depends(get_session),
    auth: str = Depends(verify_api_key),
):
    from models.schemas import check_identifier
    check_identifier(name, "空间名")
    try:
        drop_space(get_client(), sess, name)
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "data": {"space": name}}
