# ai/modules/finance.py — 财务 AI 咨询
from prompts import finance as prompts


def consult(context: dict, llm) -> dict:
    user_msg = prompts.INVOICE_CHECK.format(
        invoice_no=context.get("invoice_no", "N/A"),
        amount=context.get("amount", "N/A"),
        supplier=context.get("supplier", "N/A"),
        expense_type=context.get("expense_type", "N/A"),
        submitted_by=context.get("submitted_by", "N/A"),
        remarks=context.get("remarks", ""),
    )
    return llm.chat_json(prompts.SYSTEM_PROMPT, user_msg)


def budget_alert(context: dict, llm) -> dict:
    user_msg = prompts.BUDGET_ALERT.format(**context)
    return llm.chat_json(prompts.SYSTEM_PROMPT, user_msg)
