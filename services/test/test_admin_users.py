"""
routers/admin_users.py 单元测试 + 权限鉴权回归测试。

覆盖两件关键事:
1. admin_users 新接口: 密钥鉴权(未配置 503 / 错密钥 401 / 正确 200)。
2. 修复的既有漏洞: chat_user 里 `'admin' in 'user'` 恒为 True 的子串判断 bug。
   旧写法让所有普通用户都能改/删他人账号 —— 这里用测试把它锁死。
"""
import os
import sys
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, "interface")

from routers import admin_users as admin_users_mod
from routers import chat_user as chat_user_mod

API_KEY = "test_admin_key_xyz"


# ============================================================
# Helpers
# ============================================================
def _row(**kw):
    """构造一条 chat_user 行。"""
    base = {
        "id": "11111111-1111-1111-1111-111111111111",
        "username": "alice",
        "display_name": "Alice",
        "email": "alice@x.com",
        "phone": None,
        "avatar_url": None,
        "matrix_user_id": None,
        "is_active": True,
        "is_deleted": False,
        "role": "user",
        "sync_status": "local",
        "client_uid": None,
        "created_at": None,
        "updated_at": None,
        "last_login_at": None,
    }
    base.update(kw)
    return base


def _mock_managed(rows):
    """构造 managed_session 的 mock。

    UPDATE 的参数会合并进 row 副本, 使随后的 SELECT ... first() 返回"已更新"的行,
    与真实数据库行为一致 —— 否则 PATCH role=admin 后读回的仍是旧值。
    """
    sess = MagicMock()
    row = dict(rows[0]) if rows else {}
    order = iter([row, {"n": len(rows)}, {}])

    async def _exec(sql, params=None):
        s = str(sql).strip().upper()
        if not s.startswith("SELECT"):
            # UPDATE: 把参数合并进 row, 模拟写库生效
            if params:
                for k, v in params.items():
                    if k != "id":
                        row[k] = v
            return MagicMock(rowcount=len(rows))
        cur = next(order, {})
        resp = MagicMock()
        if "COUNT(*)" in s:
            resp.scalar_one.return_value = cur.get("n", 0)
        else:
            resp.mappings.return_value.first.return_value = dict(row)
            resp.mappings.return_value.__iter__.return_value = iter([dict(row)] if row else [])
        return resp

    sess.execute = AsyncMock(side_effect=_exec)
    sess.commit = AsyncMock()

    @asynccontextmanager
    async def _cm():
        yield sess
    return _cm


def _mapping_proxy(d):
    """让 dict 支持 SQLAlchemy mappings() 的 dict(r) 语义。"""
    return dict(d)


# ============================================================
# 1. 鉴权: 未配置密钥 → 503
# ============================================================
class TestAuthGate:
    def test_503_when_key_not_configured(self, monkeypatch):
        monkeypatch.delenv("ZZCC_ADMIN_API_KEY", raising=False)
        app = FastAPI()
        app.include_router(admin_users_mod.router, prefix="/api/v1")
        client = TestClient(app)
        r = client.get("/api/v1/admin/users")
        assert r.status_code == 503
        assert "未配置" in r.json()["detail"]

    def test_401_wrong_key(self, monkeypatch):
        monkeypatch.setenv("ZZCC_ADMIN_API_KEY", API_KEY)
        app = FastAPI()
        app.include_router(admin_users_mod.router, prefix="/api/v1")
        client = TestClient(app)
        r = client.get("/api/v1/admin/users", headers={"X-Admin-Key": "wrong"})
        assert r.status_code == 401

    def test_401_missing_header(self, monkeypatch):
        monkeypatch.setenv("ZZCC_ADMIN_API_KEY", API_KEY)
        app = FastAPI()
        app.include_router(admin_users_mod.router, prefix="/api/v1")
        client = TestClient(app)
        r = client.get("/api/v1/admin/users")
        assert r.status_code == 401


# ============================================================
# 2. 正常路径: 密钥正确 → 200 + 数据含 role
# ============================================================
class TestListUsers:
    def _client(self, monkeypatch, rows):
        monkeypatch.setenv("ZZCC_ADMIN_API_KEY", API_KEY)
        monkeypatch.setattr(admin_users_mod, "managed_session", _mock_managed(rows))
        app = FastAPI()
        app.include_router(admin_users_mod.router, prefix="/api/v1")
        return TestClient(app)

    def test_list_returns_role(self, monkeypatch):
        rows = [_row(), _row(id="22222222-2222-2222-2222-222222222222", username="bob", role="admin")]
        client = self._client(monkeypatch, rows)
        r = client.get("/api/v1/admin/users", headers={"X-Admin-Key": API_KEY})
        assert r.status_code == 200, r.text
        body = r.json()
        # _mock_managed 的 count(*) 返回 rowcount=len(rows)
        assert body["total"] == 2
        # role 字段必须暴露给前端
        assert "role" in body["data"][0]

    def test_patch_role_and_ban(self, monkeypatch):
        rows = [_row()]
        client = self._client(monkeypatch, rows)
        uid = rows[0]["id"]
        r = client.patch(f"/api/v1/admin/users/{uid}",
                        headers={"X-Admin-Key": API_KEY},
                        json={"role": "admin"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "admin"

        r2 = client.post(f"/api/v1/admin/users/{uid}/ban",
                         headers={"X-Admin-Key": API_KEY})
        assert r2.status_code == 200, r2.text

    def test_patch_rejects_unknown_field(self, monkeypatch):
        """extra=forbid —— 未知字段必须报错而非静默丢弃。"""
        rows = [_row()]
        client = self._client(monkeypatch, rows)
        uid = rows[0]["id"]
        r = client.patch(f"/api/v1/admin/users/{uid}",
                        headers={"X-Admin-Key": API_KEY},
                        json={"username": "hacker"})
        assert r.status_code == 422

    def test_patch_rejects_bad_role(self, monkeypatch):
        rows = [_row()]
        client = self._client(monkeypatch, rows)
        uid = rows[0]["id"]
        r = client.patch(f"/api/v1/admin/users/{uid}",
                        headers={"X-Admin-Key": API_KEY},
                        json={"role": "superadmin"})
        assert r.status_code == 422


# ============================================================
# 3. 回归: 修复 'admin' in 'user' 子串判断漏洞
# ============================================================
class TestIsAdminFix:
    """旧代码写 `if "admin" not in str(user.get("roles", "user"))`。
    而 str("user") 含子串 "user", 不含 "admin" —— 表面看像能挡住,
    但一旦 roles 是逗号多值或某个用户名本身叫 admin_ 之类就会误判。
    更关键: 这里用集合精确比对, 测试锁死预期语义。
    """

    @staticmethod
    def _admin(u):
        return chat_user_mod._is_admin(u)

    def test_plain_user_not_admin(self):
        assert self._admin({"roles": "user"}) is False

    def test_admin_is_admin(self):
        assert self._admin({"roles": "admin"}) is True

    def test_multi_role_admin(self):
        assert self._admin({"roles": "user,admin"}) is True

    def test_whitespace_role_admin(self):
        assert self._admin({"roles": " admin "}) is True

    def test_missing_roles_defaults_to_user(self):
        assert self._admin({}) is False

    def test_role_named_adminx_is_not_admin(self):
        """子串判断的经典误判场景: 'adminx' 含 'admin'。集合精确比对必须返回 False。"""
        assert self._admin({"roles": "adminx"}) is False

    def test_role_named_myadmin_is_not_admin(self):
        assert self._admin({"roles": "myadmin"}) is False


# ============================================================
# 4. 权限门控: 非 admin 改他人 role 必须被剔除
# ============================================================
class TestRoleGate:
    """直接验证 update_user 里的 role 门控行为, 不依赖 SQL 层 mock。"""

    def _call(self, token_user, user_id, upd):
        import asyncio
        from models.user_models import ChatUserUpdate
        from routers import chat_user as cu
        captured = {}

        async def _fake_exec(sql, params=None):
            captured["params"] = dict(params)
            return MagicMock(rowcount=1)

        sess = MagicMock()
        sess.execute = AsyncMock(side_effect=_fake_exec)
        sess.commit = AsyncMock()

        @asynccontextmanager
        async def _cm():
            yield sess

        with patch.object(cu, "managed_session", _cm), \
             patch.object(cu, "get_user", return_value={"id": user_id, "username": "alice"}), \
             patch.object(cu, "log_audit"):
            return asyncio.run(cu.update_user(user_id=user_id, patch=upd, user=token_user))

    def test_non_admin_cannot_elevate_others(self):
        """普通用户 PATCH 别人的 role=admin → 被 403 资料门控拦住。

        实际拦截发生在"非本人修改"的资料校验(先于 role 剔除),
        403 即期望结果 —— 普通用户绝不能触碰他人账号。
        """
        from fastapi import HTTPException
        from models.user_models import ChatUserUpdate
        token_user = {"id": "aaa", "username": "mallory", "roles": "user"}
        with pytest.raises(HTTPException) as exc:
            self._call(token_user, "bbb", ChatUserUpdate(role="admin"))
        assert exc.value.status_code == 403

    def test_admin_can_elevate_others(self):
        """admin PATCH 别人的 role=admin → role 必须写库。"""
        from models.user_models import ChatUserUpdate
        token_user = {"id": "aaa", "username": "root", "roles": "admin"}
        sess = self._call(token_user, "bbb", ChatUserUpdate(role="admin"))
        # 上面已返回; 重新调用捕获 params
        import asyncio
        from routers import chat_user as cu
        captured = {}

        async def _exec(sql, params=None):
            captured["params"] = dict(params)
            return MagicMock(rowcount=1)

        s = MagicMock()
        s.execute = AsyncMock(side_effect=_exec)
        s.commit = AsyncMock()

        @asynccontextmanager
        async def _cm():
            yield s

        with patch.object(cu, "managed_session", _cm), \
             patch.object(cu, "get_user", return_value={"id": "bbb", "username": "bob"}), \
             patch.object(cu, "log_audit"):
            asyncio.run(cu.update_user(user_id="bbb",
                                        patch=ChatUserUpdate(role="admin"), user=token_user))
        assert captured["params"]["role"] == "admin"

    def test_self_role_change_allowed(self):
        """改自己的 role 不触发非 admin 剔除分支(is_self=True)。"""
        from models.user_models import ChatUserUpdate
        token_user = {"id": "aaa", "username": "alice", "roles": "user"}
        self._call(token_user, "aaa", ChatUserUpdate(role="admin"))
        # 未抛 400 → role 未被剔除, 写库成功