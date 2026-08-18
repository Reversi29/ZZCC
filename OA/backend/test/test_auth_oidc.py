"""P3.15 SSO — Casdoor OIDC 集成测试（mock IdP，验证 OA 侧逻辑）

验证点：
1. /api/auth/oidc/login → 302 到 IdP authorize（带 client_id/redirect_uri/state）
2. callback JIT 建号：首次 SSO 登录自动创建 OA 账号（role=user, status=active）
3. callback 绑定已有账号：Casdoor email == OA username → 不重复建号
4. state 防 CSRF：无效/过期 state → 400
5. 已存在但停用的账号 → 403
6. id_token 验签失败 → 401
"""
import base64
import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import routers.auth_oidc as oidc
from database import User

# ── 测试密钥与 id_token 工具 ─────────────────────────────────
TEST_KID = "test-kid"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PEM = _PRIVATE_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)


def _b64u(n: int) -> str:
    length = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()


def _test_jwk() -> dict:
    pub = _PRIVATE_KEY.public_key()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": TEST_KID,
        "n": _b64u(pub.public_numbers().n),
        "e": _b64u(pub.public_numbers().e),
    }


def _make_id_token(sub: str = "alice.sso", email: str = "alice.sso@zzcc.local",
                   name: str = "Alice SSO", aud: str | None = None,
                   iss: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    return pyjwt.encode(
        {
            "sub": sub,
            "email": email,
            "name": name,
            "preferred_username": sub,
            "iss": iss or oidc.get_settings().OAUTH_CASDOOR_URL,
            "aud": aud or oidc.get_settings().OAUTH_CLIENT_ID,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        _PEM,
        algorithm="RS256",
        headers={"kid": TEST_KID},
    )


@pytest.fixture(autouse=True)
def _mock_idp(monkeypatch):
    """mock IdP：token 端点 + JWKS，避免真实网络请求"""
    monkeypatch.setattr(oidc, "_get_jwks_keys", lambda: [_test_jwk()])
    monkeypatch.setattr(oidc, "_exchange_code", lambda code: {"id_token": _make_id_token()})
    yield


# ── 用例 ─────────────────────────────────────────────────────
def test_oidc_login_redirects_to_idp(client):
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 307
    loc = r.headers["location"]
    assert loc.startswith(f"{oidc.get_settings().OAUTH_CASDOOR_URL}/login/oauth/authorize")
    assert f"client_id={oidc.get_settings().OAUTH_CLIENT_ID}" in loc
    assert "response_type=code" in loc
    assert "state=" in loc
    from urllib.parse import quote
    assert quote(oidc.get_settings().OAUTH_REDIRECT_URI, safe="") in loc


def test_oidc_callback_jit_creates_user(client, db):
    """首次 SSO 登录 → 自动创建 OA 账号（JIT，用户决策 B）"""
    # 先拿合法 state
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    state = r.headers["location"].split("state=")[1]

    r = client.get(f"/api/auth/oidc/callback?code=test-code&state={state}")
    assert r.status_code == 200
    assert "oa_token" in r.text
    assert "alice.sso@zzcc.local" in r.text

    u = db.query(User).filter(User.username == "alice.sso@zzcc.local").first()
    assert u is not None
    assert u.role == "user"
    assert u.status == "active"
    assert u.is_active is True
    assert u.display_name == "Alice SSO"
    # JIT 用户密码为随机串：本地密码登录不可用（无法与任何已知密码匹配）
    assert u.hashed_password != oidc._hash_pw("Passw0rd!")


def test_oidc_callback_binds_existing_user(client, db):
    """Casdoor email 与 OA 已有用户名相同 → 直接绑定，不重复建号"""
    db.add(User(username="alice.sso@zzcc.local", hashed_password=oidc._hash_pw("x"),
                display_name="Old Name", role="user", status="active", is_active=True))
    db.commit()

    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    state = r.headers["location"].split("state=")[1]
    r = client.get(f"/api/auth/oidc/callback?code=c&state={state}")

    assert r.status_code == 200
    users = db.query(User).filter(User.username == "alice.sso@zzcc.local").all()
    assert len(users) == 1  # 未重复创建
    assert users[0].display_name == "Old Name"  # 不改写已有信息


def test_oidc_callback_rejects_bad_state(client):
    r = client.get("/api/auth/oidc/callback?code=c&state=forged")
    assert r.status_code == 400
    assert "state" in r.json()["detail"]


def test_oidc_callback_rejects_stale_state(client):
    """已消费过的 state 不能重用"""
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    state = r.headers["location"].split("state=")[1]
    assert client.get(f"/api/auth/oidc/callback?code=c&state={state}").status_code == 200
    r2 = client.get(f"/api/auth/oidc/callback?code=c&state={state}")
    assert r2.status_code == 400


def test_oidc_callback_rejects_inactive_user(client, db):
    """已存在但停用/未激活账号 → 403"""
    db.add(User(username="alice.sso@zzcc.local", hashed_password=oidc._hash_pw("x"),
                display_name="A", role="user", status="pending", is_active=True))
    db.commit()
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    state = r.headers["location"].split("state=")[1]
    r = client.get(f"/api/auth/oidc/callback?code=c&state={state}")
    assert r.status_code == 403


def test_oidc_callback_rejects_bad_signature(client, monkeypatch):
    """id_token 签名/发行方错误 → 401"""
    bad = pyjwt.encode(
        {"sub": "x", "email": "x@y.z", "iss": oidc.get_settings().OAUTH_CASDOOR_URL,
         "aud": oidc.get_settings().OAUTH_CLIENT_ID, "iat": datetime.now(timezone.utc),
         "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "not-a-key", algorithm="HS256",  # 用错误算法/密钥签名
    )
    monkeypatch.setattr(oidc, "_exchange_code", lambda code: {"id_token": bad})
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    state = r.headers["location"].split("state=")[1]
    r = client.get(f"/api/auth/oidc/callback?code=c&state={state}")
    assert r.status_code == 401


def test_oidc_callback_token_exchange_failure(client, monkeypatch):
    """IdP token 端点异常 → 502"""
    def _boom(code):
        raise __import__("httpx").ConnectError("idp down")
    monkeypatch.setattr(oidc, "_exchange_code", _boom)
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    state = r.headers["location"].split("state=")[1]
    r = client.get(f"/api/auth/oidc/callback?code=c&state={state}")
    assert r.status_code == 502
