"""routers/project.py — 项目/任务（SQLAlchemy）"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db, Project, Task
from pydantic import BaseModel
from typing import Optional
from routers._db import model_to_dict, seq_for, register as _reg, DOCTYPE_MODEL

router = APIRouter(prefix="/api/resource", tags=["Project"])

_reg("Project", Project, "PRJ")
_reg("Task", Task, "TSK")

def check(x_api_key: str = Header(...)):
    from config import get_settings
    if x_api_key != get_settings().API_KEY:
        raise HTTPException(401, "Invalid API Key")

def md(m) -> dict:
    return model_to_dict(m)

class R(BaseModel):
    data: Optional[dict | list] = None
    message: Optional[str] = None

def _upsert(model_cls, name: str, data: dict, db: Session, update=True):
    m = db.query(model_cls).filter(model_cls.name == name).first() if update else None
    if not m:
        m = model_cls(name=name)
        db.add(m)
    for k, v in data.items():
        if k not in ("name",) and hasattr(m, k):
            setattr(m, k, v)
    return m

# ── Project ───────────────────────────────────────────────────
@router.get("/Project", response_model=R)
def list_projects(db: Session = Depends(get_db), limit: int = 100, x_api_key: str = Header(None)):
    check(x_api_key)
    rows = db.query(Project).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Project", response_model=R)
def create_project(data: dict, db: Session = Depends(get_db), x_api_key: str = Header(None)):
    check(x_api_key)
    name = data.get("name") or seq_for("Project", db)
    m = _upsert(Project, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Project created")

@router.get("/Project/{name}", response_model=R)
def get_project(name: str, db: Session = Depends(get_db), x_api_key: str = Header(None)):
    check(x_api_key)
    m = db.query(Project).filter(Project.name == name).first()
    if not m: raise HTTPException(404, "Project not found")
    return R(data=md(m))

@router.put("/Project/{name}", response_model=R)
def update_project(name: str, data: dict, db: Session = Depends(get_db), x_api_key: str = Header(None)):
    check(x_api_key)
    m = _upsert(Project, name, data, db)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Project updated")

@router.delete("/Project/{name}", response_model=R)
def delete_project(name: str, db: Session = Depends(get_db), x_api_key: str = Header(None)):
    check(x_api_key)
    m = db.query(Project).filter(Project.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Project deleted")

# ── Task ──────────────────────────────────────────────────────
@router.get("/Task", response_model=R)
def list_tasks(db: Session = Depends(get_db), limit: int = 100, x_api_key: str = Header(None)):
    check(x_api_key)
    rows = db.query(Task).limit(limit).all()
    return R(data={"data": [md(r) for r in rows], "length": len(rows)})

@router.post("/Task", response_model=R)
def create_task(data: dict, db: Session = Depends(get_db), x_api_key: str = Header(None)):
    check(x_api_key)
    name = data.get("name") or seq_for("Task", db)
    m = _upsert(Task, name, data, db, update=False)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Task created")

@router.get("/Task/{name}", response_model=R)
def get_task(name: str, db: Session = Depends(get_db), x_api_key: str = Header(None)):
    check(x_api_key)
    m = db.query(Task).filter(Task.name == name).first()
    if not m: raise HTTPException(404, "Task not found")
    return R(data=md(m))

@router.put("/Task/{name}", response_model=R)
def update_task(name: str, data: dict, db: Session = Depends(get_db), x_api_key: str = Header(None)):
    check(x_api_key)
    m = _upsert(Task, name, data, db)
    db.commit(); db.refresh(m)
    return R(data={"name": m.name}, message="Task updated")

@router.delete("/Task/{name}", response_model=R)
def delete_task(name: str, db: Session = Depends(get_db), x_api_key: str = Header(None)):
    check(x_api_key)
    m = db.query(Task).filter(Task.name == name).first()
    if m: db.delete(m); db.commit()
    return R(message="Task deleted")
