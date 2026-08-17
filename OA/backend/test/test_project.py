"""test/test_project.py — P2.12 项目管理模块测试"""
import pytest

pytestmark = pytest.mark.asyncio


def test_project_crud(client, auth_headers):
    """Project CRUD"""
    r = client.post("/api/resource/Project", json={
        "project_name": "E2E项目",
        "priority": "High",
    }, headers=auth_headers)
    assert r.status_code == 200
    name = r.json()["data"]["name"]

    r = client.get(f"/api/resource/Project/{name}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["project_name"] == "E2E项目"

    r = client.put(f"/api/resource/Project/{name}", json={"percent_complete": 25.0}, headers=auth_headers)
    assert r.status_code == 200


def test_project_approval_flow(client, auth_headers):
    """Project 立项审批流"""
    r = client.post("/api/resource/Project", json={
        "project_name": "立项测试",
        "priority": "Urgent",
    }, headers=auth_headers)
    name = r.json()["data"]["name"]
    assert name.startswith("PRJ-")

    # Submit
    r = client.post("/api/workflow/action", json={"name": name, "action": "submit"}, headers=auth_headers)
    assert r.status_code == 200, f"submit failed: {r.text}"
    assert r.json()["to"] == "Submitted"

    # Approve
    r = client.post("/api/workflow/action", json={"name": name, "action": "approve"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["to"] == "Approved"


def test_task_crud(client, auth_headers):
    """Task CRUD"""
    r = client.post("/api/resource/Task", json={
        "subject": "E2E任务",
        "status": "Open",
        "priority": "Medium",
    }, headers=auth_headers)
    assert r.status_code == 200
    name = r.json()["data"]["name"]

    r = client.get(f"/api/resource/Task/{name}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["subject"] == "E2E任务"
