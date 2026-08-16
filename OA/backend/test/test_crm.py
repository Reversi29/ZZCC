"""test/test_crm.py — P2.10 CRM 模块（数据隔离 + 合同审批流）"""
import pytest


class TestCRMOwnerIsolation:
    """销售只看自己客户：user 只看 owner==自己 或 owner IS NULL；admin 看全部"""

    def test_user_sees_own_lead(self, client, user_headers):
        r = client.post("/api/resource/Lead", json={"lead_name": "隔离测试A"}, headers=user_headers)
        assert r.status_code == 200
        name = r.json()["data"]["name"]
        lst = client.get("/api/resource/Lead", headers=user_headers).json()["data"]["data"]
        assert any(x["name"] == name for x in lst)

    def test_user_cannot_see_admin_lead(self, client, auth_headers, user_headers):
        # admin 创建
        r = client.post("/api/resource/Lead", json={"lead_name": "管理员线索"}, headers=auth_headers)
        assert r.status_code == 200
        admin_name = r.json()["data"]["name"]
        # user 列表不应包含 owner=admin 的记录
        lst = client.get("/api/resource/Lead", headers=user_headers).json()["data"]["data"]
        assert not any(x["name"] == admin_name for x in lst)

    def test_admin_sees_all_leads(self, client, auth_headers, user_headers):
        r = client.post("/api/resource/Lead", json={"lead_name": "员工线索"}, headers=user_headers)
        assert r.status_code == 200
        user_name = r.json()["data"]["name"]
        lst = client.get("/api/resource/Lead", headers=auth_headers).json()["data"]["data"]
        assert any(x["name"] == user_name for x in lst)

    def test_contact_owner_isolation(self, client, auth_headers, user_headers):
        r = client.post("/api/resource/Contact", json={"first_name": "员", "last_name": "工"}, headers=user_headers)
        assert r.status_code == 200
        cname = r.json()["data"]["name"]
        # admin 创建的 contact，user 看不到
        r2 = client.post("/api/resource/Contact", json={"first_name": "管", "last_name": "理"}, headers=auth_headers)
        admin_cname = r2.json()["data"]["name"]
        lst = client.get("/api/resource/Contact", headers=user_headers).json()["data"]["data"]
        assert any(x["name"] == cname for x in lst)
        assert not any(x["name"] == admin_cname for x in lst)

    def test_opportunity_owner_isolation(self, client, auth_headers, user_headers):
        r = client.post("/api/resource/Opportunity", json={"opportunity_name": "商机A", "amount": 100}, headers=user_headers)
        assert r.status_code == 200
        oname = r.json()["data"]["name"]
        lst = client.get("/api/resource/Opportunity", headers=user_headers).json()["data"]["data"]
        assert any(x["name"] == oname for x in lst)


class TestContractApproval:
    """合同关联审批流：Draft → Submitted → Approved"""

    def _create(self, client, headers):
        r = client.post("/api/resource/Contract", json={
            "contract_name": "测试合同",
            "party_a": "甲方公司",
            "party_b": "乙方公司",
            "contract_value": 50000,
        }, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()["data"]["name"]

    def test_contract_default_draft(self, client, auth_headers):
        name = self._create(client, auth_headers)
        g = client.get(f"/api/resource/Contract/{name}", headers=auth_headers).json()["data"]
        assert g["status"] == "Draft"

    def test_contract_approval_flow(self, client, auth_headers):
        name = self._create(client, auth_headers)
        # submit
        r = client.post("/api/workflow/action", json={
            "doctype": "Contract", "action": "submit", "name": name
        }, headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["to"] == "Submitted"
        # approve
        r2 = client.post("/api/workflow/action", json={
            "doctype": "Contract", "action": "approve", "name": name
        }, headers=auth_headers)
        assert r2.status_code == 200, r2.text
        assert r2.json()["to"] == "Approved"

    def test_contract_in_pending_list(self, client, auth_headers):
        name = self._create(client, auth_headers)
        client.post("/api/workflow/action", json={
            "doctype": "Contract", "action": "submit", "name": name
        }, headers=auth_headers)
        pend = client.get("/api/workflow/pending", headers=auth_headers).json()
        contracts = [p for p in pend.get("pending", []) if p.get("doctype") == "Contract"]
        assert any(c["name"] == name for c in contracts)
