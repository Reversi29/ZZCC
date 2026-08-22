"""
routers/form_designer.py — 表单设计器
"""
import json
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db, FormTemplate, FormSubmission
from routers.auth import require_auth

router = APIRouter(prefix="/api/form-designer", tags=["FormDesigner"])
R = dict

class FormField(BaseModel):
    id: str = ""
    label: str = ""
    field_type: str = "text"  # text / textarea / select / number / date / checkbox
    required: bool = False
    options: list = []  # for select: [label1,label2,...]
    placeholder: str = ""

class FormCreate(BaseModel):
    name: str = ""
    description: str = ""
    schema: list = []
    status: str = "active"

class FormSubmit(BaseModel):
    template_id: int = 0
    data: dict = {}

def _to_dict(r):
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description or "",
        "schema": json.loads(r.schema) if r.schema else [],
        "created_by": r.created_by,
        "status": r.status,
        "created": r.creation.strftime("%Y-%m-%d %H:%M") if r.creation else "",
    }

@router.get("/templates")
def list_templates(db: Session = Depends(get_db), current_user=Depends(require_auth)):
    rows = db.query(FormTemplate).all()
    return R(data={"items": [_to_dict(r) for r in rows], "length": len(rows)})

@router.post("/templates")
def create_template(body: FormCreate, db: Session = Depends(get_db),
                    current_user=Depends(require_auth)):
    t = FormTemplate(name=body.name, description=body.description,
                     schema=json.dumps(body.schema, ensure_ascii=False),
                     created_by=current_user.username, status=body.status)
    db.add(t); db.commit(); db.refresh(t)
    return R(data=_to_dict(t), message="Template created")

@router.put("/templates/{tid}")
def update_template(tid: int, body: FormCreate, db: Session = Depends(get_db),
                    current_user=Depends(require_auth)):
    t = db.query(FormTemplate).get(tid)
    if not t or t.created_by != current_user.username:
        return R(message="403", status_code=403)
    t.name = body.name; t.description = body.description
    t.schema = json.dumps(body.schema, ensure_ascii=False)
    t.status = body.status
    db.commit(); db.refresh(t)
    return R(data=_to_dict(t), message="Updated")

@router.delete("/templates/{tid}")
def delete_template(tid: int, db: Session = Depends(get_db),
                    current_user=Depends(require_auth)):
    t = db.query(FormTemplate).get(tid)
    if not t or t.created_by != current_user.username:
        return R(message="403", status_code=403)
    db.delete(t); db.commit()
    return R(message="Deleted", status_code=204)

@router.get("/submissions")
def list_submissions(template_id: int = Query(0),
                     db: Session = Depends(get_db), current_user=Depends(require_auth)):
    q = db.query(FormSubmission)
    if template_id:
        q = q.filter(FormSubmission.template_id == template_id)
    rows = q.order_by(FormSubmission.id.desc()).all()
    return R(data={"items": [{
        "id": r.id, "template_id": r.template_id,
        "data": json.loads(r.data) if r.data else {},
        "submitted_by": r.submitted_by, "status": r.status,
        "created": r.creation.strftime("%Y-%m-%d %H:%M") if r.creation else "",
    } for r in rows], "length": len(rows)})

@router.post("/submissions")
def create_submission(body: FormSubmit, db: Session = Depends(get_db),
                      current_user=Depends(require_auth)):
    s = FormSubmission(template_id=body.template_id,
                       data=json.dumps(body.data, ensure_ascii=False),
                       submitted_by=current_user.username)
    db.add(s); db.commit(); db.refresh(s)
    return R(data={"id": s.id, "template_id": s.template_id, "data": body.data},
             message="Submitted")