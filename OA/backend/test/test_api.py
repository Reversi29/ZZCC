"""test/test_api.py — 通用 API 路由测试"""
import pytest

class TestStatus:
    def test_status_public(self, client, db):
        r = client.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "persistence" in data


class TestResourceCreate:
    def test_create_expense_claim(self, client, db, api_key_headers):
        r = client.post("/api/resource/Expense%20Claim", headers=api_key_headers,
                        json={"title": "差旅报销", "employee": "Alice", "claim_amount": 500.0})
        assert r.status_code == 200
        assert "data" in r.json()
        assert "name" in r.json()["data"]

    def test_create_purchase_order(self, client, db, api_key_headers):
        r = client.post("/api/resource/Purchase%20Order", headers=api_key_headers,
                        json={"supplier": "文具店", "total": 3000.0})
        assert r.status_code == 200

    def test_create_journal_entry(self, client, db, api_key_headers):
        # JournalEntry 需要借贷平衡的分录
        r = client.post("/api/resource/Journal%20Entry", headers=api_key_headers,
                        json={
                            "title": "凭证测试",
                            "accounts": [
                                {"account": "银行", "debit": 1000, "credit": 0},
                                {"account": "管理费用", "debit": 0, "credit": 1000},
                            ]
                        })
        assert r.status_code == 200

    def test_create_unknown_resource(self, client, db, api_key_headers):
        r = client.post("/api/resource/UnknownType", headers=api_key_headers,
                        json={"foo": "bar"})
        # returns 405 Method Not Allowed (route not registered) or 404
        assert r.status_code in (404, 405)
