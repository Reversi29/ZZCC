"""routers/notification_settings.py — 通知渠道配置管理 (P3.13)

提供:
- GET /api/notifications/settings — 当前配置
- PUT /api/notifications/settings — 更新渠道配置
- POST /api/notifications/settings/test — 发送测试通知
- POST /api/notifications/settings/trigger — 触发一条示例审批通知（全流程测试）
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal, Notification
from routers.auth import get_current_user, CurrentUser, require_admin
from routers.notifications import (
    _wecom_webhook, _dingtalk_cfg, _email_cfg, _legacy_webhook,
    enabled_channels, push_external, notify,
)

logger = logging.getLogger("notification_settings")
router = APIRouter(prefix="/api/notifications", tags=["notifications"])

SETTINGS_FILE = "/tmp/zzcc-oa-notification-settings.json"
DEFAULT_SETTINGS = {
    "wecom_webhook": "",
    "dingtalk_webhook": "",
    "dingtalk_secret": "",
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_pass": "",
    "smtp_from": "",
    "smtp_to": "",
    "smtp_tls": True,
    "webhook_url": "",
    "channels": {
        "wecom": False,
        "dingtalk": False,
        "email": False,
        "webhook": False,
    },
}


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
        # Merge with defaults
        merged = dict(DEFAULT_SETTINGS)
        for k in ("wecom_webhook", "dingtalk_webhook", "dingtalk_secret",
                   "smtp_host", "smtp_port", "smtp_user", "smtp_pass",
                   "smtp_from", "smtp_to", "smtp_tls", "webhook_url"):
            if k in saved:
                merged[k] = saved[k]
        if "channels" in saved:
            merged["channels"].update(saved["channels"])
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)


def save_settings(s: dict) -> None:
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def _apply_settings_to_env(s: dict) -> None:
    """将持久化配置同步到环境变量，使 notifications.py 读取最新值"""
    mapping = {
        "wecom_webhook": "OA_WECOM_WEBHOOK",
        "dingtalk_webhook": "OA_DINGTALK_WEBHOOK",
        "dingtalk_secret": "OA_DINGTALK_SECRET",
        "smtp_host": "OA_SMTP_HOST",
        "smtp_port": "OA_SMTP_PORT",
        "smtp_user": "OA_SMTP_USER",
        "smtp_pass": "OA_SMTP_PASS",
        "smtp_from": "OA_SMTP_FROM",
        "smtp_to": "OA_SMTP_TO",
        "smtp_tls": "OA_SMTP_TLS",
        "webhook_url": "OA_WEBHOOK_URL",
    }
    for key, env_name in mapping.items():
        val = s.get(key)
        if val is not None:
            os.environ[env_name] = str(val)
        else:
            os.environ.pop(env_name, None)


class NotificationSettings(BaseModel):
    wecom_webhook: str = ""
    dingtalk_webhook: str = ""
    dingtalk_secret: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_tls: bool = True
    webhook_url: str = ""
    channels: dict = DEFAULT_SETTINGS["channels"]


@router.get("/settings")
def get_settings(current_user: CurrentUser = Depends(get_current_user)):
    return load_settings()


@router.put("/settings")
def update_settings(body: NotificationSettings,
                    current_user: CurrentUser = Depends(require_admin)):
    s = body.model_dump()
    save_settings(s)
    _apply_settings_to_env(s)
    logger.info("notification settings updated by %s", current_user.username)
    return {"status": "ok", "channels": enabled_channels()}


@router.post("/settings/test")
def test_channels(body: NotificationSettings,
                  current_user: CurrentUser = Depends(require_admin)):
    """先保存配置再发送测试通知，返回各渠道结果"""
    s = body.model_dump()
    save_settings(s)
    _apply_settings_to_env(s)

    results = {}
    from routers.notifications import (
        _push_wecom, _push_dingtalk, _push_email, _push_legacy
    )
    for name, fn in [("wecom", _push_wecom), ("dingtalk", _push_dingtalk),
                     ("email", _push_email), ("webhook", _push_legacy)]:
        try:
            if name == "email":
                fn("🔔 OA 通知测试", "来自 {} 的测试通知 ({})".format(current_user.username, datetime.now().isoformat()))
            else:
                fn("🔔 OA 通知测试", "来自 {} 的测试通知".format(current_user.username))
            results[name] = "ok"
        except Exception as e:
            results[name] = "error: " + str(e)

    return {"status": "test_sent", "results": results}


@router.post("/settings/trigger")
def trigger_notification(current_user: CurrentUser = Depends(get_current_user)):
    """触发一条示例审批通知（全流程：DB + 外部推送）"""
    db = SessionLocal()
    try:
        notify(
            db,
            recipient="admin",
            title="🧪 测试审批通知",
            body="用户 {} 触发了测试通知 ({})".format(current_user.username, datetime.now().isoformat()),
            ntype="approval_result",
            doctype="Test",
            doc_name="TEST-001",
            action="trigger",
        )
        db.commit()
        return {"status": "ok", "message": "通知已创建"}
    finally:
        db.close()