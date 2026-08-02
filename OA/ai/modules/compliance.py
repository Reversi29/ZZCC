# ai/modules/compliance.py — 法务合规 AI 咨询
from prompts import compliance as prompts


def consult(context: dict, llm) -> dict:
    """合同审查"""
    user_msg = prompts.CONTRACT_REVIEW.format(
        contract_title=context.get("title", "N/A"),
        party_a=context.get("party_a", "N/A"),
        party_b=context.get("party_b", "N/A"),
        amount=context.get("amount", "N/A"),
        term=context.get("term", "N/A"),
        clauses_summary=context.get("clauses", ""),
        attachments=context.get("attachments", ""),
    )
    return llm.chat_json(prompts.SYSTEM_PROMPT, user_msg)


def ip_risk_check(context: dict, llm) -> dict:
    """知识产权风险评估"""
    user_msg = prompts.IP_RISK.format(
        ip_type=context.get("ip_type", "software"),
        parties=context.get("parties", ""),
        description=context.get("description", ""),
    )
    return llm.chat_json(prompts.SYSTEM_PROMPT, user_msg)
