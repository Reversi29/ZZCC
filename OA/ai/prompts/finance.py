# ── 财务（Finance）─ AI 提示词模板 ──

SYSTEM_PROMPT = """你是一位资深财务分析师，擅长会计分录审核、发票合规检查、异常交易检测和税务风险评估。"""

INVOICE_CHECK = """请审核以下发票信息：

发票号：{invoice_no}
金额：{amount}
供应商：{supplier}
费用类型：{expense_type}
提交人：{submitted_by}
备注：{remarks}

请检查：
1. 发票信息完整性和合规性
2. 费用合理性（相比历史同类支出）
3. 是否存在虚假或重复报销风险
4. 税务风险提示

输出 JSON 格式：风险等级 + 详细理由。"""

BUDGET_ALERT = """预算执行情况：
部门：{department}
月度预算：{budget}
已用预算：{used_budget}
当前请求金额：{request_amount}

请分析：
1. 预算使用率是否过高
2. 是否需要预警
3. 建议措施"""
