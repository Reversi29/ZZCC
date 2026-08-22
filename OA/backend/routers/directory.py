"""
routers/directory.py — 组织通讯录
基于 Department（组织架构树）+ Employee（成员）
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db
from database import Department, Employee
from routers.auth import require_auth

router = APIRouter(prefix="/api/directory", tags=["Directory"])

R = dict

@router.get("/tree")
def directory_tree(db: Session = Depends(get_db),
                  company: str = Query(None, description="按公司过滤"),
                  current_user=Depends(require_auth)):
    """返回组织架构树（含每个部门的成员数）"""
    q = db.query(Department)
    if company:
        q = q.filter(Department.company == company)
    rows = q.all()
    names = {r.name for r in rows}

    # 预取员工，构建 dept → employees 映射
    dept_members = {}
    dept_name_to_id = {r.department_name: r.name for r in rows}
    eq = db.query(Employee)
    if company:
        eq = eq.filter(Employee.company == company)
    for emp in eq.all():
        did = dept_name_to_id.get(emp.department)
        if did is not None:
            dept_members.setdefault(did, []).append(emp.employee_name)

    # 构建树
    children = {}
    for r in rows:
        children[r.name] = [c for c in (c.name for c in rows if c.parent == r.name and c.name in names)]

    roots = [r for r in rows if r.parent is None or r.parent not in names]
    def build(row):
        return {
            "name": row.name,
            "department_name": row.department_name,
            "parent": row.parent,
            "lft": row.lft,
            "rgt": row.rgt,
            "member_count": len(dept_members.get(row.name, [])),
            "members": dept_members.get(row.name, []),
            "children": [build(db.query(Department).get(c)) for c in children.get(row.name, [])],
        }

    tree = [build(r) for r in roots]
    return R(data={"tree": tree, "length": len(rows)})

@router.get("/search")
def directory_search(q: str = Query(""),
                     db: Session = Depends(get_db),
                     current_user=Depends(require_auth)):
    """搜索员工（模糊匹配姓名/职位）"""
    pat = f"%{q}%"
    emps = db.query(Employee).filter(
        or_(Employee.employee_name.like(pat),
            Employee.designation.like(pat))
    ).all()
    result = [{
        "id": e.name,
        "name": e.employee_name,
        "designation": e.designation,
        "department": e.department,
        "email": e.email,
        "phone": e.phone,
    } for e in emps]
    return R(data={"items": result, "length": len(result)})