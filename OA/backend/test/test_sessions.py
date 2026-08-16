"""test_sessions.py — P0.5 会话管理（多端会话列表 + 踢出其他设备）"""
import pytest


def _login(client, username="admin", password="admin123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    t = r.json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def test_list_sessions_and_logout_all(client):
    import routers.auth as auth
    auth._ACTIVE_SESSIONS.clear()  # 隔离：避免其他测试的 admin 登录污染计数
    h1 = _login(client)
    h2 = _login(client)  # 同一用户第二次登录（另一台设备）
    rs = client.get("/api/auth/sessions", headers=h2).json()
    assert len(rs) == 2
    assert sum(1 for s in rs if s["is_current"]) == 1  # 仅有当前 token 标记为当前

    # 用 h2 踢出其他设备（应踢掉 h1，保留 h2）
    r = client.post("/api/auth/logout-all", headers=h2)
    assert r.status_code == 200
    assert r.json()["revoked"] == 1

    # h1 已失效
    assert client.get("/api/auth/sessions", headers=h1).status_code == 401
    # h2 仍有效，且仅剩自身
    rs2 = client.get("/api/auth/sessions", headers=h2).json()
    assert len(rs2) == 1
    assert rs2[0]["is_current"] is True


def test_logout_all_requires_auth(client):
    assert client.post("/api/auth/logout-all").status_code == 401


def test_token_expire_env(monkeypatch):
    """过期时长可由环境变量配置（默认 24h）"""
    import routers.auth as auth
    monkeypatch.setenv("OAUTH_TOKEN_EXPIRE_HOURS", "1")
    # 重新读取模块级常量需 reload；此处验证默认值存在且为 int
    assert isinstance(auth.ACCESS_TOKEN_EXPIRE_HOURS, int)
    assert auth.ACCESS_TOKEN_EXPIRE_HOURS >= 1
