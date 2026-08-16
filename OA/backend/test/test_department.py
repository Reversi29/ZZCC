"""test_department.py — P1.7 组织架构与数据隔离"""
from sqlalchemy import or_
import pytest
from database import Department, User, Budget, ApprovalRule


def _make_tree(db):
    """建立测试用部门树（NSM）：
    ZZCC(lft=1,rgt=14)
      ├─ D-CEO  (2, 3)
      ├─ D-FIN  (4, 7)
      │   └─ D-ACT  (5, 6)
      └─ D-OPS  (8, 13)
          ├─ D-SALES (9,10)
          └─ D-ADMIN (11,12)
    """
    rows = [
        ("D-ROOT",  "ZZCC",     None,  1, 14),
        ("D-CEO",   "总裁办",  "D-ROOT", 2,  3),
        ("D-FIN",   "财务部",  "D-ROOT", 4,  7),
        ("D-ACT",   "会计组",  "D-FIN",  5,  6),
        ("D-OPS",   "运营部",  "D-ROOT", 8, 13),
        ("D-SALES", "销售部",  "D-OPS",  9, 10),
        ("D-ADMIN", "行政部",  "D-OPS", 11, 12),
    ]
    for name, dept_name, parent, lft, rgt in rows:
        db.add(Department(
            name=name, department_name=dept_name, parent=parent,
            lft=lft, rgt=rgt, company="ZZCC",
        ))
    db.commit()


class TestDepartmentModel:
    def test_tree_structure(self, db):
        """NSM 区间正确：子节点包含在父节点 lft/rgt 内"""
        _make_tree(db)
        ops = db.query(Department).filter_by(name="D-OPS").first()
        # 所有祖先
        ancestors = (
            db.query(Department)
              .filter(Department.lft <= ops.lft, Department.rgt >= ops.rgt)
              .order_by(Department.lft)
              .all()
        )
        names = [d.name for d in ancestors]
        assert names == ["D-ROOT", "D-OPS"]
        # 查所有后代（含自身）
        descendants = (
            db.query(Department)
              .filter(Department.lft >= ops.lft, Department.rgt <= ops.rgt)
              .order_by(Department.lft)
              .all()
        )
        assert [d.name for d in descendants] == ["D-OPS", "D-SALES", "D-ADMIN"]

    def test_ext_json(self, db):
        """ext JSON 列可存储成本中心等额外字段"""
        db.add(Department(
            name="D-DEV", department_name="研发部",
            lft=100, rgt=101, company="ZZCC",
            ext='{"cost_center":"CC001","approval_limit":50000}',
        ))
        db.commit()
        dept = db.query(Department).filter_by(name="D-DEV").first()
        import json
        assert json.loads(dept.ext)["cost_center"] == "CC001"


class TestOrgHelper:
    def test_get_department(self, db):
        _make_tree(db)
        from routers._org import get_department
        fin = get_department(db, "D-FIN")
        assert fin.department_name == "财务部"
        assert fin.parent == "D-ROOT"
        # 不存在的部门
        assert get_department(db, "D-NOEXIST") is None
        assert get_department(db, None) is None

    def test_get_subdepartments(self, db):
        _make_tree(db)
        from routers._org import get_subdepartments
        subs = get_subdepartments(db, "D-OPS")
        assert {s.name for s in subs} == {"D-SALES", "D-ADMIN"}
        # 叶子节点无下级
        subs_leaf = get_subdepartments(db, "D-ACT")
        assert subs_leaf == []

    def test_get_ancestors(self, db):
        _make_tree(db)
        from routers._org import get_ancestors
        path = get_ancestors(db, "D-ACT")
        assert [d.name for d in path] == ["D-ROOT", "D-FIN", "D-ACT"]

    def test_is_descendant(self, db):
        _make_tree(db)
        from routers._org import is_descendant_of
        assert is_descendant_of(db, "D-ACT",    "D-ROOT") is True
        assert is_descendant_of(db, "D-ACT",    "D-FIN")  is True
        assert is_descendant_of(db, "D-ACT",    "D-ACT")  is True   # 含自身
        assert is_descendant_of(db, "D-SALES",  "D-FIN")  is False
        assert is_descendant_of(db, "D-SALES",  "D-ROOT") is True
        assert is_descendant_of(db, "D-ROOT",   "D-SALES") is False
        assert is_descendant_of(db, "D-NOEXIST","D-ROOT") is False

    def test_budget_for_fallback(self, db):
        """部门级预算不存在时回退到全局预算"""
        from routers._org import budget_for
        # 写全局预算
        db.add(Budget(doctype="ExpenseClaim", period="2026-08",
                      department_id=None, limit_amount=10000, used_amount=0))
        db.commit()
        # 无部门预算 → 用全局
        b = budget_for(db, "ExpenseClaim", "2026-08", "D-FIN")
        assert b is not None and b.limit_amount == 10000
        # 有部门预算 → 用部门级
        db.add(Budget(doctype="ExpenseClaim", period="2026-08",
                      department_id="D-FIN", limit_amount=5000, used_amount=0))
        db.commit()
        b2 = budget_for(db, "ExpenseClaim", "2026-08", "D-FIN")
        assert b2.limit_amount == 5000

    def test_budget_for_no_budget_record(self, db):
        """无任何预算记录 → None（不限制）"""
        from routers._org import budget_for
        assert budget_for(db, "ExpenseClaim", "2026-08", "D-FIN") is None


class TestUserDepartmentFK:
    def test_user_belongs_to_department(self, db):
        """用户通过 department_id FK 关联部门"""
        _make_tree(db)
        # 写一个属于 D-FIN 的用户
        db.add(User(
            username="fin_user1",
            hashed_password="dummy",
            display_name="财务小李",
            role="user",
            department_id="D-FIN",
        ))
        db.commit()
        u = db.query(User).filter_by(username="fin_user1").first()
        assert u.department_id == "D-FIN"
        fin = db.query(Department).filter_by(name="D-FIN").first()
        assert fin is not None

    def test_user_department_null(self, db):
        """旧用户（admin/user01）的 department_id 为 NULL，不影响功能"""
        db.add(User(
            username="bob",
            hashed_password="dummy",
            display_name="临时工",
            role="user",
            department_id=None,
        ))
        db.commit()
        u = db.query(User).filter_by(username="bob").first()
        assert u.department_id is None

    def test_user_ext_json(self, db):
        """ext JSON 列可存 title/phone/manager 等扩展字段"""
        db.add(User(
            username="carol",
            hashed_password="dummy",
            display_name="Carol",
            role="user",
            ext='{"title":"高级会计","phone":"13800001111","manager":"alice"}',
        ))
        db.commit()
        u = db.query(User).filter_by(username="carol").first()
        import json
        assert json.loads(u.ext)["title"] == "高级会计"


class TestApprovalRuleDepartment:
    def test_global_rule_applies_to_all(self, db):
        """department_id=NULL 的全局规则对任何部门生效"""
        _make_tree(db)
        db.add(ApprovalRule(
            doctype="ExpenseClaim", department_id=None,
            level=1, approver_role="admin",
        ))
        db.commit()
        rules = (
            db.query(ApprovalRule)
              .filter_by(doctype="ExpenseClaim", level=1)
              .filter(or_(ApprovalRule.department_id == "D-FIN", ApprovalRule.department_id.is_(None)))
              .order_by(ApprovalRule.department_id.desc())
              .all()
        )
        assert len(rules) >= 1

    def test_dept_rule_preferred_over_global(self, db):
        """同 level，部门专用规则优先于全局规则"""
        _make_tree(db)
        db.add(ApprovalRule(
            doctype="ExpenseClaim", department_id=None,
            level=1, approver_role="admin",
        ))
        db.add(ApprovalRule(
            doctype="ExpenseClaim", department_id="D-FIN",
            level=1, approver_role="finance_manager",
        ))
        db.commit()
        rules = (
            db.query(ApprovalRule)
              .filter_by(doctype="ExpenseClaim", level=1)
              .filter(or_(ApprovalRule.department_id == "D-FIN", ApprovalRule.department_id.is_(None)))
              .order_by(ApprovalRule.department_id.desc(), ApprovalRule.level)
              .all()
        )
        assert rules[0].department_id == "D-FIN"
        assert rules[0].approver_role == "finance_manager"
        assert len(rules) == 2
