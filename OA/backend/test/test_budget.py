"""test_budget.py — P1.5 预算控制"""
from datetime import datetime
from database import Budget


def _create_exp(client, headers, amount):
    r = client.post("/api/resource/Expense%20Claim", headers=headers, json={
        "employee": "alice", "title": "差旅报销", "claim_amount": amount,
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]["name"]


def test_over_budget_blocked(client, db, user_headers):
    """提交金额超出月度预算 → 400"""
    period = datetime.utcnow().strftime("%Y-%m")
    db.add(Budget(doctype="ExpenseClaim", period=period, limit_amount=1000.0, used_amount=0.0))
    db.commit()
    name = _create_exp(client, user_headers, 1500.0)
    r = client.post("/api/workflow/action", headers=user_headers,
                    json={"name": name, "action": "submit"})
    assert r.status_code == 400
    assert "预算" in r.json()["detail"]


def test_under_budget_ok_and_consume(client, db, user_headers, auth_headers):
    """预算内提交通过，审批通过后扣减 used"""
    period = datetime.utcnow().strftime("%Y-%m")
    db.add(Budget(doctype="ExpenseClaim", period=period, limit_amount=5000.0, used_amount=0.0))
    db.commit()
    name = _create_exp(client, user_headers, 1500.0)
    r = client.post("/api/workflow/action", headers=user_headers,
                    json={"name": name, "action": "submit"})
    assert r.status_code == 200
    # admin 审批通过
    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "approve"})
    assert r.json()["to"] == "Approved"
    # 预算已扣减
    b = db.query(Budget).filter_by(doctype="ExpenseClaim", period=period).first()
    assert abs(b.used_amount - 1500.0) < 0.01
