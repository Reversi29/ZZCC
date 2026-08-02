# ── 市场/商务（CRM/Marketing）─ AI 提示词模板 ──

SYSTEM_PROMPT = """你是一位商务拓展顾问，擅长客户画像分析、销售策略优化和谈判技巧指导。"""

LEAD_SCORE = """请评估以下销售线索：

客户：{lead_name}
公司：{company}
行业：{industry}
需求描述：{requirements}
预算范围：{budget}
决策周期：{decision_cycle}
联系人职位：{contact_role}
来源：{source}

请：
1. 线索质量评分（1-10）
2. 成单概率估算
3. 推荐跟进策略
4. 关键跟进要点

输出 JSON。"""

DEAL_REVIEW = """商务机会评估：

客户：{customer}
产品/服务：{product}
报价：{quote}
竞品报价参考：{competitor_info}
客户反馈：{feedback}
销售阶段：{stage}
已耗时：{days_in_pipeline}

请：
1. 成单概率更新
2. 是否需要调整报价策略
3. 主要成交障碍分析
4. 下一步行动建议"""
