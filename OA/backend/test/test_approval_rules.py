"""test_approval_rules.py — P1.3 审批规则配置 CRUD"""


def _make_rule(client, headers):
    r = client.post("/api/approval-rules", headers=headers, json={
        "doctype": "ExpenseClaim", "level": 1, "approver_role": "admin",
    })
    assert r.status_code == 201, r.text
    lst = client.get("/api/approval-rules?doctype=ExpenseClaim", headers=headers).json()
    return lst[0]["id"]


def test_admin_create_and_list_rule(client, auth_headers):
    rid = _make_rule(client, auth_headers)
    lst = client.get("/api/approval-rules?doctype=ExpenseClaim", headers=auth_headers)
    assert lst.status_code == 200
    assert any(x["doctype"] == "ExpenseClaim" and x["level"] == 1 and x["id"] == rid for x in lst.json())


def test_user_cannot_create_rule(client, user_headers):
    r = client.post("/api/approval-rules", headers=user_headers, json={
        "doctype": "ExpenseClaim", "level": 1,
    })
    assert r.status_code == 403


def test_delete_rule(client, auth_headers):
    rid = _make_rule(client, auth_headers)
    r = client.delete(f"/api/approval-rules/{rid}", headers=auth_headers)
    assert r.status_code == 200
    lst = client.get("/api/approval-rules?doctype=ExpenseClaim", headers=auth_headers).json()
    assert all(x["id"] != rid for x in lst)
