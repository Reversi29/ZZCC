"""test_approval.py — P1.2 多级审批流引擎"""
from database import ApprovalRule


def _create_exp(client, headers):
    r = client.post("/api/resource/Expense%20Claim", headers=headers,
                    json={"employee": "alice", "title": "差旅报销", "claim_amount": 100.0})
    assert r.status_code == 200
    return r.json()["data"]["name"]


def _seed_rules(db, doctype="ExpenseClaim", levels=("admin", "admin")):
    for i, role in enumerate(levels, start=1):
        db.add(ApprovalRule(doctype=doctype, level=i, approver_role=role))
    db.commit()


def test_two_level_approval(client, db, auth_headers):
    """两级审批：submit → approve(L1) → Pending-L2 → approve(L2) → Approved"""
    _seed_rules(db, levels=("admin", "admin"))
    name = _create_exp(client, auth_headers)

    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "submit"})
    assert r.status_code == 200
    assert r.json()["to"] == "Submitted"

    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "approve"})
    assert r.json()["to"] == "Pending-L2"

    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "approve"})
    assert r.json()["to"] == "Approved"


def test_single_level_rule(client, db, auth_headers):
    """单级规则：submit → approve → Approved（直接终态）"""
    _seed_rules(db, levels=("admin",))
    name = _create_exp(client, auth_headers)
    client.post("/api/workflow/action", headers=auth_headers,
                json={"name": name, "action": "submit"})
    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "approve"})
    assert r.json()["to"] == "Approved"


def test_reject_in_multilevel(client, db, auth_headers):
    """多级中任意级 reject → Rejected"""
    _seed_rules(db, levels=("admin", "admin"))
    name = _create_exp(client, auth_headers)
    client.post("/api/workflow/action", headers=auth_headers,
                json={"name": name, "action": "submit"})
    client.post("/api/workflow/action", headers=auth_headers,
                json={"name": name, "action": "approve"})  # → Pending-L2
    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "reject"})
    assert r.json()["to"] == "Rejected"


def test_level_role_enforced(client, db, user_headers, auth_headers):
    """某级要求 manager 角色，普通 user 审批 → 403"""
    _seed_rules(db, levels=("admin", "manager"))
    name = _create_exp(client, user_headers)
    client.post("/api/workflow/action", headers=user_headers,
                json={"name": name, "action": "submit"})
    # L1 需 admin，user 审批被拒
    r = client.post("/api/workflow/action", headers=user_headers,
                    json={"name": name, "action": "approve"})
    assert r.status_code == 403
    # admin 过 L1
    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "approve"})
    assert r.json()["to"] == "Pending-L2"
    # L2 需 manager，admin 可代批（admin 放行）
    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "approve"})
    assert r.json()["to"] == "Approved"
