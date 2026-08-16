"""test_security.py — P0.2 账号安全（改密 / 登出失效 / 登录锁定）"""
import pytest


def _login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_change_password_ok(client, auth_headers):
    """改密成功 + 旧密码失效 + 新密码可登录"""
    r = client.post("/api/auth/change-password", headers=auth_headers,
                    json={"old_password": "admin123", "new_password": "newpass789"})
    assert r.status_code == 200, r.text
    # 旧密码登录失败
    assert _login(client, "admin", "admin123").status_code == 401
    # 新密码登录成功
    assert _login(client, "admin", "newpass789").status_code == 200


def test_change_password_invalidates_token(client, auth_headers):
    """改密后旧 token 立即失效（jti 黑名单）"""
    r = client.post("/api/auth/change-password", headers=auth_headers,
                    json={"old_password": "admin123", "new_password": "newpass789"})
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers=auth_headers)
    assert me.status_code == 401, me.text


def test_change_password_wrong_old(client, auth_headers):
    r = client.post("/api/auth/change-password", headers=auth_headers,
                    json={"old_password": "wrong", "new_password": "newpass789"})
    assert r.status_code == 400


def test_change_password_same(client, auth_headers):
    r = client.post("/api/auth/change-password", headers=auth_headers,
                    json={"old_password": "admin123", "new_password": "admin123"})
    assert r.status_code == 400


def test_change_password_weak(client, auth_headers):
    r = client.post("/api/auth/change-password", headers=auth_headers,
                    json={"old_password": "admin123", "new_password": "123"})
    assert r.status_code == 422


def test_logout_invalidates_token(client):
    """登录 → 登出 → 旧 token 失效"""
    tok = _login(client, "admin", "admin123").json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200
    out = client.post("/api/auth/logout", headers=h)
    assert out.status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_login_lock_after_5_fails(client):
    """连续 5 次错误 → 423 锁定"""
    for i in range(5):
        r = _login(client, "lockuser", "badpass")
        if i < 4:
            assert r.status_code == 401, f"第{i+1}次应 401，实际 {r.status_code}"
        else:
            assert r.status_code == 423, f"第5次应 423，实际 {r.status_code}: {r.text}"
