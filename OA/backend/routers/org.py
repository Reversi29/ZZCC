"""
routers/org.py — 组织架构管理（Department CRUD）
前缀：/api/resource/Department

NSM（Nested Set Model）维护规则：
  - 新增子节点：所有 lft/rgt >= 父.rgt 的节点向右推移 2 位，在父.rgt 位置插入新节点
  - 删除节点（含后代）：宽度 width = node.rgt - node.lft + 1；删除后代后，所有
    rgt > node.rgt 的节点向左推移 width 位；所有 lft > node.rgt 的节点向左推移 width 位
  - 移动节点（改 parent）：先删再插（保持 lft/rgt 整数序列不出现空洞）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db, Department
from routers.auth import require_auth, require_admin, CurrentUser
from routers._db import model_to_dict


router = APIRouter(prefix="/api/resource", tags=["Organization"])
_md = lambda m: model_to_dict(m)


class DeptCreate(BaseModel):
    name: str                    # 主键，如 "D-NEW"
    department_name: str         # 显示名，如 "研发部"
    parent: Optional[str] = None # 父部门 name，None 表示根部门
    company: Optional[str] = "ZZCC"
    is_group: bool = False


class DeptUpdate(BaseModel):
    department_name: Optional[str] = None  # 只允许改名（移动用删插实现）
    parent: Optional[str] = None            # None=不变


# ── 通用辅助 ──────────────────────────────────────────────────

def _dept_to_dict(d: Department, db: Session) -> dict:
    """Department → plain dict（含直接子部门数量）"""
    out = _md(d)
    # 直接子部门数量（查 parent 引用，而非 NSM 区间反推）
    out["children_count"] = db.query(Department).filter_by(parent=d.name).count()
    out["has_children"] = out["children_count"] > 0
    return out


def _next_lft_rgt(db: Session, parent_rgt: int) -> tuple[int, int]:
    """给定父节点 rgt，返回新节点应占的 lft/rgt，并维护已有节点区间"""
    # 1. 推移 lft/rgt >= parent_rgt 的节点
    db.execute(
        __import__("sqlalchemy").text(
            "UPDATE departments SET lft = lft + 2 WHERE lft >= :r"
        ), {"r": parent_rgt}
    )
    db.execute(
        __import__("sqlalchemy").text(
            "UPDATE departments SET rgt = rgt + 2 WHERE rgt >= :r"
        ), {"r": parent_rgt}
    )
    db.flush()
    return (parent_rgt, parent_rgt + 1)


def _remove_subtree(db: Session, lft: int, rgt: int):
    """删除 [lft, rgt] 区间内的所有节点，并维护剩余节点"""
    width = rgt - lft + 1
    # 删除区间内节点
    db.execute(
        __import__("sqlalchemy").text(
            "DELETE FROM departments WHERE lft BETWEEN :l AND :r"
        ), {"l": lft, "r": rgt}
    )
    # lft/rgt > rgt 的节点左移 width 位
    db.execute(
        __import__("sqlalchemy").text(
            "UPDATE departments SET lft = lft - :w WHERE lft > :r"
        ), {"w": width, "r": rgt}
    )
    db.execute(
        __import__("sqlalchemy").text(
            "UPDATE departments SET rgt = rgt - :w WHERE rgt > :r"
        ), {"w": width, "r": rgt}
    )
    db.flush()


# ── CRUD ──────────────────────────────────────────────────────

@router.get("/Department", response_model=dict)
def list_departments(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_auth),
):
    """
    返回所有部门（扁平列表，前端可自行组装树）。
    按 lft 排序保证父子顺序。
    """
    depts = db.query(Department).order_by(Department.lft).all()
    return {"data": [_dept_to_dict(d, db) for d in depts]}


@router.post("/Department", response_model=dict)
def create_department(
    body: DeptCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
):
    """新增部门（admin only）。指定 parent 时插入到父节点下方；parent=None 插入到树末尾。"""
    # 主键去重
    if db.query(Department).filter_by(name=body.name).first():
        raise HTTPException(400, f"部门编号 {body.name} 已存在")

    if body.parent:
        parent = db.query(Department).filter_by(name=body.parent).first()
        if not parent:
            raise HTTPException(400, f"父部门 {body.parent} 不存在")
        insert_rgt = parent.rgt
    else:
        # 无 parent → 插到最大 rgt 之后（根节点同级）
        max_r = db.query(Department).order_by(Department.rgt.desc()).first()
        insert_rgt = (max_r.rgt + 1) if max_r else 1

    new_lft, new_rgt = _next_lft_rgt(db, insert_rgt)

    d = Department(
        name=body.name,
        department_name=body.department_name,
        parent=body.parent,
        lft=new_lft,
        rgt=new_rgt,
        company=body.company or "ZZCC",
        is_group=body.is_group,
        ext=None,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"data": _dept_to_dict(d, db), "message": "部门已创建"}


@router.get("/Department/{name}", response_model=dict)
def get_department(
    name: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_auth),
):
    d = db.query(Department).filter_by(name=name).first()
    if not d:
        raise HTTPException(404, "部门不存在")
    children = db.query(Department).filter_by(parent=name).order_by(Department.lft).all()
    out = _dept_to_dict(d, db)
    out["children"] = [{"name": c.name, "department_name": c.department_name} for c in children]
    return {"data": out}


@router.put("/Department/{name}", response_model=dict)
def update_department(
    name: str,
    body: DeptUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
):
    """
    更新部门（admin only）。
    - department_name: 直接改名
    - parent: 改为新的父节点（通过删插实现，必须保证不形成环）
    """
    d = db.query(Department).filter_by(name=name).first()
    if not d:
        raise HTTPException(404, "部门不存在")

    changed = False

    if body.department_name is not None and body.department_name != d.department_name:
        d.department_name = body.department_name
        changed = True

    if body.parent is not None and body.parent != d.parent:
        # 禁止移动到自身或自身后代下（NSM 环检测）
        if body.parent == name:
            raise HTTPException(400, "不能将部门设为自身的子部门")
        new_parent = db.query(Department).filter_by(name=body.parent).first()
        if not new_parent:
            raise HTTPException(400, f"目标父部门 {body.parent} 不存在")
        # 检测：目标 parent 是否是当前节点的后代
        if new_parent.lft > d.lft and new_parent.rgt < d.rgt:
            raise HTTPException(400, "不能将部门移到自身的后代之下")

        # 删插：先记下当前 lft/rgt
        old_lft, old_rgt = d.lft, d.rgt
        subtree_width = old_rgt - old_lft + 1

        # 1. 在新位置插入（先计算新 lft/rgt）
        target_rgt = new_parent.rgt
        new_lft, new_rgt = _next_lft_rgt(db, target_rgt)

        # 2. 把子树整体移动到新位置（UPDATE 只移动区间内节点）
        #    先把子树从原位置"提取"：lft/rgt 收缩 subtree_width
        #    但更简单的做法是：删插（删子树，重插到新位置）
        _remove_subtree(db, old_lft, old_rgt)

        # 3. 现在 re-insert（因为删了子树，原来的 rgt 值已变）
        #    重新找 new_parent（因为它的 rgt 已在 _next_lft_rgt 里推移了）
        new_parent = db.query(Department).filter_by(name=body.parent).first()
        new_lft, new_rgt = _next_lft_rgt(db, new_parent.rgt)

        d.lft = new_lft
        d.rgt = new_rgt
        d.parent = body.parent
        changed = True

    if changed:
        db.commit()
        db.refresh(d)
    return {"data": _dept_to_dict(d, db), "message": "部门已更新"}


@router.delete("/Department/{name}", response_model=dict)
def delete_department(
    name: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
):
    """删除部门及其所有子部门（admin only）。根部门 D-ROOT 禁止删除。"""
    if name == "D-ROOT":
        raise HTTPException(400, "根部门 D-ROOT 禁止删除")

    d = db.query(Department).filter_by(name=name).first()
    if not d:
        raise HTTPException(404, "部门不存在")

    lft, rgt = d.lft, d.rgt
    count = db.query(Department).filter(
        Department.lft >= lft, Department.rgt <= rgt
    ).count()

    _remove_subtree(db, lft, rgt)
    return {"message": f"已删除部门 {name} 及 {count - 1} 个子部门", "deleted_count": count}
