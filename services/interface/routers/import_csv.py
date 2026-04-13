"""
Router: /api/v1/import — CSV file import.
"""
import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from dependencies import get_client, get_session, require_api_key
from models.schemas import ImportResp, check_identifier
from modules.nebula_client import NebulaError
from services.graph import insert_edge, insert_vertex

router = APIRouter(prefix="/import", tags=["import"])


def _coerce(raw: str | None) -> Any:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        if s.startswith("0") and len(s) > 1:
            raise ValueError
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


@router.post("/csv/vertices", response_model=ImportResp)
async def import_vertices_csv(
    space: str,
    tag: str,
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(tag, "标签名")
    reader = csv.DictReader(io.TextIOWrapper(file.file, encoding="utf-8"))
    if not reader.fieldnames or "vid" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must have 'vid' column")
    count, errors = 0, []
    for i, row in enumerate(reader, 1):
        vid = (row.get("vid") or "").strip()
        if not vid:
            continue
        props = {k: _coerce(v) for k, v in row.items() if k != "vid" and v}
        for k in props:
            check_identifier(k, "属性名")
        try:
            insert_vertex(
                get_client(), sess,
                space=space, vid=vid, tag=tag, props=props,
            )
            count += 1
        except NebulaError as exc:
            errors.append(f"row {i} ({vid}): {exc}")
    return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}


@router.post("/csv/edges", response_model=ImportResp)
async def import_edges_csv(
    space: str,
    edge: str,
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")
    reader = csv.DictReader(io.TextIOWrapper(file.file, encoding="utf-8"))
    if not reader.fieldnames or "src" not in reader.fieldnames or "dst" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must have 'src' and 'dst' columns")
    count, errors = 0, []
    for i, row in enumerate(reader, 1):
        src = (row.get("src") or "").strip()
        dst = (row.get("dst") or "").strip()
        if not src or not dst:
            continue
        props = {k: _coerce(v) for k, v in row.items() if k not in ("src", "dst") and v}
        for k in props:
            check_identifier(k, "属性名")
        try:
            insert_edge(
                get_client(), sess,
                space=space, src=src, dst=dst, edge=edge, props=props,
            )
            count += 1
        except NebulaError as exc:
            errors.append(f"row {i} ({src}->{dst}): {exc}")
    return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}
