"""test_org.py — Department CRUD 测试（NSM Nested Set Model）"""
import pytest


@pytest.fixture(autouse=True)
def seed_depts(client, admin_headers):
    """每个测试前重建 D-ROOT"""
    client.delete("/api/resource/Department/D-ROOT", headers=admin_headers)
    client.post("/api/resource/Department",
                json={"name": "D-ROOT", "department_name": "ZZCC", "is_group": True},
                headers=admin_headers)
    yield


class TestListDepartments:
    def test_list_returns_depts(self, client, auth_headers):
        r = client.get("/api/resource/Department", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "D-ROOT"
        assert data[0]["children_count"] == 0
        assert data[0]["has_children"] is False


class TestCreateDepartment:
    def test_create_child_dept(self, client, admin_headers):
        r = client.post("/api/resource/Department",
                        json={"name": "D-DEV", "department_name": "研发部",
                              "parent": "D-ROOT", "is_group": False},
                        headers=admin_headers)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["name"] == "D-DEV"
        assert d["parent"] == "D-ROOT"
        assert d["lft"] > 0 and d["rgt"] > d["lft"]

    def test_create_duplicate_fails(self, client, admin_headers):
        client.post("/api/resource/Department",
                    json={"name": "D-DUP", "department_name": "重复", "is_group": False},
                    headers=admin_headers)
        r = client.post("/api/resource/Department",
                        json={"name": "D-DUP", "department_name": "重复2", "is_group": False},
                        headers=admin_headers)
        assert r.status_code == 400
        assert "已存在" in r.json()["detail"]

    def test_create_as_non_admin_fails(self, client, user_headers):
        r = client.post("/api/resource/Department",
                        json={"name": "D-BAD", "department_name": "非法", "is_group": False},
                        headers=user_headers)
        assert r.status_code == 403


class TestGetDepartment:
    def test_get_one(self, client, admin_headers):
        client.post("/api/resource/Department",
                    json={"name": "D-DEV", "department_name": "研发部",
                          "parent": "D-ROOT", "is_group": False},
                    headers=admin_headers)
        r = client.get("/api/resource/Department/D-DEV", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["name"] == "D-DEV"
        assert "children" in d

    def test_get_nonexistent_404(self, client, auth_headers):
        r = client.get("/api/resource/Department/NOTEXIST", headers=auth_headers)
        assert r.status_code == 404


class TestUpdateDepartment:
    def test_rename(self, client, admin_headers):
        client.post("/api/resource/Department",
                    json={"name": "D-DEV", "department_name": "研发部", "is_group": False},
                    headers=admin_headers)
        r = client.put("/api/resource/Department/D-DEV",
                       json={"department_name": "研发一部"},
                       headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["data"]["department_name"] == "研发一部"

    def test_move_to_new_parent(self, client, admin_headers):
        client.post("/api/resource/Department",
                    json={"name": "D-A", "department_name": "A部",
                          "parent": "D-ROOT", "is_group": False},
                    headers=admin_headers)
        client.post("/api/resource/Department",
                    json={"name": "D-B", "department_name": "B部",
                          "parent": "D-ROOT", "is_group": False},
                    headers=admin_headers)
        r = client.put("/api/resource/Department/D-B",
                       json={"parent": "D-A"},
                       headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["data"]["parent"] == "D-A"

    def test_cyclic_move_fails(self, client, admin_headers):
        client.post("/api/resource/Department",
                    json={"name": "D-DEV", "department_name": "研发",
                          "parent": "D-ROOT", "is_group": False},
                    headers=admin_headers)
        r = client.put("/api/resource/Department/D-ROOT",
                       json={"parent": "D-DEV"},
                       headers=admin_headers)
        assert r.status_code == 400
        assert "自身" in r.json()["detail"]


class TestDeleteDepartment:
    def test_delete_leaf(self, client, admin_headers):
        client.post("/api/resource/Department",
                    json={"name": "D-DEL", "department_name": "待删", "is_group": False},
                    headers=admin_headers)
        r = client.delete("/api/resource/Department/D-DEL", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["deleted_count"] == 1

    def test_delete_subtree(self, client, admin_headers):
        client.post("/api/resource/Department",
                    json={"name": "D-PARENT", "department_name": "父部门",
                          "parent": "D-ROOT", "is_group": False},
                    headers=admin_headers)
        client.post("/api/resource/Department",
                    json={"name": "D-CHILD", "department_name": "子部门",
                          "parent": "D-PARENT", "is_group": False},
                    headers=admin_headers)
        r = client.delete("/api/resource/Department/D-PARENT", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["deleted_count"] == 2

    def test_delete_root_forbidden(self, client, admin_headers):
        r = client.delete("/api/resource/Department/D-ROOT", headers=admin_headers)
        assert r.status_code == 400
        assert "禁止删除" in r.json()["detail"]
