# ai/modules/hr.py — 人力资源 AI 咨询
from prompts import hr as prompts


def consult(context: dict, llm) -> dict:
    user_msg = prompts.PERFORMANCE.format(**context)
    return llm.chat_json(prompts.SYSTEM_PROMPT, user_msg)
