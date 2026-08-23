"""routers/module_toggle.py — 模块开关"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, Column, Integer, String, DateTime
from sqlalchemy.orm import Session

from database import get_db, Base
from routers.auth import require_admin

router = APIRouter(prefix="/api/module-toggle", tags=["module-toggle"])
R = dict

FIXED_MODULES = {"dashboard", "workflow", "auth", "notifications", "users"}

OPTIONAL_MODULES = {
    "announcements": "公告栏",
    "calendar": "日历",
    "directory": "通讯录",
    "reports": "日报周报",
    "meetings": "会议纪要",
    "forms": "表单设计",
    "netdrive": "企业网盘",
    "analytics": "统计概览",
    "crm": "CRM线索",
    "contacts": "联系人",
    "opportunities": "CRM商机",
    "project": "项目管理",
    "tasks": "任务管理",
    "procurement": "采购",
    "finance": "财务",
    "compliance": "合同管理",
    "quality": "质量检验",
    "tickets": "客服工单",
    "hr": "人力资源",
    "departments": "部门管理",
    "leaves": "请假管理",
    "attendance": "考勤管理",
    "salary": "薪资记录",
    "stock": "资产行政",
    "ai": "AI咨询",
    "approval-rules": "审批规则",
    "budget": "预算管理",
    "suppliers": "供应商",
    "notification-settings": "通知设置",
    "registrations": "账号管理",
    "assets": "固定资产",
    "performance": "绩效考核",
    "recruitment": "招聘管理",
    "audit-log": "操作日志",
    "profile": "个人资料",
    "settings": "个人设置",
}


class SystemSettings(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(String(500), default="")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


def _ensure_table(db: Session):
    if "system_settings" not in Base.metadata.tables:
        SystemSettings.__table__.create(bind=db.get_bind(), checkfirst=True)


class ToggleReq(BaseModel):
    module_id: str
    enabled: bool


@router.get("/status")
def get_status(db: Session = Depends(get_db), _=Depends(require_admin)):
    _ensure_table(db)
    toggles = db.execute(
        select(SystemSettings).where(SystemSettings.key.like("module_%"))
    ).scalars().all()
    toggle_map = {t.key[7:]: t.value == "1" for t in toggles}
    result = {m: True for m in FIXED_MODULES}
    for m in OPTIONAL_MODULES:
        result[m] = toggle_map.get(m, True)
    enabled = sum(1 for v in result.values() if v)
    return R(total=len(result), enabled=enabled, disabled=len(result)-enabled, modules=result)


@router.patch("/toggle")
def toggle_module(body: ToggleReq, db: Session = Depends(get_db), _=Depends(require_admin)):
    if body.module_id in FIXED_MODULES:
        raise HTTPException(400, f"模块 {body.module_id} 不可关闭")
    if body.module_id not in OPTIONAL_MODULES:
        raise HTTPException(404, f"未知模块 {body.module_id}")
    _ensure_table(db)
    key = f"module_{body.module_id}"
    now = datetime.now()
    existing = db.execute(select(SystemSettings).where(SystemSettings.key == key)).scalar_one_or_none()
    if existing:
        existing.value = "1" if body.enabled else "0"
        existing.updated_at = now
    else:
        db.add(SystemSettings(key=key, value="1" if body.enabled else "0", created_at=now, updated_at=now))
    db.commit()
    return R(module_id=body.module_id, enabled=body.enabled)


@router.get("/list")
def list_modules():
    items = [R(module_id=m, name=n, can_disable=True) for m, n in OPTIONAL_MODULES.items()]
    items += [R(module_id=m, name=m, can_disable=False) for m in sorted(FIXED_MODULES)]
    return items
