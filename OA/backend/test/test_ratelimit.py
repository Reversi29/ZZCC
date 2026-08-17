"""
测试 P3.16 API 限流中间件
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_buckets(monkeypatch):
    from middleware.ratelimit import RateLimitMiddleware

    # conftest 默认关闭限流，本测试文件需开启以验证行为
    monkeypatch.setenv("RATELIMIT_ENABLED", "true")
    RateLimitMiddleware._buckets.clear()
    yield
    RateLimitMiddleware._buckets.clear()


def test_default_limit_triggers_429(client: TestClient, monkeypatch):
    """超过全局限流阈值返回 429 且带 Retry-After 头"""
    monkeypatch.setenv("RATELIMIT_DEFAULT", "3")
    headers = {"X-Forwarded-For": "198.51.100.7"}
    statuses = [
        client.get("/api/status", headers=headers).status_code for _ in range(5)
    ]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429
    assert statuses[4] == 429
    assert client.get("/api/status", headers=headers).headers.get("Retry-After")


def test_per_ip_isolation(client: TestClient, monkeypatch):
    """不同 IP 的限流桶互相独立"""
    monkeypatch.setenv("RATELIMIT_DEFAULT", "2")
    for ip in ("203.0.113.1", "203.0.113.2"):
        h = {"X-Forwarded-For": ip}
        assert client.get("/api/status", headers=h).status_code == 200
        assert client.get("/api/status", headers=h).status_code == 200
        assert client.get("/api/status", headers=h).status_code == 429


def test_login_has_separate_limit(client: TestClient, monkeypatch):
    """登录接口走独立限流桶，超限返回 429"""
    monkeypatch.setenv("RATELIMIT_LOGIN", "2")
    headers = {"X-Forwarded-For": "198.51.100.23"}
    body = {"username": "admin", "password": "wrong"}
    s1 = client.post("/api/auth/login", json=body, headers=headers).status_code
    s2 = client.post("/api/auth/login", json=body, headers=headers).status_code
    s3 = client.post("/api/auth/login", json=body, headers=headers).status_code
    assert s1 in (401, 422, 423)
    assert s2 in (401, 422, 423)
    assert s3 == 429


def test_x_forwarded_for_respected(client: TestClient, monkeypatch):
    """反向代理后取 X-Forwarded-For 第一个 IP 作为限流依据"""
    monkeypatch.setenv("RATELIMIT_DEFAULT", "1")
    h1 = {"X-Forwarded-For": "10.0.0.1, 10.0.0.2"}
    h2 = {"X-Forwarded-For": "10.0.0.9"}
    assert client.get("/api/status", headers=h1).status_code == 200
    # 同一 X-Forwarded-For 首 IP 再次请求应被限流
    assert client.get("/api/status", headers=h1).status_code == 429
    # 不同 IP 不受影响
    assert client.get("/api/status", headers=h2).status_code == 200
