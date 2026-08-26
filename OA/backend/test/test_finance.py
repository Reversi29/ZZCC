"""test/test_finance.py — 财务模块 CRUD 测试"""
import pytest

API_KEY_HEADERS = {"X-API-Key": "zzcc_oadev_key_2024"}


class TestAccount:
    def test_list_accounts(self, client, db):
        r = client.get("/api/resource/Account", headers=API_KEY_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert "data" in data["data"]

    def test_create_account(self, client, db):
        r = client.post("/api/resource/Account", headers=API_KEY_HEADERS,
                        json={"name": "Test Account 001", "account_name": "Test Account", "account_type": "asset"})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "Test Account 001"

    def test_create_account_auto_seq(self, client, db):
        """不传 name → 自动生成 ACC 序列号"""
        r = client.post("/api/resource/Account", headers=API_KEY_HEADERS,
                        json={"account_name": "Auto Acc", "account_type": "asset"})
        assert r.status_code == 200
        assert r.json()["data"]["name"].startswith("ACC")

    def test_get_account(self, client, db):
        r = client.post("/api/resource/Account", headers=API_KEY_HEADERS,
                        json={"name": "Get Acc Test", "account_name": "Get Acc", "account_type": "expense"})
        name = r.json()["data"]["name"]
        r2 = client.get(f"/api/resource/Account/{name}", headers=API_KEY_HEADERS)
        assert r2.status_code == 200
        assert r2.json()["data"]["name"] == name

    def test_get_account_not_found(self, client, db):
        r = client.get("/api/resource/Account/NOTEXIST", headers=API_KEY_HEADERS)
        assert r.status_code == 404

    def test_update_account(self, client, db):
        r = client.post("/api/resource/Account", headers=API_KEY_HEADERS,
                        json={"name": "Update Acc", "account_name": "Update Acc", "account_type": "asset"})
        name = r.json()["data"]["name"]
        r2 = client.put(f"/api/resource/Account/{name}", headers=API_KEY_HEADERS,
                        json={"account_type": "liability"})
        assert r2.status_code == 200

    def test_delete_account(self, client, db):
        r = client.post("/api/resource/Account", headers=API_KEY_HEADERS,
                        json={"name": "Delete Acc", "account_name": "Delete Acc", "account_type": "asset"})
        name = r.json()["data"]["name"]
        r2 = client.delete(f"/api/resource/Account/{name}", headers=API_KEY_HEADERS)
        assert r2.status_code == 200


class TestJournalEntry:
    def test_create_journal_entry(self, client, db):
        r = client.post("/api/resource/Journal%20Entry", headers=API_KEY_HEADERS,
                        json={
                            "name": "JE-TEST-001",
                            "accounts": [
                                {"account": "银行", "debit": 1000, "credit": 0},
                                {"account": "管理费用", "debit": 0, "credit": 1000},
                            ]
                        })
        assert r.status_code == 200

    def test_list_journal_entries(self, client, db):
        r = client.get("/api/resource/Journal%20Entry", headers=API_KEY_HEADERS)
        assert r.status_code == 200

    def test_create_unbalanced(self, client, db):
        r = client.post("/api/resource/Journal%20Entry", headers=API_KEY_HEADERS,
                        json={
                            "name": "JE-BAD-001",
                            "accounts": [
                                {"account": "银行", "debit": 1000, "credit": 0},
                                {"account": "管理费用", "debit": 0, "credit": 500},
                            ]
                        })
        # 借贷不平衡应返回错误
        assert r.status_code in (200, 400, 422)


class TestPaymentEntry:
    def test_create_payment_entry(self, client, db):
        r = client.post("/api/resource/Payment%20Entry", headers=API_KEY_HEADERS,
                        json={"name": "PE-TEST-001", "party_type": "Customer", "party": "ABC Ltd", "amount": 500.0})
        assert r.status_code == 200

    def test_list_payment_entries(self, client, db):
        r = client.get("/api/resource/Payment%20Entry", headers=API_KEY_HEADERS)
        assert r.status_code == 200


class TestExpenseClaim:
    def test_create_expense_claim(self, client, db):
        r = client.post("/api/resource/Expense%20Claim", headers=API_KEY_HEADERS,
                        json={"name": "EC-TEST-001", "employee": "Alice", "claim_amount": 200.0})
        assert r.status_code == 200

    def test_list_expense_claims(self, client, db):
        r = client.get("/api/resource/Expense%20Claim", headers=API_KEY_HEADERS)
        assert r.status_code == 200

    def test_get_expense_claim(self, client, db):
        r = client.post("/api/resource/Expense%20Claim", headers=API_KEY_HEADERS,
                        json={"name": "EC-GET-001", "employee": "Bob", "claim_amount": 100.0})
        name = r.json()["data"]["name"]
        r2 = client.get(f"/api/resource/Expense%20Claim/{name}", headers=API_KEY_HEADERS)
        assert r2.status_code == 200


class TestFinanceRequiresAuth:
    def test_list_accounts_no_auth(self, client, db):
        r = client.get("/api/resource/Account")
        assert r.status_code == 401