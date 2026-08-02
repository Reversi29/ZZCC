# ai/modules/crm.py — 商务/CRM AI 咨询
from prompts import crm as prompts


def consult(context: dict, llm) -> dict:
    """通用 CRM 咨询（自动判断线索评分 vs 商机分析）"""
    is_lead = context.get("type") == "lead"
    user_msg = (prompts.LEAD_SCORE if is_lead else prompts.DEAL_REVIEW).format(**context)
    return llm.chat_json(prompts.SYSTEM_PROMPT, user_msg)
