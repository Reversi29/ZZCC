"""test/test_auth.py — 认证路由测试"""
import pytest
from routers.auth import create_access_token

BASE = "/api/auth"

class TestLogin:
    def test_login_success(self, client, db):
        r = client.post(f"{BASE}/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    def test_login_wrong_password(self, client, db):
        r = client.post(f"{BASE}/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401
        assert "用户名或密码错误" in r.text

    def test_login_unknown_user(self, client, db):
        r = client.post(f"{BASE}/login", json={"username": "nobody", "password": "pass"})
        assert r.status_code == 401

    def test_login_missing_fields(self, client, db):
        r = client.post(f"{BASE}/login", json={"username": "admin"})
        assert r.status_code == 422  # FastAPI validation


class TestMe:
    def test_me_success(self, client, db, auth_headers):
        r = client.get(f"{BASE}/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"

    def test_me_no_token(self, client, db):
        r = client.get(f"{BASE}/me")
        assert r.status_code == 401

    def test_me_bad_token(self, client, db):
        r = client.get(f"{BASE}/me", headers={"Authorization": "Bearer badtoken"})
        assert r.status_code == 401


class TestRegister:
    def test_register_success(self, client, db):
        r = client.post(f"{BASE}/register", json={
            "username": "alice2", "password": "alice123", "display_name": "爱丽丝"
        })
        assert r.status_code == 201
        data = r.json()
        assert data["username"] == "alice2"
        assert data["role"] == "user"

    def test_register_then_login(self, client, db):
        client.post(f"{BASE}/register", json={
            "username": "bob", "password": "bob123456", "display_name": "Bob"
        })
        # 注册后处于待审核状态，登录应被拒（403）
        r0 = client.post(f"{BASE}/login", json={"username": "bob", "password": "bob123456"})
        assert r0.status_code == 403
        # 管理员审批后，登录成功
        admin_tok = create_access_token("admin", "管理员", "admin")
        client.post("/api/users/bob/approve", headers={"Authorization": f"Bearer {admin_tok}"})
        r = client.post(f"{BASE}/login", json={"username": "bob", "password": "bob123456"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_register_duplicate_username(self, client, db):
        client.post(f"{BASE}/register", json={
            "username": "dup", "password": "dup123456", "display_name": "Dup"
        })
        r = client.post(f"{BASE}/register", json={
            "username": "dup", "password": "dup123456", "display_name": "Dup2"
        })
        assert r.status_code == 400
        assert "已存在" in r.text

    def test_register_short_username(self, client, db):
        r = client.post(f"{BASE}/register", json={
            "username": "ab", "password": "ab123456", "display_name": "AB"
        })
        assert r.status_code == 422

    def test_register_non_alnum_username(self, client, db):
        r = client.post(f"{BASE}/register", json={
            "username": "ab@cd", "password": "abcd1234", "display_name": "AB"
        })
        assert r.status_code == 422

    def test_register_short_password(self, client, db):
        r = client.post(f"{BASE}/register", json={
            "username": "shortpw", "password": "12345", "display_name": "SP"
        })
        assert r.status_code == 422


class TestRefresh:
    def test_refresh_success(self, client, db, auth_headers):
        r = client.post(f"{BASE}/refresh", headers=auth_headers)
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_refresh_no_token(self, client, db):
        r = client.post(f"{BASE}/refresh")
        assert r.status_code == 401
