"""
routers/search.py — 全局搜索
跨模块搜索: 员工/部门/项目/合同/采购/发票/资产/客户/供应商/工单/审批单
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import get_db
from routers.auth import require_auth, require_admin

router = APIRouter(prefix="/api/search", tags=["search"])

R = dict


class SearchResponse(BaseModel):
    total: int
    items: list[dict]


@router.get("/global")
async def global_search(
    q: str = Query("", description="搜索关键词"),
    type: str = Query("all", description="过滤类型: all/employee/department/project/contract/lead/opportunity/contact"),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
) -> SearchResponse:
    """全局搜索 — 跨所有可搜索模块"""
    pat = f"%{q}%"
    results = []
    if not q:
        return SearchResponse(total=0, items=[])

    # ── 员工 ──
    if type in ("all", "employee"):
        from database import Employee
        emps = db.query(Employee).filter(
            or_(Employee.employee_name.like(pat),
                Employee.designation.like(pat),
                Employee.department.like(pat))
        ).all()
        for e in emps:
            results.append({
                "type": "employee",
                "id": e.name,
                "name": e.employee_name,
                "subtitle": f"{e.designation} · {e.department}",
                "path": "hr",
            })

    # ── 部门 ──
    if type in ("all", "department"):
        from database import Department
        depts = db.query(Department).filter(
            or_(Department.department_name.like(pat),
                Department.name.like(pat))
        ).all()
        for d in depts:
            results.append({
                "type": "department",
                "id": d.name,
                "name": d.department_name,
                "subtitle": f"部门 {d.name}",
                "path": "departments",
            })

    # ── 项目 ──
    if type in ("all", "project"):
        from database import Project
        projs = db.query(Project).filter(
            or_(Project.project_name.like(pat),
                Project.name.like(pat))
        ).all()
        for p in projs:
            results.append({
                "type": "project",
                "id": p.name,
                "name": p.project_name,
                "subtitle": f"Project {p.name}",
                "path": "project",
            })

    # ── 合同 ──
    if type in ("all", "contract"):
        from database import Contract
        cons = db.query(Contract).filter(
            or_(Contract.contract_name.like(pat),
                Contract.party_a.like(pat),
                Contract.party_b.like(pat),
                Contract.name.like(pat))
        ).all()
        for c in cons:
            results.append({
                "type": "contract",
                "id": c.name,
                "name": c.contract_name,
                "subtitle": f"Contract {c.name} · {c.party_b}",
                "path": "compliance",
            })

    # ── 采购单 ──
    if type in ("all", "po"):
        from database import PurchaseOrder
        pos = db.query(PurchaseOrder).filter(
            or_(PurchaseOrder.supplier.like(pat),
                PurchaseOrder.name.like(pat))
        ).all()
        for p in pos:
            results.append({
                "type": "po",
                "id": p.name,
                "name": p.supplier,
                "subtitle": f"PO {p.name} · ¥{p.total}",
                "path": "procurement",
            })

    # ── 发票 ──
    if type in ("all", "invoice"):
        from database import JournalEntry
        jes = db.query(JournalEntry).filter(
            or_(JournalEntry.title.like(pat),
                JournalEntry.name.like(pat))
        ).all()
        for j in jes[:20]:  # 限制数量避免溢出
            results.append({
                "type": "invoice",
                "id": j.name,
                "name": j.title,
                "subtitle": f"Journal Entry {j.name}",
                "path": "finance",
            })

    # ── 客户/供应商 ──
    if type in ("all", "lead", "contact"):
        from database import Lead, Contact
        for LeadModel, tname, path in [(Lead, "lead", "crm"), (Contact, "contact", "contacts")]:
            items = db.query(LeadModel).filter(
                or_(LeadModel.name.like(pat),
                    LeadModel.company_name.like(pat) if hasattr(LeadModel, 'company_name') else False,
                    LeadModel.first_name.like(pat) if hasattr(LeadModel, 'first_name') else False,
                    LeadModel.last_name.like(pat) if hasattr(LeadModel, 'last_name') else False,
                    LeadModel.lead_name.like(pat) if hasattr(LeadModel, 'lead_name') else False,
                    LeadModel.contact_name.like(pat) if hasattr(LeadModel, 'contact_name') else False,
                    LeadModel.phone.like(pat) if hasattr(LeadModel, 'phone') else False,
                )
            ).all()
            for item in items:
                if tname == "lead":
                    results.append({
                        "type": "lead",
                        "id": item.name,
                        "name": item.lead_name or item.first_name or "Unknown",
                        "subtitle": f"{item.company_name or ''} · {item.phone or ''}",
                        "path": path,
                    })
                else:
                    results.append({
                        "type": "contact",
                        "id": item.name,
                        "name": item.contact_name or item.first_name or "Unknown",
                        "subtitle": f"{item.company_name or ''} · {item.phone or ''}",
                        "path": path,
                    })

    return SearchResponse(total=len(results), items=results)


@router.get("/suggestions")
async def search_suggestions(
    q: str = Query("", description="搜索关键词（输入时实时建议）"),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """快速搜索建议 — 返回前 5 条匹配"""
    pat = f"%{q}%"
    results = []

    if q:
        from database import Employee, Department, Project, Contract
        for model, type_name, label_field in [
            (Employee, "employee", "employee_name"),
            (Department, "department", "department_name"),
            (Project, "project", "project_name"),
            (Contract, "contract", "contract_name"),
        ]:
            rows = db.query(model).filter(
                getattr(model, label_field).like(pat)
            ).limit(5).all()
            for r in rows:
                results.append({
                    "type": type_name,
                    "id": r.name,
                    "name": getattr(r, label_field),
                })

    return {"total": len(results), "items": results[:10]}