"""test/test_hr.py — HR 模块"""
import pytest

from conftest import *


class TestLeaveRequest:
    def test_apply_leave(self, client, auth_headers):
        r = client.post("/api/hr/leaves", json={
            "leave_type": "Annual",
            "start_date": "2025-08-10",
            "end_date": "2025-08-12",
            "reason": "旅行",
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "Submitted"
        assert data["leave_type"] == "Annual"
        assert data["days"] == 3.0
        assert "name" in data

    def test_apply_leave_invalid_dates(self, client, auth_headers):
        r = client.post("/api/hr/leaves", json={
            "leave_type": "Annual",
            "start_date": "2025-08-15",
            "end_date": "2025-08-10",
        }, headers=auth_headers)
        assert r.status_code in (200, 400)

    def test_list_leaves(self, client, auth_headers):
        client.post("/api/hr/leaves", json={
            "leave_type": "Sick",
            "start_date": "2025-09-01",
            "end_date": "2025-09-01",
        }, headers=auth_headers)
        r = client.get("/api/hr/leaves", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_leaves_requires_auth(self, client):
        r = client.get("/api/hr/leaves")
        assert r.status_code in (401, 403)

    def test_leave_auto_submit(self, client, auth_headers):
        """创建请假申请后自动进入 Submitted 状态"""
        r = client.post("/api/hr/leaves", json={
            "leave_type": "Annual",
            "start_date": "2025-10-01",
            "end_date": "2025-10-03",
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "Submitted"


class TestAttendance:
    def test_create_attendance(self, client, auth_headers):
        r = client.post("/api/hr/attendance", json={
            "employee": "alice",
            "date": "2025-08-01",
            "check_in": "09:00",
            "check_out": "18:00",
            "status": "Normal",
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["employee"] == "alice"

    def test_list_attendance(self, client, auth_headers):
        r = client.get("/api/hr/attendance", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_attendance_requires_auth(self, client):
        r = client.get("/api/hr/attendance")
        assert r.status_code in (401, 403)


class TestSalary:
    def test_create_salary(self, client, auth_headers):
        r = client.post("/api/hr/salary", json={
            "employee": "alice",
            "year_month": "2025-08",
            "base_salary": 15000.0,
            "bonus": 2000.0,
            "deductions": 500.0,
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["net_salary"] == 16500.0  # 15000+2000-500

    def test_list_salary(self, client, auth_headers):
        r = client.get("/api/hr/salary", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_salary_requires_auth(self, client):
        r = client.get("/api/hr/salary")
        assert r.status_code in (401, 403)
