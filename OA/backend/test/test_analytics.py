"""
测试 P3.14 统计概览接口
"""
import pytest
from fastapi.testclient import TestClient


def test_overview_returns_all_sections(client: TestClient, auth_headers: dict):
    """概览接口返回全部 4 个模块字段"""
    r = client.get("/api/analytics/overview", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "generated_at" in data
    assert set(data.keys()) == {"generated_at", "workflow", "hr", "crm", "stock"}


def test_overview_workflow_has_pending_and_monthly(client: TestClient, auth_headers: dict):
    """workflow 节点含 pending_by_type / approved_this_month / rejected_this_month"""
    r = client.get("/api/analytics/overview", headers=auth_headers)
    assert r.status_code == 200
    wf = r.json()["workflow"]
    assert "pending_by_type" in wf
    assert "approved_this_month" in wf
    assert "rejected_this_month" in wf
    assert isinstance(wf["pending_by_type"], dict)


def test_overview_hr_has_employee_counts(client: TestClient, auth_headers: dict):
    """hr 节点含员工统计"""
    r = client.get("/api/analytics/overview", headers=auth_headers)
    assert r.status_code == 200
    hr = r.json()["hr"]
    assert set(hr.keys()) == {"total_employees", "on_leave_today", "pending_leave_requests"}


def test_overview_requires_auth(client: TestClient):
    """未登录 401"""
    r = client.get("/api/analytics/overview")
    assert r.status_code == 401
