"""
routers/netdrive.py — 企业网盘
"""
import os, secrets
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, Form
from pydantic import BaseModel
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db, NetFile
from routers.auth import require_auth

router = APIRouter(prefix="/api/netdrive", tags=["NetDrive"])
R = dict
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "netdrive")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def _to_dict(r):
    return {
        "id": r.id,
        "parent_id": r.parent_id,
        "name": r.name,
        "file_size": r.file_size or 0,
        "mime_type": r.mime_type or "",
        "is_dir": bool(r.is_dir),
        "uploaded_by": r.uploaded_by,
        "share_code": r.share_code,
        "created": r.creation.strftime("%Y-%m-%d %H:%M") if r.creation else "",
    }

@router.get("/list")
def list_files(parent_id: int = Query(-1),
               db: Session = Depends(get_db),
               current_user=Depends(require_auth)):
    q = db.query(NetFile)
    if parent_id is None or parent_id == -1:
        q = q.filter(or_(NetFile.parent_id.is_(None), NetFile.parent_id == -1))
    else:
        q = q.filter(NetFile.parent_id == parent_id)
    q = q.order_by(NetFile.is_dir.desc(), NetFile.name)
    rows = q.all()
    return R(data={"items": [_to_dict(r) for r in rows], "length": len(rows)})

class NetRequest(BaseModel):
    name: str = ""
    parent_id: int = -1

@router.post("/mkdir")
def make_dir(body: NetRequest,
             db: Session = Depends(get_db),
             current_user=Depends(require_auth)):
    if not body.name:
        return R(message="名称不能为空", status_code=400)
    f = NetFile(name=body.name, parent_id=None if body.parent_id == -1 else body.parent_id,
                is_dir=True, uploaded_by=current_user.username)
    db.add(f); db.commit(); db.refresh(f)
    return R(data=_to_dict(f), message="目录创建成功")

@router.post("/upload")
async def upload_file(file: UploadFile = File(...),
                      parent_id: int = Form(-1),
                      db: Session = Depends(get_db),
                      current_user=Depends(require_auth)):
    if not file.filename:
        return R(message="文件名不能为空", status_code=400)
    ext = os.path.splitext(file.filename)[1]
    content = await file.read()
    nf = NetFile(name=file.filename, parent_id=None if parent_id == -1 else parent_id,
                 is_dir=False, file_size=len(content),
                 mime_type=file.content_type or "",
                 uploaded_by=current_user.username)
    db.add(nf); db.commit(); db.refresh(nf)
    sid = str(nf.id) + ext
    path = os.path.join(UPLOAD_DIR, sid)
    with open(path, "wb") as f:
        f.write(content)
    return R(data=_to_dict(nf), message="上传成功")

@router.get("/download/{fid}")
def download_file(fid: int, db: Session = Depends(get_db),
                  current_user=Depends(require_auth)):
    nf = db.query(NetFile).get(fid)
    if not nf or nf.is_dir:
        raise HTTPException(status_code=404, detail="文件不存在")
    # find the stored file — iterate uploads dir matching id
    # We stored by sid, need reverse lookup: store the id in filename?
    # Simple approach: rename stored file to {id}.{ext}
    ext = os.path.splitext(nf.name)[1]
    path = os.path.join(UPLOAD_DIR, str(fid) + ext)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件已丢失")
    return FileResponse(path, filename=nf.name, media_type=nf.mime_type or "application/octet-stream")

@router.post("/share/{fid}")
def share_file(fid: int, db: Session = Depends(get_db),
               current_user=Depends(require_auth)):
    nf = db.query(NetFile).get(fid)
    if not nf:
        raise HTTPException(status_code=404, detail="文件不存在")
    nf.share_code = secrets.token_hex(6)
    db.commit(); db.refresh(nf)
    return R(data=_to_dict(nf), message="分享链接已生成")

@router.delete("/delete/{fid}")
def delete_file(fid: int, db: Session = Depends(get_db),
                current_user=Depends(require_auth)):
    nf = db.query(NetFile).get(fid)
    if not nf:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not nf.is_dir:
        ext = os.path.splitext(nf.name)[1]
        path = os.path.join(UPLOAD_DIR, str(fid) + ext)
        if os.path.exists(path):
            os.remove(path)
    db.delete(nf); db.commit()
    return R(message="已删除", status_code=204)

@router.put("/rename/{fid}")
def rename_file(fid: int,
                body: NetRequest,
                db: Session = Depends(get_db),
                current_user=Depends(require_auth)):
    nf = db.query(NetFile).get(fid)
    if not nf:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not body.name:
        return R(message="名称不能为空", status_code=400)
    nf.name = body.name
    db.commit()
    return R(data=_to_dict(nf), message="已重命名")