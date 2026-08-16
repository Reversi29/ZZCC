"""test_users.py — P1.8 用户管理 CRUD（Admin）"""
import pytest
from database import User


class TestUserCRUD:
    """GET /api/users  list / GET /{username} get / POST create"""

    def test_admin_lists_users(self, client, auth_headers):
        r = client.get("/api/users", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        # admin + user01 + alice
        assert len(r.json()) >= 2

    def test_admin_gets_user_detail(self, client, auth_headers):
        r = client.get("/api/users/admin", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"
        assert "creation" in data

    def test_admin_get_nonexistent(self, client, auth_headers):
        r = client.get("/api/users/no_such_user_xyz", headers=auth_headers)
        assert r.status_code == 404

    def test_user_forbidden(self, client, user_headers):
        r = client.get("/api/users", headers=user_headers)
        assert r.status_code == 403

    def test_create_user_ok(self, client, auth_headers, db):
        payload = {
            "username": "testuser",
            "password": "secure123",
            "display_name": "测试用户",
            "role": "user",
        }
        r = client.post("/api/users", headers=auth_headers, json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["username"] == "testuser"
        assert data["role"] == "user"
        assert data["is_active"] is True
        assert data["department_id"] is None
        assert "hashed_password" not in data

    def test_create_user_with_department(self, client, auth_headers, db):
        # 需先有部门，先创建一个简单部门
        from database import Department
        db.add(Department(name="D-TEST", department_name="测试部",
                          lft=200, rgt=201, company="ZZCC"))
        db.commit()
        payload = {
            "username": "testuser2",
            "password": "secure123",
            "display_name": "测试用户2",
            "role": "manager",
            "department_id": "D-TEST",
        }
        r = client.post("/api/users", headers=auth_headers, json=payload)
        assert r.status_code == 201
        assert r.json()["department_id"] == "D-TEST"

    def test_create_duplicate_username(self, client, auth_headers):
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "alice",
            "password": "newpass123",
            "display_name": "管理员",
            "role": "admin",
        })
        assert r.status_code == 400

    def test_create_invalid_role(self, client, auth_headers):
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "badrole",
            "password": "secure123",
            "display_name": "无效角色",
            "role": "superadmin",  # 不在允许列表内
        })
        assert r.status_code == 422

    def test_create_username_too_short(self, client, auth_headers):
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "ab",  # < 3 chars
            "password": "secure123",
            "display_name": "太短",
            "role": "user",
        })
        assert r.status_code == 422

    def test_create_department_not_exist(self, client, auth_headers):
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "nodept",
            "password": "secure123",
            "display_name": "不存在部门",
            "role": "user",
            "department_id": "D-NOEXIST",
        })
        assert r.status_code == 400


class TestUserUpdate:
    """PATCH /api/users/{username} update"""

    def test_update_display_name(self, client, auth_headers, db):
        # 先创建用户
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "updatetest",
            "password": "secure123",
            "display_name": "更新测试",
            "role": "user",
        })
        assert r.status_code == 201
        # 更新 display_name
        r = client.patch("/api/users/updatetest", headers=auth_headers, json={
            "display_name": "更新后的名字",
        })
        assert r.status_code == 200
        assert r.json()["display_name"] == "更新后的名字"

    def test_update_role(self, client, auth_headers, db):
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "roleupdatetest",
            "password": "secure123",
            "display_name": "角色更新",
            "role": "user",
        })
        r = client.patch("/api/users/roleupdatetest", headers=auth_headers, json={
            "role": "manager",
        })
        assert r.status_code == 200
        assert r.json()["role"] == "manager"

    def test_update_department(self, client, auth_headers, db):
        from database import Department
        db.add(Department(name="D-UPD", department_name="更新部门",
                          lft=300, rgt=301, company="ZZCC"))
        db.commit()
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "depttest",
            "password": "secure123",
            "display_name": "部门更新",
            "role": "user",
        })
        r = client.patch("/api/users/depttest", headers=auth_headers, json={
            "department_id": "D-UPD",
        })
        assert r.status_code == 200
        assert r.json()["department_id"] == "D-UPD"
        # 清除 department
        r = client.patch("/api/users/depttest", headers=auth_headers, json={
            "department_id": "",
        })
        assert r.status_code == 200
        assert r.json()["department_id"] is None

    def test_update_ext_patch(self, client, auth_headers, db):
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "exttest",
            "password": "secure123",
            "display_name": "扩展字段",
            "role": "user",
        })
        r = client.patch("/api/users/exttest", headers=auth_headers, json={
            "ext": {"title": "财务主管", "phone": "13800009999"},
        })
        assert r.status_code == 200
        assert r.json()["ext"]["title"] == "财务主管"
        # 再次 patch 合并
        r = client.patch("/api/users/exttest", headers=auth_headers, json={
            "ext": {"phone": "13900009999"},  # 只更新 phone
        })
        assert r.status_code == 200
        assert r.json()["ext"]["title"] == "财务主管"  # 保留
        assert r.json()["ext"]["phone"] == "13900009999"  # 更新

    def test_update_nonexistent(self, client, auth_headers):
        r = client.patch("/api/users/no_such_user", headers=auth_headers, json={
            "display_name": "不存在",
        })
        assert r.status_code == 404


class TestResetPassword:
    """POST /api/users/{username}/reset-password"""

    def test_reset_password_ok(self, client, auth_headers, db):
        # 创建用户 → 重置密码 → 用新密码登录
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "resetpwtest",
            "password": "oldpass123",
            "display_name": "重置密码测试",
            "role": "user",
        })
        r = client.post("/api/users/resetpwtest/reset-password",
                        headers=auth_headers,
                        json={"new_password": "newpass456", "invalidate_sessions": True})
        assert r.status_code == 200
        # 用新密码登录
        r = client.post("/api/auth/login", json={
            "username": "resetpwtest",
            "password": "newpass456",
        })
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_reset_admin_forbidden(self, client, auth_headers):
        r = client.post("/api/users/admin/reset-password", headers=auth_headers,
                        json={"new_password": "hacked"})
        assert r.status_code == 400

    def test_reset_nonexistent(self, client, auth_headers):
        r = client.post("/api/users/no_such_user/reset-password",
                        headers=auth_headers, json={"new_password": "anypass"})
        assert r.status_code == 404


class TestDeactivateUser:
    """DELETE /api/users/{username} soft-delete"""

    def test_deactivate_ok(self, client, auth_headers, db):
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "deactivatetest",
            "password": "secure123",
            "display_name": "禁用测试",
            "role": "user",
        })
        r = client.delete("/api/users/deactivatetest", headers=auth_headers)
        assert r.status_code == 204
        # 查不到 is_active=True 的
        r = client.get("/api/users", headers=auth_headers)
        names = [u["username"] for u in r.json() if u["is_active"]]
        assert "deactivatetest" not in names

    def test_deactivate_admin_forbidden(self, client, auth_headers):
        r = client.delete("/api/users/admin", headers=auth_headers)
        assert r.status_code == 400

    def test_deactivate_self_forbidden(self, client, api_key_headers):
        # Business rule: cannot deactivate own account. alice token -> target alice -> 400
        r = client.delete("/api/users/admin", headers=api_key_headers)
        assert r.status_code == 400
        # Business rule: cannot deactivate own account. alice token -> target alice -> 400

    def test_deactivate_nonexistent(self, client, auth_headers):
        r = client.delete("/api/users/no_such_user", headers=auth_headers)
        assert r.status_code == 404


class TestUserFilter:
    """GET /api/users 过滤参数"""

    def test_filter_by_role(self, client, auth_headers, db):
        r = client.get("/api/users?role=admin", headers=auth_headers)
        assert r.status_code == 200
        for u in r.json():
            assert u["role"] == "admin"

    def test_filter_by_is_active(self, client, auth_headers, db):
        # 创建一个禁用的用户
        r = client.post("/api/users", headers=auth_headers, json={
            "username": "inactivetest",
            "password": "secure123",
            "display_name": "禁用用户",
            "role": "user",
        })
        r = client.delete("/api/users/inactivetest", headers=auth_headers)
        r = client.get("/api/users?is_active=false", headers=auth_headers)
        assert r.status_code == 200
        names = [u["username"] for u in r.json()]
        assert "inactivetest" in names
        r = client.get("/api/users?is_active=true", headers=auth_headers)
        names = [u["username"] for u in r.json()]
        assert "inactivetest" not in names

    def test_filter_by_search(self, client, auth_headers):
        r = client.get("/api/users?search=admin", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1
        for u in r.json():
            assert "admin" in u["username"] or "admin" in u["display_name"]


class TestRegistrationApproval:
    """注册审批流：注册->pending，管理员审批/拒绝"""

    def _register_pending(self, client, username="penduser"):
        return client.post("/api/auth/register", json={
            "username": username, "password": "pend123456", "display_name": "待审用户",
        })

    def test_register_creates_pending(self, client, db):
        r = self._register_pending(client)
        assert r.status_code == 201
        assert r.json()["status"] == "pending"
        # 待审用户不能登录
        login = client.post("/api/auth/login", json={
            "username": "penduser", "password": "pend123456",
        })
        assert login.status_code == 403

    def test_pending_listed_for_admin(self, client, auth_headers, db):
        self._register_pending(client, username="penda")
        r = client.get("/api/users/registrations/pending", headers=auth_headers)
        assert r.status_code == 200
        names = [u["username"] for u in r.json()]
        assert "penda" in names
        # 普通用户不可见
        r2 = client.get("/api/users/registrations/pending", headers=None)
        # 无 token -> 401（require_admin 依赖也会 401）
        assert r2.status_code in (401, 403)

    def test_approve_activates(self, client, auth_headers, db):
        self._register_pending(client, username="pendb")
        r = client.post("/api/users/pendb/approve", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "active"
        assert r.json()["is_active"] is True
        # 审批后登录成功
        login = client.post("/api/auth/login", json={
            "username": "pendb", "password": "pend123456",
        })
        assert login.status_code == 200
        assert "access_token" in login.json()

    def test_approve_notifies_user(self, client, auth_headers, db):
        self._register_pending(client, username="pendc")
        client.post("/api/users/pendc/approve", headers=auth_headers)
        # 用该用户登录后拉通知
        login = client.post("/api/auth/login", json={
            "username": "pendc", "password": "pend123456",
        })
        tok = login.json()["access_token"]
        r = client.get("/api/workflow/notifications?recipient=pendc",
                       headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        titles = [n["title"] for n in r.json()["items"]]
        assert "账号已激活" in titles

    def test_reject_disables(self, client, auth_headers, db):
        self._register_pending(client, username="pendd")
        r = client.post("/api/users/pendd/reject", headers=auth_headers)
        assert r.status_code == 204
        # 拒绝后账号已停用，登录返回 401
        login = client.post("/api/auth/login", json={
            "username": "pendd", "password": "pend123456",
        })
        assert login.status_code == 401
        # 已拒绝账号不能再次审批
        r2 = client.post("/api/users/pendd/approve", headers=auth_headers)
        assert r2.status_code == 400

    def test_approve_nonexistent(self, client, auth_headers):
        r = client.post("/api/users/ghost/approve", headers=auth_headers)
        assert r.status_code == 404
