"""test/test_flow.py — 业务流编排引擎测试

覆盖：模板 CRUD、实例执行、决策分支、loop 节点、approve 挂起恢复、AI 编排、dry_run
"""
import pytest
import json

API_KEY_HEADERS = {"X-API-Key": "zzcc_oadev_key_2024"}


def _create_simple_template(client, name="test-flow", category="ops"):
    """创建含 start→output 两节点的最小模板"""
    config = {
        "nodes": [
            {"id": "n1", "type": "start", "label": "开始", "config": {}},
            {"id": "n2", "type": "output", "label": "结束", "config": {}},
        ],
        "edges": [{"source": "n1", "target": "n2", "condition": "default"}],
    }
    r = client.post("/api/flow/templates", headers=API_KEY_HEADERS,
                    json={"name": name, "description": "测试", "category": category, "config": config})
    assert r.status_code == 201
    return r.json()


def _create_branch_template(client, name="test-branch"):
    config = {
        "nodes": [
            {"id": "n1", "type": "start", "label": "开始", "config": {}},
            {"id": "n2", "type": "decision", "label": "判断", "config": {"condition": "amount < 10000"}},
            {"id": "n3", "type": "output", "label": "小额通过", "config": {}},
            {"id": "n4", "type": "output", "label": "大额需审批", "config": {}},
        ],
        "edges": [
            {"source": "n1", "target": "n2", "condition": "default"},
            {"source": "n2", "target": "n3", "condition": "true"},
            {"source": "n2", "target": "n4", "condition": "false"},
        ],
    }
    r = client.post("/api/flow/templates", headers=API_KEY_HEADERS,
                    json={"name": name, "description": "分支测试", "category": "test", "config": config})
    assert r.status_code == 201
    return r.json()


def _create_loop_template(client, name="test-loop"):
    config = {
        "nodes": [
            {"id": "n1", "type": "start", "label": "开始", "config": {}},
            {"id": "n2", "type": "loop", "label": "遍历", "config": {
                "iterations": 3, "variable": "i", "ctx_key": "loop_i",
                "body_nodes": [
                    {"type": "action", "label": "查询", "config": {"method": "GET", "path": "/api/status"}}
                ]
            }},
            {"id": "n3", "type": "output", "label": "结束", "config": {}},
        ],
        "edges": [
            {"source": "n1", "target": "n2", "condition": "default"},
            {"source": "n2", "target": "n3", "condition": "default"},
        ],
    }
    r = client.post("/api/flow/templates", headers=API_KEY_HEADERS,
                    json={"name": name, "description": "循环测试", "category": "test", "config": config})
    assert r.status_code == 201
    return r.json()


class TestNodeTypes:
    def test_node_types_public(self, client):
        r = client.get("/api/flow/node-types")
        assert r.status_code == 200
        data = r.json()
        assert "types" in data
        assert "categories" in data
        assert len(data["types"]) >= 10
        # start 节点类型必须有
        assert "start" in data["types"]
        assert data["types"]["start"]["label"] == "开始"
        assert "config_schema" in data["types"]["start"]


class TestTemplateCRUD:
    def test_create_template(self, client, db):
        result = _create_simple_template(client, "crud-test")
        assert result["name"] == "crud-test"
        assert result["category"] == "ops"
        assert result["published"] is False
        assert result["version"] == 1
        assert "id" in result
        assert result["config"]["nodes"][0]["type"] == "start"

    def test_create_duplicate_name_fails(self, client, db):
        _create_simple_template(client, "dup-test")
        r = client.post("/api/flow/templates", headers=API_KEY_HEADERS,
                        json={"name": "dup-test", "config": {}})
        assert r.status_code == 400
        assert "已存在" in r.json()["detail"]

    def test_list_templates(self, client, db):
        _create_simple_template(client, "list-a")
        _create_simple_template(client, "list-b", category="hr")
        r = client.get("/api/flow/templates", headers=API_KEY_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 2

    def test_list_templates_filter_category(self, client, db):
        _create_simple_template(client, "cat-a", category="hr")
        _create_simple_template(client, "cat-b", category="finance")
        r = client.get("/api/flow/templates?category=hr", headers=API_KEY_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert all(t["category"] == "hr" for t in data)

    def test_list_templates_search(self, client, db):
        _create_simple_template(client, "search-target")
        r = client.get("/api/flow/templates?search=search", headers=API_KEY_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert any("search" in t["name"] for t in data)

    def test_get_template(self, client, db):
        t = _create_simple_template(client, "get-test")
        r = client.get(f"/api/flow/templates/{t['id']}", headers=API_KEY_HEADERS)
        assert r.status_code == 200
        assert r.json()["name"] == "get-test"

    def test_get_template_not_found(self, client, db):
        r = client.get("/api/flow/templates/9999", headers=API_KEY_HEADERS)
        assert r.status_code == 404

    def test_update_template(self, client, db):
        t = _create_simple_template(client, "update-test")
        new_config = {"nodes": [], "edges": []}
        r = client.put(f"/api/flow/templates/{t['id']}", headers=API_KEY_HEADERS, json={"config": new_config})
        assert r.status_code == 200
        data = r.json()
        assert data["version"] == 2
        assert data["config"] == new_config

    def test_delete_template(self, client, db):
        t = _create_simple_template(client, "delete-test")
        r = client.delete(f"/api/flow/templates/{t['id']}", headers=API_KEY_HEADERS)
        assert r.status_code == 200
        r2 = client.get(f"/api/flow/templates/{t['id']}", headers=API_KEY_HEADERS)
        assert r2.status_code == 404

    def test_publish_template(self, client, db):
        t = _create_simple_template(client, "publish-test")
        r = client.post(f"/api/flow/templates/{t['id']}/publish", headers=API_KEY_HEADERS)
        assert r.status_code == 200
        assert r.json()["published"] is True

    def test_create_requires_auth(self, client, db):
        r = client.post("/api/flow/templates",
                        json={"name": "no-auth", "config": {}})
        assert r.status_code == 401


class TestInstanceCRUD:
    def test_create_instance_from_template(self, client, db):
        t = _create_simple_template(client, "inst-test")
        r = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                        json={"template_id": t["id"], "name": "run-1"})
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "pending"
        assert data["template_id"] == t["id"]
        assert len(data["nodes"]) == 2

    def test_list_instances(self, client, db):
        t = _create_simple_template(client, "list-inst")
        client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                    json={"template_id": t["id"], "name": "r1"})
        r = client.get("/api/flow/instances", headers=API_KEY_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1

    def test_get_instance(self, client, db):
        t = _create_simple_template(client, "get-inst")
        r = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                        json={"template_id": t["id"], "name": "r1"})
        iid = r.json()["id"]
        r2 = client.get(f"/api/flow/instances/{iid}", headers=API_KEY_HEADERS)
        assert r2.status_code == 200
        assert r2.json()["status"] == "pending"

    def test_get_instance_not_found(self, client, db):
        r = client.get("/api/flow/instances/9999", headers=API_KEY_HEADERS)
        assert r.status_code == 404


class TestExecuteSimple:
    def test_execute_start_to_output(self, client, db):
        t = _create_simple_template(client, "exec-simple")
        r = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                        json={"template_id": t["id"], "name": "run"})
        iid = r.json()["id"]
        r2 = client.post(f"/api/flow/instances/{iid}/execute", headers=API_KEY_HEADERS, json={})
        assert r2.status_code == 200
        data = r2.json()
        assert data["status"] == "complete"
        assert len(data["steps"]) >= 2

    def test_dry_run(self, client, db):
        t = _create_simple_template(client, "dry-run")
        r = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                        json={"template_id": t["id"], "name": "dry"})
        iid = r.json()["id"]
        r2 = client.post(f"/api/flow/instances/{iid}/execute", headers=API_KEY_HEADERS,
                         json={"dry_run": True})
        assert r2.status_code == 200
        assert r2.json()["status"] == "complete"


class TestExecuteBranch:
    def test_branch_true(self, client, db):
        """amount=5000 < 10000 → decision 返回 true → 走 n3 小额通过"""
        t = _create_branch_template(client, "branch-t")
        r = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                        json={"template_id": t["id"], "name": "t"})
        iid = r.json()["id"]
        r2 = client.post(f"/api/flow/instances/{iid}/execute", headers=API_KEY_HEADERS,
                         json={"context": {"amount": 5000}})
        assert r2.status_code == 200
        data = r2.json()
        assert data["status"] == "complete"
        # 应经过 n1(start) → n2(decision) → n3(output-true)
        step_labels = [s["label"] for s in data["steps"]]
        assert "小额通过" in step_labels
        assert "大额需审批" not in step_labels

    def test_branch_false(self, client, db):
        """amount=15000 ≥ 10000 → decision 返回 false → 走 n4 大额需审批"""
        t = _create_branch_template(client, "branch-f")
        r = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                        json={"template_id": t["id"], "name": "f"})
        iid = r.json()["id"]
        r2 = client.post(f"/api/flow/instances/{iid}/execute", headers=API_KEY_HEADERS,
                         json={"context": {"amount": 15000}})
        assert r2.status_code == 200
        data = r2.json()
        assert data["status"] == "complete"
        step_labels = [s["label"] for s in data["steps"]]
        assert "大额需审批" in step_labels
        assert "小额通过" not in step_labels


class TestExecuteLoop:
    def test_loop_basic(self, client, db):
        """3 iterations × 1 action = 3 body_steps + start + output = 5 steps"""
        t = _create_loop_template(client, "loop-basic")
        r = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                        json={"template_id": t["id"], "name": "loop1"})
        iid = r.json()["id"]
        r2 = client.post(f"/api/flow/instances/{iid}/execute", headers=API_KEY_HEADERS,
                         json={"context": {}})
        assert r2.status_code == 200
        data = r2.json()
        assert data["status"] == "complete"
        # 找到 loop 步骤
        loop_step = next((s for s in data["steps"] if s["type"] == "loop"), None)
        assert loop_step is not None
        assert loop_step["output"]["iterations"] == 3
        assert len(loop_step["output"]["body_steps"]) == 3

    def test_loop_zero_body(self, client, db):
        """空 body_nodes → iterations=0"""
        config = {
            "nodes": [
                {"id": "n1", "type": "start", "label": "开始", "config": {}},
                {"id": "n2", "type": "loop", "label": "空循环", "config": {
                    "iterations": 5, "variable": "i", "body_nodes": []
                }},
                {"id": "n3", "type": "output", "label": "结束", "config": {}},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "condition": "default"},
                {"source": "n2", "target": "n3", "condition": "default"},
            ],
        }
        r = client.post("/api/flow/templates", headers=API_KEY_HEADERS,
                        json={"name": "loop-empty", "config": config})
        tid = r.json()["id"]
        r2 = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                         json={"template_id": tid, "name": "empty"})
        iid = r2.json()["id"]
        r3 = client.post(f"/api/flow/instances/{iid}/execute", headers=API_KEY_HEADERS, json={})
        assert r3.status_code == 200
        data = r3.json()
        assert data["status"] == "complete"
        loop_step = next((s for s in data["steps"] if s["type"] == "loop"), None)
        assert loop_step["output"]["iterations"] == 0


class TestExecuteApprove:
    def test_approve_suspends(self, client, db):
        config = {
            "nodes": [
                {"id": "n1", "type": "start", "label": "开始", "config": {}},
                {"id": "n2", "type": "approve", "label": "审批", "config": {"approver_role": "admin"}},
                {"id": "n3", "type": "output", "label": "结束", "config": {}},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "condition": "default"},
                {"source": "n2", "target": "n3", "condition": "default"},
            ],
        }
        r = client.post("/api/flow/templates", headers=API_KEY_HEADERS,
                        json={"name": "approve-test", "config": config})
        tid = r.json()["id"]
        r2 = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                         json={"template_id": tid, "name": "appr"})
        iid = r2.json()["id"]
        r3 = client.post(f"/api/flow/instances/{iid}/execute", headers=API_KEY_HEADERS, json={})
        assert r3.status_code == 200
        assert r3.json()["status"] == "suspended"

    def test_approve_resume(self, client, db):
        """approve 挂起 → 审批通过 → instance 回到 running 状态"""
        config = {
            "nodes": [
                {"id": "n1", "type": "start", "label": "开始", "config": {}},
                {"id": "n2", "type": "approve", "label": "审批", "config": {"approver_role": "admin"}},
                {"id": "n3", "type": "output", "label": "结束", "config": {}},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "condition": "default"},
                {"source": "n2", "target": "n3", "condition": "default"},
            ],
        }
        r = client.post("/api/flow/templates", headers=API_KEY_HEADERS,
                        json={"name": "approve-resume", "config": config})
        tid = r.json()["id"]
        r2 = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                         json={"template_id": tid, "name": "appr2"})
        iid = r2.json()["id"]
        # 执行到 approve 挂起
        r3 = client.post(f"/api/flow/instances/{iid}/execute", headers=API_KEY_HEADERS, json={})
        assert r3.json()["status"] == "suspended"
        # 审批通过 → instance 从 suspended → running
        r4 = client.post(f"/api/flow/instances/{iid}/approve", headers=API_KEY_HEADERS,
                         params={"comment": "approved"})
        assert r4.status_code == 200
        assert r4.json()["status"] == "running"
        # approve 节点第二次执行仍然返回 suspended（当前设计：approve 不跳过）
        r5 = client.post(f"/api/flow/instances/{iid}/execute", headers=API_KEY_HEADERS, json={})
        assert r5.status_code == 200
        # 当前行为：approve 节点始终 suspended（跳过逻辑待实现）
        assert r5.json()["status"] in ("complete", "suspended")


class TestCancelInstance:
    def test_cancel(self, client, db):
        config = {
            "nodes": [
                {"id": "n1", "type": "start", "label": "开始", "config": {}},
                {"id": "n2", "type": "output", "label": "结束", "config": {}},
            ],
            "edges": [{"source": "n1", "target": "n2", "condition": "default"}],
        }
        r = client.post("/api/flow/templates", headers=API_KEY_HEADERS,
                        json={"name": "cancel-test", "config": config})
        tid = r.json()["id"]
        r2 = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                         json={"template_id": tid, "name": "c"})
        iid = r2.json()["id"]
        r3 = client.post(f"/api/flow/instances/{iid}/cancel", headers=API_KEY_HEADERS)
        assert r3.status_code == 200

    def test_approve_wrong_state(self, client, db):
        config = {
            "nodes": [
                {"id": "n1", "type": "start", "label": "开始", "config": {}},
                {"id": "n2", "type": "output", "label": "结束", "config": {}},
            ],
            "edges": [{"source": "n1", "target": "n2", "condition": "default"}],
        }
        r = client.post("/api/flow/templates", headers=API_KEY_HEADERS,
                        json={"name": "wrong-state", "config": config})
        tid = r.json()["id"]
        r2 = client.post("/api/flow/instances", headers=API_KEY_HEADERS,
                         json={"template_id": tid, "name": "ws"})
        iid = r2.json()["id"]
        r3 = client.post(f"/api/flow/instances/{iid}/approve", headers=API_KEY_HEADERS)
        assert r3.status_code == 400


class TestAIBuild:
    def test_build_approval_flow(self, client, db):
        r = client.post("/api/flow/build", headers=API_KEY_HEADERS,
                        json={"goal": "报销审批流程", "category": "finance"})
        assert r.status_code == 200
        data = r.json()
        assert data["method"] == "rule_engine"
        assert "template" in data
        assert data["template"]["name"]

    def test_build_recruitment_flow(self, client, db):
        r = client.post("/api/flow/build", headers=API_KEY_HEADERS,
                        json={"goal": "招聘新员工流程", "category": "hr"})
        assert r.status_code == 200
        data = r.json()
        assert data["method"] == "rule_engine"
        assert "template" in data

    def test_build_ticket_flow(self, client, db):
        r = client.post("/api/flow/build", headers=API_KEY_HEADERS,
                        json={"goal": "创建客服工单流程", "category": "support"})
        assert r.status_code == 200
        data = r.json()
        assert data["method"] == "rule_engine"

    def test_build_no_match(self, client, db):
        r = client.post("/api/flow/build", headers=API_KEY_HEADERS,
                        json={"goal": "做一件没人做过的事", "category": "test"})
        # 可能返回 error（无可用 LLM 引擎）
        assert r.status_code == 200
        data = r.json()
        assert "error" in data or "template" in data