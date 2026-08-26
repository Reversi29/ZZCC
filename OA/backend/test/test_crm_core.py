"""test/test_crm_core.py — CRM 核心 CRUD 测试（Lead/Contact/Opportunity）"""
import pytest

API_KEY_HEADERS = {"X-API-Key": "zzcc_oadev_key_2024"}


class TestLead:
    def test_list_leads(self, client, db):
        r = client.get("/api/resource/Lead", headers=API_KEY_HEADERS)
        assert r.status_code == 200

    def test_create_lead(self, client, db):
        r = client.post("/api/resource/Lead", headers=API_KEY_HEADERS,
                        json={"name": "LD-TEST-001", "lead_name": "测试线索", "status": "Open"})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "LD-TEST-001"
        r2 = client.get("/api/resource/Lead/LD-TEST-001", headers=API_KEY_HEADERS)
        assert r2.json()["data"]["lead_name"] == "测试线索"

    def test_create_lead_auto_seq(self, client, db):
        r = client.post("/api/resource/Lead", headers=API_KEY_HEADERS,
                        json={"lead_name": "自动线索"})
        assert r.status_code == 200
        assert r.json()["data"]["name"].startswith("LEAD")

    def test_get_lead_not_found(self, client, db):
        r = client.get("/api/resource/Lead/NOTEXIST", headers=API_KEY_HEADERS)
        assert r.status_code == 404

    def test_update_lead(self, client, db):
        client.post("/api/resource/Lead", headers=API_KEY_HEADERS,
                    json={"name": "LD-UPD-001", "lead_name": "待改"})
        r2 = client.put("/api/resource/Lead/LD-UPD-001", headers=API_KEY_HEADERS,
                        json={"lead_name": "已改", "status": "Qualified"})
        assert r2.status_code == 200
        r3 = client.get("/api/resource/Lead/LD-UPD-001", headers=API_KEY_HEADERS)
        assert r3.json()["data"]["lead_name"] == "已改"

    def test_delete_lead(self, client, db):
        client.post("/api/resource/Lead", headers=API_KEY_HEADERS,
                    json={"name": "LD-DEL-001", "lead_name": "待删"})
        r2 = client.delete("/api/resource/Lead/LD-DEL-001", headers=API_KEY_HEADERS)
        assert r2.status_code == 200


class TestContact:
    def test_create_contact(self, client, db):
        r = client.post("/api/resource/Contact", headers=API_KEY_HEADERS,
                        json={"name": "CT-TEST-001", "first_name": "张"})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "CT-TEST-001"

    def test_list_contacts(self, client, db):
        r = client.get("/api/resource/Contact", headers=API_KEY_HEADERS)
        assert r.status_code == 200

    def test_get_contact(self, client, db):
        client.post("/api/resource/Contact", headers=API_KEY_HEADERS,
                    json={"name": "CT-GET-001", "first_name": "李"})
        r2 = client.get("/api/resource/Contact/CT-GET-001", headers=API_KEY_HEADERS)
        assert r2.status_code == 200


class TestOpportunity:
    def test_create_opportunity(self, client, db):
        r = client.post("/api/resource/Opportunity", headers=API_KEY_HEADERS,
                        json={"name": "OPP-TEST-001", "opportunity_name": "测试商机", "amount": 50000.0})
        assert r.status_code == 200
        r2 = client.get("/api/resource/Opportunity/OPP-TEST-001", headers=API_KEY_HEADERS)
        assert r2.json()["data"]["opportunity_name"] == "测试商机"

    def test_list_opportunities(self, client, db):
        r = client.get("/api/resource/Opportunity", headers=API_KEY_HEADERS)
        assert r.status_code == 200

    def test_delete_opportunity(self, client, db):
        client.post("/api/resource/Opportunity", headers=API_KEY_HEADERS,
                    json={"name": "OPP-DEL-001", "opportunity_name": "del"})
        r2 = client.delete("/api/resource/Opportunity/OPP-DEL-001", headers=API_KEY_HEADERS)
        assert r2.status_code == 200


class TestCRMRequiresAuth:
    def test_no_auth(self, client, db):
        r = client.get("/api/resource/Lead")
        assert r.status_code == 401