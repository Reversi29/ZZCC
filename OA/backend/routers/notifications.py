"""
routers/notifications.py — 统一通知中心 (P3.13)
渠道: 站内(inapp) / 企业微信(wecom) / 钉钉(dingtalk) / 邮件(email) / 通用webhook(legacy)
配置驱动: 未启用则静默跳过; 任一渠道失败不影响站内 + 其他渠道。
"""
import os
import json
import time
import base64
import hmac
import hashlib
import smtplib
import ssl
import logging
import urllib.request
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import Notification
from routers.auth import get_current_user, CurrentUser

logger = logging.getLogger("notifications")
router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ── 渠道配置读取 ──────────────────────────────────────────────
def _wecom_webhook() -> str:
    return os.getenv("OA_WECOM_WEBHOOK", "")


def _dingtalk_cfg() -> tuple:
    return os.getenv("OA_DINGTALK_WEBHOOK", ""), os.getenv("OA_DINGTALK_SECRET", "")


def _email_cfg() -> dict:
    host = os.getenv("OA_SMTP_HOST", "")
    if not host:
        return {}
    return {
        "host": host,
        "port": int(os.getenv("OA_SMTP_PORT", "587")),
        "user": os.getenv("OA_SMTP_USER", ""),
        "password": os.getenv("OA_SMTP_PASS", ""),
        "from": os.getenv("OA_SMTP_FROM", os.getenv("OA_SMTP_USER", "")),
        "to": [x.strip() for x in os.getenv("OA_SMTP_TO", "").split(",") if x.strip()],
        "tls": os.getenv("OA_SMTP_TLS", "true").lower() != "false",
    }


def _legacy_webhook() -> str:
    return os.getenv("OA_WEBHOOK_URL", "")


def enabled_channels() -> list:
    """返回所有渠道启用状态 (供前端展示 + 配置 API)"""
    dt_webhook, _ = _dingtalk_cfg()
    email = _email_cfg()
    return [
        {"id": "inapp", "name": "站内通知", "enabled": True},
        {"id": "wecom", "name": "企业微信", "enabled": bool(_wecom_webhook())},
        {"id": "dingtalk", "name": "钉钉", "enabled": bool(dt_webhook)},
        {"id": "email", "name": "邮件(SMTP)", "enabled": bool(email)},
        {"id": "webhook", "name": "通用Webhook(旧)", "enabled": bool(_legacy_webhook())},
    ]


# ── 各渠道发送 ────────────────────────────────────────────────
def _post_json(url: str, payload: dict, timeout: int = 5) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=timeout)


def _push_wecom(title: str, body: str) -> None:
    url = _wecom_webhook()
    if not url:
        return
    content = "### {}\n{}".format(title, body)
    _post_json(url, {"msgtype": "markdown", "markdown": {"content": content}})


def _push_dingtalk(title: str, body: str) -> None:
    webhook, secret = _dingtalk_cfg()
    if not webhook:
        return
    content = "#### {}\n{}".format(title, body)
    payload = {"msgtype": "markdown", "markdown": {"title": title, "text": content}}
    if secret:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = "{}\n{}".format(timestamp, secret)
        hmac_code = hmac.new(secret.encode("utf-8"),
                             string_to_sign.encode("utf-8"),
                             hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        sep = "&" if "?" in webhook else "?"
        webhook = "{}{}timestamp={}&sign={}".format(webhook, sep, timestamp, sign)
    _post_json(webhook, payload)


def _push_email(title: str, body: str, recipient: str = None) -> None:
    cfg = _email_cfg()
    if not cfg or not cfg["to"]:
        return
    lines = ["From: {}".format(cfg["from"]),
             "To: {}".format(", ".join(cfg["to"])),
             "Subject: {}".format(title),
             "", body]
    if recipient:
        lines.append("")
        lines.append("(接收人: {})".format(recipient))
    msg = "\n".join(lines).encode("utf-8")
    smtp = smtplib.SMTP(cfg["host"], cfg["port"], timeout=10)
    try:
        if cfg["tls"]:
            smtp.starttls(context=ssl.create_default_context())
        if cfg["user"]:
            smtp.login(cfg["user"], cfg["password"])
        smtp.sendmail(cfg["from"], cfg["to"], msg)
    finally:
        smtp.quit()


def _push_legacy(title: str, body: str) -> None:
    url = _legacy_webhook()
    if not url:
        return
    _post_json(url, {"msgtype": "text", "text": {"content": "{}\n{}".format(title, body)}})


def push_external(title: str, body: str, recipient: str = None) -> None:
    """按配置路由到所有启用的外部渠道。任一失败不影响其他渠道 + 站内。"""
    errors = []
    for fn in (_push_wecom, _push_dingtalk, _push_email, _push_legacy):
        try:
            if fn is _push_email:
                fn(title, body, recipient)
            else:
                fn(title, body)
        except Exception as e:  # 静默降级
            errors.append(str(e))
    if errors:
        logger.warning("external push partial failure: %s", errors)


def notify(db: Session, recipient: str, title: str, body: str,
           ntype: str = "approval_result", doctype: str = None,
           doc_name: str = None, action: str = None,
           priority: str = "normal") -> None:
    """写一条站内通知并推送到所有外部渠道"""
    db.add(Notification(
        recipient=recipient, title=title, body=body, ntype=ntype,
        doctype=doctype, doc_name=doc_name, action=action, priority=priority,
    ))
    try:
        push_external(title, body, recipient)
    except Exception:
        pass


# ── API ───────────────────────────────────────────────────────
@router.get("/channels")
def get_channels(current_user: CurrentUser = Depends(get_current_user)):
    """返回各通知渠道的启用状态"""
    return {"channels": enabled_channels()}
