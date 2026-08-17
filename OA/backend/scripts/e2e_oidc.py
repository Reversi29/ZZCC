"""P3.15 SSO — Casdoor 真实链路 E2E 验证

模拟浏览器完整走一遍 OIDC Authorization Code 流程：
1. GET /api/auth/oidc/login → 307 到 Casdoor authorize
2. 在 Casdoor 登录（表单 POST /login，真实用户 alice.sso）
3. 跟随 302 回 OA callback?code=...&state=...
4. OA 完成 JIT 建号并返回 HTML（注入 oa_token）
5. 用 oa_token 调 /api/auth/me 验证会话

用法：
  QClaw python:  "...python3.11" scripts/e2e_oidc.py
前置：Casdoor 已启动（docker compose -f docker-compose.casdoor.yml up -d），
      OA 服务已运行（8003）。
"""
import sys
import httpx

OA = "http://localhost:8003"
CAS = "http://localhost:8004"
APP = "zzcc-oa"
ORG = "zzcc"
USER = "alice.sso"
PASSWORD = "Passw0rd!"


def main() -> int:
    c = httpx.Client(follow_redirects=False, timeout=20)
    # 1. SSO 入口
    r = c.get(f"{OA}/api/auth/oidc/login")
    assert r.status_code == 307, f"login 入口应 307，实际 {r.status_code}: {r.text[:120]}"
    auth_url = r.headers["location"]
    print("[1] SSO 入口 307 ->", auth_url[:100])
    assert auth_url.startswith(f"{CAS}/login/oauth/authorize")

    # 2. 访问 Casdoor 授权页（带 cookie jar）
    r = c.get(auth_url)
    print(f"[2] Casdoor 授权页: {r.status_code} ({'登录页' if r.status_code == 200 else r.text[:80]})")

    # 3. 用 /api/login 建立 Casdoor 会话（JSON，返回 session cookie）
    #    注：/login 表单端点受验证码/字段约束，不可靠；标准 SSO 行为是用户先登录 IdP
    r = c.post(
        f"{CAS}/api/login",
        json={
            "type": "login",
            "organization": ORG,
            "username": USER,
            "password": PASSWORD,
            "application": APP,
        },
    )
    ok = r.json().get("status") == "ok"
    print(f"[3] Casdoor 登录: {'成功' if ok else '失败'} | {r.text[:120]}")
    if not ok:
        print("    检查：用户/密码正确性、组织 passwordType（需 bcrypt）")
        return 1
    assert "casdoor_session_id" in dict(c.cookies), "未拿到会话 cookie"

    # 3b. 带会话重新访问 authorize → 直接发 code 回 OA
    r = c.get(auth_url)
    loc = r.headers.get("location", "")
    if r.status_code in (301, 302, 303, 307, 308) and loc.startswith(f"{OA}/api/auth/oidc/callback?code="):
        print(f"[3b] 授权页识别会话 -> 302 {loc[:110]}")
        cb_url = loc
    else:
        print(f"[3b] 授权页未发 code: {r.status_code} {loc[:100]} {r.text[:80]}")
        return 1

    # 4. 访问 OA callback（JIT 建号）
    r = c.get(cb_url)
    assert r.status_code == 200, f"callback 应 200，实际 {r.status_code}: {r.text[:200]}"
    assert "oa_token" in r.text, "回调未注入 oa_token"
    print("[4] OA callback 200，JIT 建号完成")

    # 5. 提取 token 调 /api/auth/me
    import re
    token = re.search(r"localStorage.setItem\('oa_token', '([^']+)'\)", r.text).group(1)
    me = c.get(f"{OA}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    print(f"[5] /api/auth/me -> {me.status_code} {me.text[:160]}")
    assert me.status_code == 200
    print("\n✅ OIDC 全链路 E2E 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
