"""test_seq.py — P0.1 单据编号规则测试"""
import pytest
from database import ExpenseClaim


def _mk(db, name, employee="alice"):
    db.add(ExpenseClaim(name=name, employee=employee))
    db.commit()


def test_seq_format_default_dept(db):
    """默认格式：{前缀}-DEFAULT-{YYYYMM}-0001"""
    from routers._db import seq_for
    name = seq_for("Expense Claim", db)
    assert name == "EXP-DEFAULT-202608-0001", name


def test_seq_increment_same_month(db):
    """同月同部门连续创建序号递增"""
    from routers._db import seq_for
    _mk(db, seq_for("Expense Claim", db))  # EXP-DEFAULT-202608-0001
    n2 = seq_for("Expense Claim", db)
    assert n2 == "EXP-DEFAULT-202608-0002", n2


def test_seq_month_reset(db):
    """跨月不继承上月序号：上月有 0005，本月仍从 0001 起"""
    from routers._db import seq_for
    _mk(db, "EXP-DEFAULT-202607-0005")  # 上月
    n = seq_for("Expense Claim", db)
    assert n == "EXP-DEFAULT-202608-0001", n


def test_seq_dept_dimension(db):
    """不同部门独立计数"""
    from routers._db import seq_for
    n_fin = seq_for("Expense Claim", db, dept="FIN")
    assert n_fin == "EXP-FIN-202608-0001", n_fin
    n_def = seq_for("Expense Claim", db, dept="DEFAULT")
    assert n_def == "EXP-DEFAULT-202608-0001", n_def


def test_seq_unknown_doctype(db):
    """未知 doctype 回退原行为"""
    from routers._db import seq_for
    assert seq_for("Weird Type", db) == "WeirdType-001"
