# ── 人力资源（HR）─ AI 提示词模板 ──

SYSTEM_PROMPT = """你是一位人力资源顾问，擅长招聘评估、绩效分析和团队建设。"""

PERFORMANCE = """请分析以下绩效考核数据：

员工：{employee}
岗位：{role}
考核周期：{period}
KPI达成率：{kpi_pct}%
关键成果：{key_results}
自评：{self_review}
上级评语：{manager_review}

请：
1. 综合绩效评级（S/A/B/C/D）及理由
2. 突出的优势和短板
3. 培训和发展建议
4. 薪酬调整建议范围"""
