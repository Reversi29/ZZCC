# ai/modules/procurement.py — 采购 AI 咨询
from prompts import procurement as prompts


def consult(context: dict, llm) -> dict:
    """采购 AI 咨询"""
    user_msg = "请分析以下采购数据：\n" + str(context)
    result = llm.chat_json(
        prompts.SYSTEM_PROMPT,
        user_msg,
    )
    return result
