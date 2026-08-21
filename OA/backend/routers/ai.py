"""routers/ai.py — 统一 AI 咨询入口（所有模块通用）+ AI 审批自动化"""
from routers.auth import require_auth, CurrentUser
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Any, Dict

from services.auto_approval import (
    review_document, review_all_pending,
    execute_recommendation, batch_execute,
    save_threshold, delete_threshold, list_thresholds,
    ApprovalThreshold, DEFAULT_THRESHOLDS,
)

router = APIRouter(prefix="/api/ai", tags=["AI"])



class AIConsultRequest(BaseModel):
    module: str        # procurement / finance / quality / compliance / project / crm / hr
    context: Dict[str, Any]   # 单据数据上下文


@router.post("/consult")
def ai_consult(req: AIConsultRequest, current_user: CurrentUser = Depends(require_auth)):
    """
    通用 AI 咨询入口
    - module: 业务模块名
    - context: 单据数据上下文字典
    返回: {"advice": "...", "risk_flags": [...], "suggestions": [...]}
    """

    # 业务规则 + AI 策略库（本地规则引擎，无外部依赖）
    module = req.module.lower()
    ctx = req.context

    if module == "procurement":
        return _ai_procurement_consult(ctx)
    elif module == "finance":
        return _ai_finance_consult(ctx)
    elif module == "quality":
        return _ai_quality_consult(ctx)
    elif module == "compliance":
        return _ai_compliance_consult(ctx)
    elif module == "project":
        return _ai_project_consult(ctx)
    elif module == "crm":
        return _ai_crm_consult(ctx)
    elif module == "hr":
        return _ai_hr_consult(ctx)
    else:
        return {
            "advice": f"{module} 模块 AI 咨询逻辑已注册，待注入 LLM 能力",
            "risk_flags": [],
            "suggestions": ["配置 OPENAI_API_KEY 后启用 LLM 增强"],
        }


# ── 各模块 AI 咨询策略 ─────────────────────────────────────────

def _ai_procurement_consult(ctx: dict) -> dict:
    """采购 AI：价格合理性 + 供应商风险 + 交期"""
    amount = ctx.get("amount", 0)
    supplier = ctx.get("supplier", "")
    risk_flags = []
    suggestions = []

    if amount > 500000:
        risk_flags.append("单笔金额超过50万，需审批流升级")
    if not supplier:
        risk_flags.append("缺少供应商信息")

    if amount < 10000:
        suggestions.append("建议走快速采购通道（单据直批）")
    elif amount > 100000:
        suggestions.append("建议要求3家供应商比价")

    return {
        "advice": f"采购金额 {amount} 元，供应商：{supplier or '未指定'}",
        "risk_flags": risk_flags,
        "suggestions": suggestions,
        "score": min(100, 80 if amount < 50000 else 60),
    }


def _ai_finance_consult(ctx: dict) -> dict:
    """财务 AI：发票合规 + 报销规范"""
    amount = ctx.get("amount", 0)
    category = ctx.get("category", "")
    risk_flags = []
    suggestions = []

    if amount > 50000 and category == "待分类":
        risk_flags.append("大额发票未分类，存在税务风险")

    if category in ("差旅费用", "市场营销"):
        suggestions.append(f"{category}类发票需附行程/投放证明")

    return {
        "advice": f"发票金额 {amount} 元，分类：{category}",
        "risk_flags": risk_flags,
        "suggestions": suggestions,
    }


def _ai_quality_consult(ctx: dict) -> dict:
    """质量 AI：检测参数 + 判定"""
    readings = ctx.get("readings", [])
    params = ctx.get("inspection_parameters", [])
    risk_flags = []

    if not readings or not params:
        return {"advice": "缺少检测数据，无法判定", "risk_flags": ["数据不足"], "suggestions": ["完善检测参数"]}

    for reading, param in zip(readings, params):
        val = reading.get("value", 0)
        min_val = param.get("min_value", 0)
        max_val = param.get("max_value", 999999)
        if val < min_val or val > max_val:
            risk_flags.append(f"参数 {param.get('parameter','?')} 值 {val} 超范围 [{min_val},{max_val}]")

    return {
        "advice": f"检测 {len(readings)} 项，异常 {len(risk_flags)} 项",
        "risk_flags": risk_flags,
        "suggestions": ["超标项需复检或降级处理"],
        "decision": "PASS" if not risk_flags else "FAIL",
    }


def _ai_compliance_consult(ctx: dict) -> dict:
    """合规 AI：合同风险 + 条款评估"""
    content = (ctx.get("content") or "").lower()
    risk_flags = []
    suggestions = []

    import re
    high_risk = [
        (r"违约金.*[5-9]0%|违约金.*[1-9][0-9]0%", "违约金比例过高"),
        (r"永久.*保密|无限期.*保密", "保密条款无限期"),
        (r"独家|排他", "排他性条款需评估业务影响"),
    ]
    for pattern, msg in high_risk:
        if re.search(pattern, content):
            risk_flags.append(msg)

    if not risk_flags:
        suggestions.append("合同条款风险评估正常")

    return {
        "advice": f"合同风险扫描完成，发现 {len(risk_flags)} 项风险",
        "risk_flags": risk_flags,
        "suggestions": suggestions or ["条款基本合规"],
    }


def _ai_project_consult(ctx: dict) -> dict:
    """项目 AI：进度 + 资源"""
    progress = ctx.get("progress", 0)
    status = ctx.get("status", "Open")
    risk_flags = []
    suggestions = []

    if status == "Open" and progress < 5 and ctx.get("days_since_start", 0) > 14:
        risk_flags.append("项目启动14天但进度<5%，存在拖延风险")

    if ctx.get("assigned_count", 1) == 0:
        risk_flags.append("项目未分配负责人")

    return {
        "advice": f"项目进度 {progress}%，状态：{status}",
        "risk_flags": risk_flags,
        "suggestions": suggestions or ["进度正常"],
    }


def _ai_crm_consult(ctx: dict) -> dict:
    """CRM AI：线索评分 + 跟进建议"""
    score = ctx.get("score", 0)
    level = ctx.get("level", "D")

    if level == "A":
        suggestions = ["24小时内必须跟进", "优先安排高管接待"]
    elif level == "B":
        suggestions = ["3天内跟进", "提供方案型内容"]
    elif level == "C":
        suggestions = ["7天内跟进", "培育型内容推送"]
    else:
        suggestions = ["归档定期维护池", "批量营销触达"]

    return {
        "advice": f"线索评分 {score}分，等级：{level}",
        "risk_flags": [],
        "suggestions": suggestions,
    }


def _ai_hr_consult(ctx: dict) -> dict:
    """HR AI：员工状态"""
    status = ctx.get("status", "Active")
    risk_flags = []
    suggestions = []

    if status == "Inactive":
        risk_flags.append("员工账号已停用，需确认离职手续")
    suggestions.append("建议定期盘点员工数据准确性")

    return {
        "advice": f"员工状态：{status}",
        "risk_flags": risk_flags,
        "suggestions": suggestions,
    }


# ═══════════════════════════════════════════════════════════════
# AI 审批自动化端点（/api/ai/approval/*）
# ═══════════════════════════════════════════════════════════════

# 状态机引用（供端点校验使用）
TABLE_MAP_REF = {
    "ExpenseClaim", "PurchaseOrder", "JournalEntry",
    "LeaveRequest", "Contract", "StockEntry", "Project",
}


class ApprovalReviewRequest(BaseModel):
    doctype: str       # ExpenseClaim / LeaveRequest / StockEntry / ...
    doc_name: str      # 单据名称（如 EXP-001）


class ApprovalExecuteRequest(BaseModel):
    doctype: str
    doc_name: str
    action: str        # approve / reject / flag
    comment: Optional[str] = "AI自动审批"


class ApprovalBatchRequest(BaseModel):
    execute_all: bool = False  # true=执行所有 auto/reject 建议


class ThresholdRequest(BaseModel):
    doctype: str
    auto_approve_amount: float = 0.0
    auto_approve_max_days: int = 0
    require_llm_review: bool = False
    risk_keywords: str = ""
    notes: str = ""


@router.post("/approval/review")
def ai_approval_review(
    req: ApprovalReviewRequest,
    current_user: CurrentUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    对单个待审单据进行 AI 审批审查。
    返回 AI 的建议（auto/manual/reject），不执行实际状态变更。
    """
    if req.doctype not in TABLE_MAP_REF:
        raise HTTPException(400, f"不支持的单据类型: {req.doctype}")
    return review_document(db, req.doctype, req.doc_name)


@router.post("/approval/review-all")
def ai_approval_review_all(
    current_user: CurrentUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    扫描所有待审单据，逐个 AI 审查。
    返回建议列表 + 汇总统计。不执行状态变更。
    """
    return review_all_pending(db)


@router.post("/approval/execute")
def ai_approval_execute(
    req: ApprovalExecuteRequest,
    current_user: CurrentUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    执行单条 AI 审批决策（approve/reject/flag）。
    执行后写入 WorkflowHistory（operator='ai_agent'）+ 通知 admin。
    """
    return execute_recommendation(
        db, req.doctype, req.doc_name, req.action, req.comment
    )


@router.post("/approval/batch-execute")
def ai_approval_batch_execute(
    req: ApprovalBatchRequest,
    current_user: CurrentUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    先审查所有待审单据，再批量执行 AI 建议。
    - execute_all=true: 执行所有 auto 和 reject 建议
    - execute_all=false: 仅审查，不执行
    """
    result = review_all_pending(db)
    if not req.execute_all:
        return result

    exec_result = batch_execute(db, result["recommendations"])
    return {
        "review": result,
        "execution": exec_result,
    }


# ── 审批阈值配置 ──────────────────────────────────────────────

@router.get("/approval/thresholds")
def ai_approval_thresholds_list(
    current_user: CurrentUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """获取所有单据类型的审批阈值配置"""
    return list_thresholds(db)


@router.put("/approval/threshold")
def ai_approval_threshold_update(
    req: ThresholdRequest,
    current_user: CurrentUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """保存/更新指定单据类型的审批阈值"""
    threshold = ApprovalThreshold(
        doctype=req.doctype,
        auto_approve_amount=req.auto_approve_amount,
        auto_approve_max_days=req.auto_approve_max_days,
        require_llm_review=req.require_llm_review,
        risk_keywords=req.risk_keywords,
        notes=req.notes,
    )
    save_threshold(db, threshold)
    return {"ok": True, "threshold": threshold.to_dict()}


@router.delete("/approval/threshold")
def ai_approval_threshold_delete(
    doctype: str,
    current_user: CurrentUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """删除指定单据类型的审批阈值（恢复为人工审核）"""
    delete_threshold(db, doctype)
    return {"ok": True, "deleted": doctype}
