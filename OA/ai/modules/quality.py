# ai/modules/quality.py — 质量 AI 咨询
from prompts import quality as prompts


def consult(context: dict, llm) -> dict:
    user_msg = prompts.Q_INSPECTION.format(**context)
    return llm.chat_json(prompts.SYSTEM_PROMPT, user_msg)
