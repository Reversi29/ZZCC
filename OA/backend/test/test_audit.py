"""test_audit.py — P0.3 操作审计日志增强（field_changes 结构化）"""
import json


def _create_and_submit(client, headers):
    r = client.post("/api/resource/Expense%20Claim", headers=headers,
                    json={"employee": "alice", "title": "差旅报销", "claim_amount": 100.0})
    name = r.json()["data"]["name"]
    client.post("/api/workflow/action", headers=headers,
                json={"name": name, "action": "submit", "comment": "提交"})
    return name


def test_history_records_status_change(client, auth_headers):
    """审批动作后审计记录含 status 字段变更明细"""
    name = _create_and_submit(client, auth_headers)
    # admin 审批
    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "approve", "comment": "同意"})
    assert r.status_code == 200

    # 查审批历史
    h = client.get(f"/api/workflow/history/ExpenseClaim/{name}", headers=auth_headers)
    assert h.status_code == 200
    rows = h.json()
    # 至少两条：submit + approve
    assert len(rows) >= 2
    # approve 那条应含 field_changes
    approve_row = next(x for x in rows if x["action"] == "approve")
    fc = json.loads(approve_row["field_changes"])
    assert fc["status"]["from"] == "Submitted"
    assert fc["status"]["to"] == "Approved"


def test_history_operator_and_comment(client, auth_headers):
    """审计含操作人与备注"""
    name = _create_and_submit(client, auth_headers)
    h = client.get(f"/api/workflow/history/ExpenseClaim/{name}", headers=auth_headers).json()
    submit_row = next(x for x in h if x["action"] == "submit")
    assert submit_row["operator"] == "admin"
    assert submit_row["comment"] == "提交"
