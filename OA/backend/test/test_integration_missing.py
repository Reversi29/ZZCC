"""test/test_integration_missing.py — 集成冒烟测试：覆盖 19 个无测试 router

复用 conftest.py 的 client/db/admin_token fixture。"""

import pytest


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


class TestAnnouncements:
    def test_get_list(self, client, auth_headers):
        r = client.get("/api/resource/Announcement", headers=auth_headers)
        assert r.status_code == 200 and "data" in r.json()

    def test_create_and_delete(self, client, auth_headers):
        r = client.post("/api/resource/Announcement",
                        json={"title": "T", "body": "C"}, headers=auth_headers)
        assert r.status_code == 200
        aid = r.json()["data"]["id"]
        assert client.delete(f"/api/resource/Announcement/{aid}", headers=auth_headers).status_code == 200


class TestCalendar:
    def test_events(self, client, auth_headers):
        r = client.get("/api/calendar/events", headers=auth_headers)
        assert r.status_code == 200


class TestCompliance:
    def test_contract_crud(self, client, auth_headers):
        r = client.post("/api/resource/Contract",
                        json={"contract_name": "TC", "party_a": "A", "party_b": "B", "amount": 100},
                        headers=auth_headers)
        assert r.status_code == 200 and "name" in r.json()["data"]


class TestCustomerService:
    def test_ticket_crud(self, client, auth_headers):
        r = client.post("/api/resource/Support Ticket",
                        json={"subject": "TT", "priority": "normal", "status": "open", "raised_by": "admin"},
                        headers=auth_headers)
        assert r.status_code == 200 and "name" in r.json()["data"]


class TestDailyReports:
    def test_crud(self, client, auth_headers):
        r = client.post("/api/reports/create",
                        json={"title": "T", "report_date": "2026-08-01", "content": "C", "author": "admin"},
                        headers=auth_headers)
        assert r.status_code == 200
        r2 = client.get("/api/reports/list", params={"report_type": "daily"}, headers=auth_headers)
        assert r2.status_code == 200


class TestDashboard:
    def test_quickstats(self, client, auth_headers):
        r = client.get("/api/dashboard/quickstats", headers=auth_headers)
        assert r.status_code == 200


class TestDirectory:
    def test_tree(self, client, auth_headers):
        r = client.get("/api/directory/tree", headers=auth_headers)
        assert r.status_code == 200

    def test_search(self, client, auth_headers):
        r = client.get("/api/directory/search?q=admin", headers=auth_headers)
        assert r.status_code == 200


class TestFinance:
    def test_account(self, client, auth_headers):
        r = client.post("/api/resource/Account",
                        json={"account_name": "TA", "type": "expense"}, headers=auth_headers)
        assert r.status_code == 200 and "name" in r.json()["data"]


class TestFormDesigner:
    def test_template_crud(self, client, auth_headers):
        r = client.post("/api/form-designer/templates",
                        json={"name": "TF", "schema": [{"type": "text", "name": "f1"}]},
                        headers=auth_headers)
        assert r.status_code == 200 and "id" in r.json()["data"]
        r2 = client.get("/api/form-designer/templates", headers=auth_headers)
        assert r2.status_code == 200


class TestMeetings:
    def test_create_and_delete(self, client, auth_headers):
        r = client.post("/api/meetings/create",
                        json={"title": "TM", "start_date": "2026-08-01", "location": "x"},
                        headers=auth_headers)
        assert r.status_code == 200
        mid = r.json()["data"]["id"]
        assert client.delete(f"/api/meetings/delete/{mid}", headers=auth_headers).status_code == 200


class TestModuleToggle:
    def test_status(self, client, auth_headers):
        r = client.get("/api/module-toggle/status", headers=auth_headers)
        assert r.status_code == 200 and "modules" in r.json()

    def test_list(self, client, auth_headers):
        r = client.get("/api/module-toggle/list", headers=auth_headers)
        assert r.status_code == 200


class TestNetDrive:
    def test_mkdir_and_list(self, client, auth_headers):
        r = client.post("/api/netdrive/mkdir", json={"name": "test_dir"}, headers=auth_headers)
        assert r.status_code == 200
        r2 = client.get("/api/netdrive/list", headers=auth_headers)
        assert r2.status_code == 200


class TestNotificationSettings:
    def test_get_settings(self, client, auth_headers):
        r = client.get("/api/notifications/settings", headers=auth_headers)
        assert r.status_code == 200

    def test_channels(self, client, auth_headers):
        r = client.get("/api/notifications/channels", headers=auth_headers)
        assert r.status_code == 200


class TestPerformance:
    def test_create_and_delete(self, client, auth_headers):
        r = client.post("/api/performance",
                        json={"employee_name": "Admin", "period": "2026Q3",
                              "manager_score": 4.0, "overall_score": 4.0, "status": "approved"},
                        headers=auth_headers)
        assert r.status_code == 200
        rid = r.json()["id"]
        assert client.delete(f"/api/performance/{rid}", headers=auth_headers).status_code == 204


class TestProcurement:
    def test_supplier(self, client, auth_headers):
        r = client.post("/api/resource/Supplier",
                        json={"supplier_name": "TS"}, headers=auth_headers)
        assert r.status_code == 200 and "name" in r.json()["data"]


class TestQuality:
    def test_inspection(self, client, auth_headers):
        r = client.post("/api/resource/Quality Inspection",
                        json={"title": "TQ", "result": "pass"}, headers=auth_headers)
        assert r.status_code == 200 and "name" in r.json()["data"]


class TestRecruitment:
    def test_create_and_delete(self, client, auth_headers):
        r = client.post("/api/recruitment",
                        json={"position": "TR", "headcount": 1, "status": "active"},
                        headers=auth_headers)
        assert r.status_code == 200
        rid = r.json()["id"]
        assert client.delete(f"/api/recruitment/{rid}", headers=auth_headers).status_code == 204


class TestSearch:
    def test_global(self, client, auth_headers):
        r = client.get("/api/search/global?q=test", headers=auth_headers)
        assert r.status_code == 200

    def test_suggestions(self, client, auth_headers):
        r = client.get("/api/search/suggestions?q=test", headers=auth_headers)
        assert r.status_code == 200


class TestAI:
    def test_thresholds(self, client, auth_headers):
        r = client.get("/api/ai/approval/thresholds", headers=auth_headers)
        assert r.status_code == 200

class TestAuditLog:
    def test_record_and_query(self, client, auth_headers):
        r = client.get("/api/audit-log", headers=auth_headers)
        assert r.status_code == 200, f"GET got {r.status_code}: {r.text[:200]}"
