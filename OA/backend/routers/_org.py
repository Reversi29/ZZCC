"""routers/_org.py — 组织架构查询辅助（Nested Set Model）

所有函数接受 `db: Session` + 目标 department_id，查询粒度分为三层：

  get_department(dept_name)        — 精确查一个部门（含 ext JSON 解析）
  get_subdepartments(db, dept)    — 查某部门所有直接下级（parent = dept_name）
  get_ancestors(db, dept_name)    — 查根→当前部门的路径（ORDER BY lft）
  is_descendant_of(db, child, ancestor) — child 是否是 ancestor 的下级（含自身）
  budget_for(db, doctype, period, department_id) — 预算查法：先部门后全局

使用示例：
  dept = get_department(db, "研发部")
  subs = get_subdepartments(db, "研发部")
  ancestors = get_ancestors(db, "研发部")
  budget = budget_for(db, "ExpenseClaim", "2026-08", "研发部")
"""
from sqlalchemy.orm import Session
import json

from database import Department, Budget


# ── 部门基础查询 ───────────────────────────────────────────────

def get_department(db: Session, dept_name: str | None):
    """返回 Department 对象（含 ext JSON 解析），dept_name=None 返回 None"""
    if not dept_name:
        return None
    dept = db.query(Department).filter_by(name=dept_name).first()
    if dept and dept.ext:
        try:
            dept._ext_cache = json.loads(dept.ext)
        except Exception:
            dept._ext_cache = {}
    return dept


def get_subdepartments(db: Session, dept_name: str) -> list[Department]:
    """返回 dept_name 的直接下级部门列表"""
    return db.query(Department).filter_by(parent=dept_name).order_by(Department.lft).all()


def get_ancestors(db: Session, dept_name: str) -> list[Department]:
    """返回根部门→dept_name 整条路径，按 lft 升序（即从根到叶）"""
    dept = get_department(db, dept_name)
    if not dept:
        return []
    return (
        db.query(Department)
          .filter(Department.lft <= dept.lft, Department.rgt >= dept.rgt)
          .order_by(Department.lft)
          .all()
    )


def is_descendant_of(db: Session, child_name: str, ancestor_name: str) -> bool:
    """判断 child_name 是否是 ancestor_name 的下级（ancestor_name 本身也算）"""
    child = get_department(db, child_name)
    ancestor = get_department(db, ancestor_name)
    if not child or not ancestor:
        return False
    return ancestor.lft <= child.lft and child.rgt <= ancestor.rgt


# ── 预算查询 ──────────────────────────────────────────────────

def budget_for(db: Session, doctype: str, period: str, department_id: str | None):
    """
    预算查询策略（优先级递减）：
      1. doctype + period + department_id  → 部门级预算
      2. doctype + period + NULL           → 全公司预算（兜底）
      3. 无记录                             → None（不限制）
    """
    budget = db.query(Budget).filter_by(
        doctype=doctype, period=period, department_id=department_id
    ).first()
    if budget:
        return budget
    if department_id is not None:
        budget = db.query(Budget).filter_by(
            doctype=doctype, period=period, department_id=None
        ).first()
    return budget


# ── 种子数据（可选，供 init_db 调用）───────────────────────────

def seed_default_departments(db: Session):
    """写入默认部门树（如果表为空）"""
    if db.query(Department).count() > 0:
        return
    # Nested Set: ZZCC（1,14）
    #   ├── 总裁办（2,3）
    #   ├── 财务部（4,7）
    #   │   ├── 会计（5,6）
    #   └── 运营部（8,13）
    #       ├── 销售（9,10）
    #       └── 行政（11,12）
    defaults = [
        ("D-ROOT", "ZZCC",         None,  1, 14, "ZZCC", False, None),
        ("D-CEO",  "总裁办",       "D-ROOT", 2,  3, "ZZCC", False, None),
        ("D-FIN",  "财务部",       "D-ROOT", 4,  7, "ZZCC", False, None),
        ("D-ACT",  "会计",         "D-FIN",  5,  6, "ZZCC", False, None),
        ("D-OPS",  "运营部",       "D-ROOT", 8, 13, "ZZCC", False, None),
        ("D-SALES","销售部",       "D-OPS",  9, 10, "ZZCC", False, None),
        ("D-ADMIN","行政部",       "D-OPS", 11, 12, "ZZCC", False, None),
    ]
    for row in defaults:
        db.add(Department(
            name=row[0], department_name=row[1], parent=row[2],
            lft=row[3], rgt=row[4], company=row[5], is_group=row[6], ext=row[7],
        ))
    db.commit()
    print("[init] Default departments seeded: D-ROOT→D-ADMIN (7 nodes)")
