"""test_delegation.py — P1.4 审批代理人（Delegation）"""
from database import ApprovalRule, Delegation


def _create_exp(client, headers):
    r = client.post("/api/resource/Expense%20Claim", headers=headers,
                    json={"employee": "alice", "title": "差旅报销", "claim_amount": 100.0})
    assert r.status_code == 200
    return r.json()["data"]["name"]


def _seed_rules(db, levels=("admin",)):
    for i, role in enumerate(levels, start=1):
        db.add(ApprovalRule(doctype="ExpenseClaim", level=i, approver_role=role))
    db.commit()


def test_delegate_can_approve(client, db, user_headers):
    """alice（user）被 admin 委托后，可代 admin 审批 ExpenseClaim"""
    _seed_rules(db, levels=("admin",))
    db.add(Delegation(grantor="admin", delegate="alice", doctype="ExpenseClaim"))
    db.commit()

    name = _create_exp(client, user_headers)
    r = client.post("/api/workflow/action", headers=user_headers,
                    json={"name": name, "action": "submit"})
    assert r.json()["to"] == "Submitted"
    # alice 作为 admin 的代理人审批（规则要求 admin 角色）
    r = client.post("/api/workflow/action", headers=user_headers,
                    json={"name": name, "action": "approve"})
    assert r.json()["to"] == "Approved"


def test_non_delegate_blocked(client, db, user_headers):
    """未被委托的普通用户审批 admin 级 → 403"""
    _seed_rules(db, levels=("admin",))
    db.commit()
    name = _create_exp(client, user_headers)
    client.post("/api/workflow/action", headers=user_headers,
                json={"name": name, "action": "submit"})
    r = client.post("/api/workflow/action", headers=user_headers,
                    json={"name": name, "action": "approve"})
    assert r.status_code == 403
