# ai/modules/customer_service.py — 客服 AI 咨询
from prompts import customer_service as prompts


def consult(context: dict, llm) -> dict:
    """售后/售前咨询"""
    is_presales = context.get("type") == "presales"
    if is_presales:
        user_msg = prompts.PRE_SALES.format(**context)
    else:
        user_msg = prompts.AFTER_SALES.format(**context)

    result = llm.chat_json(prompts.SYSTEM_PROMPT, user_msg)
    result["type"] = "presales" if is_presales else "aftersales"
    return result
