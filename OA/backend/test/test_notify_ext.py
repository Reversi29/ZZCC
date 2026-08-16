"""test_notify_ext.py — P1.6 外部通知推送（webhook，配置驱动降级）"""
import urllib.request


def _create_exp(client, headers):
    r = client.post("/api/resource/Expense%20Claim", headers=headers, json={
        "employee": "alice", "title": "差旅报销", "claim_amount": 100.0,
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]["name"]


def test_webhook_push_on_submit(monkeypatch, client, auth_headers):
    """配置 OA_WEBHOOK_URL 后，提交单据应触发 webhook 推送"""
    monkeypatch.setenv("OA_WEBHOOK_URL", "http://hook.test/x")
    calls = []

    class FakeResp:
        status = 200

    def fake_urlopen(req, timeout=5):
        calls.append(req)
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    name = _create_exp(client, auth_headers)
    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "submit"})
    assert r.status_code == 200
    assert len(calls) >= 1
    assert b"text" in calls[0].data  # webhook payload 含 text 消息体


def test_no_webhook_when_unconfigured(client, auth_headers):
    """未配置 webhook 时提交不报错（仅站内）"""
    name = _create_exp(client, auth_headers)
    r = client.post("/api/workflow/action", headers=auth_headers,
                    json={"name": name, "action": "submit"})
    assert r.status_code == 200
