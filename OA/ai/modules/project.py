# ai/modules/project.py — 项目管理 AI 咨询
from prompts import project as prompts


def consult(context: dict, llm) -> dict:
    user_msg = prompts.PROJECT_HEALTH.format(**context)
    return llm.chat_json(prompts.SYSTEM_PROMPT, user_msg)
