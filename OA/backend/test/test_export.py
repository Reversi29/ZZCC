"""test_export.py — P0.4 数据导出（Excel / CSV）"""
import pytest


def _make_exp(client, headers):
    r = client.post("/api/resource/Expense%20Claim", headers=headers,
                    json={"employee": "alice", "title": "差旅报销", "claim_amount": 100.0})
    assert r.status_code == 200
    return r.json()["data"]["name"]


def test_export_xlsx(client, auth_headers):
    _make_exp(client, auth_headers)
    r = client.get("/api/export/Expense%20Claim?format=xlsx", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    body = r.content
    assert body[:2] == b"PK", "xlsx 文件应以 PK 开头"
    assert len(body) > 0


def test_export_csv(client, auth_headers):
    _make_exp(client, auth_headers)
    r = client.get("/api/export/Expense%20Claim?format=csv", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8-sig")
    assert "employee" in text and "claim_amount" in text  # 表头
    assert "alice" in text  # 数据行


def test_export_unknown_doctype(client, auth_headers):
    r = client.get("/api/export/NotExists?format=xlsx", headers=auth_headers)
    assert r.status_code == 400


def test_export_requires_auth(client):
    r = client.get("/api/export/ExpenseClaim")
    assert r.status_code == 401
