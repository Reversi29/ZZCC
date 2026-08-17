"""test_notifications.py — P3.13 多渠道通知 (企业微信/钉钉/邮件/通用webhook)

验证: 配置驱动路由 / 钉钉加签 / 邮件SMTP / 未配置静默 / 渠道失败隔离 / 配置API
"""
import urllib.request
import smtplib
from routers import notifications as N


class _FakeResp:
    status = 200


def _fake_urlopen_factory(calls):
    def _fake(req, timeout=5):
        calls.append({"url": req.full_url, "data": req.data, "headers": dict(req.headers)})
        return _FakeResp()
    return _fake


class _FakeSMTP:
    def __init__(self, host=None, port=None, timeout=None):
        self.host = host
        self.port = port
        self.sent = []
        self.started = False
        self.logged = False

    def starttls(self, context=None):
        self.started = True

    def login(self, user, pw):
        self.logged = True

    def sendmail(self, frm, to, msg):
        self.sent.append((frm, to, msg))

    def quit(self):
        pass


def test_wecom_markdown(monkeypatch):
    """配置了企业微信 webhook 时推 markdown 格式"""
    monkeypatch.setenv("OA_WECOM_WEBHOOK", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc")
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(calls))
    N.push_external("报销审批", "张三提交了100元")
    assert len(calls) == 1
    payload = __import__("json").loads(calls[0]["data"])
    assert payload["msgtype"] == "markdown"
    assert "报销审批" in payload["markdown"]["content"]


def test_dingtalk_sign(monkeypatch):
    """配置了钉钉 webhook + secret 时 URL 带 timestamp & sign 签名"""
    monkeypatch.setenv("OA_DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=xyz")
    monkeypatch.setenv("OA_DINGTALK_SECRET", "SEC123")
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(calls))
    N.push_external("待审批", "李四提交")
    assert len(calls) == 1
    url = calls[0]["url"]
    assert "timestamp=" in url
    assert "sign=" in url
    payload = __import__("json").loads(calls[0]["data"])
    assert payload["msgtype"] == "markdown"


def test_email_smtp(monkeypatch):
    """配置了 SMTP 时通过 smtplib 发送邮件"""
    monkeypatch.setenv("OA_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("OA_SMTP_PORT", "587")
    monkeypatch.setenv("OA_SMTP_USER", "oa@example.com")
    monkeypatch.setenv("OA_SMTP_PASS", "pass")
    monkeypatch.setenv("OA_SMTP_FROM", "oa@example.com")
    monkeypatch.setenv("OA_SMTP_TO", "admin@example.com, boss@example.com")
    fake = _FakeSMTP()
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: fake)
    N.push_external("标题", "正文", recipient="admin")
    assert len(fake.sent) == 1
    frm, to, msg = fake.sent[0]
    assert frm == "oa@example.com"
    assert set(to) == {"admin@example.com", "boss@example.com"}
    assert b"Subject: " in msg
    assert "接收人: admin" in msg.decode("utf-8")


def test_no_channel_silent(monkeypatch):
    """未配置任何外部渠道时不发送、不抛异常"""
    for k in ("OA_WECOM_WEBHOOK", "OA_DINGTALK_WEBHOOK", "OA_DINGTALK_SECRET",
             "OA_SMTP_HOST", "OA_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(calls))
    fake = _FakeSMTP()
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: fake)
    N.push_external("t", "b")  # 不应抛
    assert len(calls) == 0
    assert len(fake.sent) == 0


def test_channel_failure_isolated(monkeypatch):
    """单个渠道失败不影响其他渠道 (静默降级)"""
    monkeypatch.setenv("OA_WECOM_WEBHOOK", "https://wecom")
    monkeypatch.setenv("OA_WEBHOOK_URL", "https://legacy")
    calls = []

    def _boom(req, timeout=5):
        if "wecom" in req.full_url:
            raise RuntimeError("wecom down")
        calls.append(req)
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    N.push_external("t", "b")  # 不应抛
    # legacy 仍应成功发送
    assert len(calls) == 1
    assert "legacy" in calls[0].full_url


def test_legacy_webhook_text(monkeypatch):
    """向后兼容: 旧 OA_WEBHOOK_URL 仍推 text 格式"""
    monkeypatch.setenv("OA_WEBHOOK_URL", "https://hook.old/x")
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(calls))
    N.push_external("标题", "正文")
    assert len(calls) == 1
    payload = __import__("json").loads(calls[0]["data"])
    assert payload["msgtype"] == "text"
    assert "标题" in payload["text"]["content"]


def test_channels_api(client, auth_headers):
    """GET /api/notifications/channels 返回启用状态结构"""
    r = client.get("/api/notifications/channels", headers=auth_headers)
    assert r.status_code == 200
    ch = {c["id"]: c for c in r.json()["channels"]}
    assert set(ch.keys()) == {"inapp", "wecom", "dingtalk", "email", "webhook"}
    assert ch["inapp"]["enabled"] is True


def test_channels_api_requires_auth(client):
    """未带 token 时拒绝访问"""
    r = client.get("/api/notifications/channels")
    assert r.status_code in (401, 403)
