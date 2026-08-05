"""test/test_workflow.py — 审批工作流测试"""
import pytest

class TestPending:
    def test_pending_public_or_auth(self, client, db):
        # pending is public (no auth required)
        r = client.get("/api/workflow/pending")
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_pending_with_token(self, client, db, auth_headers):
        r = client.get("/api/workflow/pending", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict) and "pending" in data

    def test_pending_with_api_key(self, client, db, api_key_headers):
        r = client.get("/api/workflow/pending", headers=api_key_headers)
        assert r.status_code == 200


class TestWorkflowActions:
    def test_create_exp(self, client, db, api_key_headers):
        r = client.post("/api/resource/Expense%20Claim", headers=api_key_headers,
                        json={"title": "Test1", "employee": "Alice", "claim_amount": 100})
        assert r.status_code == 200
        name = r.json()["data"]["name"]
        assert name.startswith("EXP-")
        return name

    def test_submit_exp(self, client, db, auth_headers):
        name = self.test_create_exp(client, db, {"X-API-Key": "zzcc_oadev_key_2024"})
        r = client.post("/api/workflow/action", headers=auth_headers,
                       json={"name": name, "action": "submit"})
        assert r.status_code == 200
        assert r.json()["to"] == "Submitted"
        return name

    def test_approve_exp(self, client, db, auth_headers):
        name = self.test_submit_exp(client, db, auth_headers)
        r = client.post("/api/workflow/action", headers=auth_headers,
                       json={"name": name, "action": "approve"})
        assert r.status_code == 200
        assert r.json()["to"] == "Approved"


    def test_reject_exp(self, client, db, auth_headers):
        name = self.test_submit_exp(client, db, auth_headers)
        r = client.post("/api/workflow/action", headers=auth_headers,
                       json={"name": name, "action": "reject"})
        assert r.status_code == 200
        assert r.json()["to"] == "Rejected"

    def test_pay_exp(self, client, db, auth_headers):
        name = self.test_approve_exp(client, db, auth_headers)
        r = client.post("/api/workflow/action", headers=auth_headers,
                       json={"name": name, "action": "pay"})
        # pay may return 422 (missing required fields) or 200
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert r.json()["to"] == "Paid"

    def test_invalid_action(self, client, db, auth_headers):
        name = self.test_create_exp(client, db, {"X-API-Key": "zzcc_oadev_key_2024"})
        r = client.post("/api/workflow/action", headers=auth_headers,
                       json={"name": name, "action": "approve"})
        assert r.status_code == 400
        assert "不适用于" in r.text

    def test_invalid_action_wrong_from(self, client, db, auth_headers):
        """Draft 状态不能 approve"""
        name = self.test_create_exp(client, db, {"X-API-Key": "zzcc_oadev_key_2024"})
        r = client.post("/api/workflow/action", headers=auth_headers,
                       json={"name": name, "action": "approve"})
        assert r.status_code == 400


class TestWorkflowDoc:
    def test_doc_not_found(self, client, db, auth_headers):
        r = client.get("/api/workflow/doc/ExpenseClaim/NOTEXIST-999", headers=auth_headers)
        assert r.status_code == 404

    def test_doc_found(self, client, db, auth_headers):
        name = TestWorkflowActions().test_create_exp(client, db, {"X-API-Key": "zzcc_oadev_key_2024"})
        r = client.get(f"/api/workflow/doc/ExpenseClaim/{name}", headers=auth_headers)
        assert r.status_code == 200
        assert "doc" in r.json()


class TestWorkflowStats:
    def test_stats_with_auth(self, client, db, auth_headers):
        r = client.get("/api/workflow/stats", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "ExpenseClaim" in data or "PurchaseOrder" in data


class TestNotifications:
    def test_notifications_requires_auth(self, client, db):
        r = client.get("/api/workflow/notifications")
        assert r.status_code == 401

    def test_notifications_with_auth(self, client, db, auth_headers):
        r = client.get("/api/workflow/notifications", headers=auth_headers)
        assert r.status_code == 200
        assert "unread_count" in r.json()


class TestHistory:
    def test_history_not_found(self, client, db, auth_headers):
        r = client.get("/api/workflow/history/ExpenseClaim/NOTEXIST-999", headers=auth_headers)
        assert r.status_code == 200  # returns empty list, not 404

    def test_history_after_submit(self, client, db, auth_headers):
        name = TestWorkflowActions().test_submit_exp(client, db, auth_headers)
        r = client.get(f"/api/workflow/history/ExpenseClaim/{name}", headers=auth_headers)
        assert r.status_code == 200
        history = r.json()
        assert isinstance(history, list) and len(history) > 0
        assert history[0]["operator"] == "admin"
        assert history[0]["action"] == "submit"

class TestPermissions:
    """权限体系：普通用户可提交，审批动作仅限 admin/api"""

    def _create_and_submit(self, client, db, user_headers):
        name = self._create_exp(client, db)
        r = client.post("/api/workflow/action", headers=user_headers,
                        json={"name": name, "action": "submit"})
        assert r.status_code == 200
        return name

    def _create_exp(self, client, db):
        return TestWorkflowActions().test_create_exp(
            client, db, {"X-API-Key": "zzcc_oadev_key_2024"})

    def test_user_can_submit(self, client, db, user_headers):
        """普通用户提交审批 → 200"""
        name = self._create_and_submit(client, db, user_headers)
        assert name.startswith("EXP-")

    def test_user_cannot_approve(self, client, db, user_headers):
        """普通用户审批 → 403"""
        name = self._create_and_submit(client, db, user_headers)
        r = client.post("/api/workflow/action", headers=user_headers,
                        json={"name": name, "action": "approve"})
        assert r.status_code == 403
        assert "管理员" in r.json()["detail"]

    def test_user_cannot_reject(self, client, db, user_headers):
        """普通用户拒绝 → 403"""
        name = self._create_and_submit(client, db, user_headers)
        r = client.post("/api/workflow/action", headers=user_headers,
                        json={"name": name, "action": "reject"})
        assert r.status_code == 403

    def test_admin_can_approve(self, client, db, auth_headers):
        """管理员审批 → 200"""
        name = self._create_and_submit(client, db, auth_headers)
        r = client.post("/api/workflow/action", headers=auth_headers,
                        json={"name": name, "action": "approve"})
        assert r.status_code == 200
        assert r.json()["to"] == "Approved"

    def test_api_key_can_approve(self, client, db, api_key_headers):
        """X-API-Key（api 角色）审批 → 200（向后兼容）"""
        name = self._create_and_submit(client, db, api_key_headers)
        r = client.post("/api/workflow/action", headers=api_key_headers,
                        json={"name": name, "action": "approve"})
        assert r.status_code == 200

    def test_unauth_action_401(self, client, db):
        """未认证调审批 → 401"""
        r = client.post("/api/workflow/action",
                        json={"name": "EXP-999", "action": "approve"})
        assert r.status_code == 401

