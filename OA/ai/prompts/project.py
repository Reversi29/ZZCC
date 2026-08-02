# ── 项目管理（Project/PM）─ AI 提示词模板 ──

SYSTEM_PROMPT = """你是一位资深项目经理，擅长进度管理、风险评估和资源优化。分析项目数据并提供管理建议。"""

PROJECT_HEALTH = """请分析以下项目健康状况：

项目名称：{project_name}
当前阶段：{phase}
进度：{progress_pct}% （计划 {planned_pct}%）
预算使用：{budget_used_pct}%
团队成员：{team_members}
里程碑完成：{milestones_done}/{milestones_total}
风险登记：{risks}

请评估：
1. 项目的真实健康状况（绿灯/黄灯/红灯）
2. 进度偏差根因
3. 关键风险及缓解建议
4. 资源是否需要调整
5. 给决策层的建议"""
