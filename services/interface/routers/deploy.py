"""
Router: /api/v1/deploy — one-shot space + schema creation.
"""
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException

from dependencies import get_client, get_session, verify_api_key
from models.schemas import DeployRequest, SpaceResp, check_identifier
from modules.nebula_client import NebulaError
from services.graph import (
    create_edge_type,
    create_space,
    create_tag,
    wait_space,
)

router = APIRouter(prefix="/deploy", tags=["deploy"])


@router.post("", response_model=SpaceResp, status_code=201)
async def deploy_schema_endpoint(
    payload: DeployRequest | None = Body(default=None),
    sess=Depends(get_session),
    auth: str = Depends(verify_api_key),
):
    if payload is None:
        defaults = Path(__file__).parent.parent / "deploy_defaults.json"
        if not defaults.exists():
            raise HTTPException(status_code=500, detail="deploy_defaults.json not found")
        payload = DeployRequest.model_validate_json(defaults.read_text())

    check_identifier(payload.space, "空间名")
    for tag in payload.tags:
        check_identifier(tag.name, "标签名")
    for edge in payload.edges:
        check_identifier(edge.name, "边类型名")

    steps: list[str] = []
    try:
        create_space(
            get_client(), sess,
            name=payload.space,
            partition_num=payload.partition_num,
            replica_factor=payload.replica_factor,
            vid_type=payload.vid_type,
        )
        steps.append(f"space:{payload.space}")
        wait_space(get_client(), sess, payload.space)
        steps.append(f"space-ready:{payload.space}")

        for tag in payload.tags:
            cols = [(p.name, p.type) for p in tag.properties]
            create_tag(get_client(), sess, space=payload.space, tag=tag.name, columns=cols)
            steps.append(f"tag:{tag.name}")

        for edge in payload.edges:
            cols = [(p.name, p.type) for p in edge.properties]
            create_edge_type(get_client(), sess, space=payload.space, edge=edge.name, columns=cols)
            steps.append(f"edge:{edge.name}")

    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True, "data": {"space": payload.space, "steps": steps}}
