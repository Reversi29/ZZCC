# -*- coding: utf-8 -*-
# oa_ai — ZZCC OA AI Integration App
# ERPNext 自定义应用：为每个业务模块挂载 AI Agent
from __future__ import unicode_literals

app_name = "oa_ai"
app_title = "ZZCC OA AI"
app_publisher = "ZZCC"
app_description = "企业AI咨询与自动化"
app_icon = "octicon octicon-bot"
app_color = "#2563eb"
app_email = "admin@zzcc.local"
app_license = "MIT"

# ── DocType 自动发现 ──────────────────────
# Frappe 会自动发现这个目录下的 DocType

# ── 自定义 Fixtures ──────────────────────
# fixtures = ["Custom Field", "DocType"]

# ── 集成点：注入到 ERPNext 标准模块 ──────
doctype_js = {
    "Sales Invoice": "public/js/sales_invoice_ai.js",
    "Purchase Order": "public/js/purchase_order_ai.js",
    "Project": "public/js/project_ai.js",
    "Issue": "public/js/issue_ai.js",
    "Contract": "public/js/contract_ai.js",
    "Quality Inspection": "public/js/quality_inspection_ai.js",
}

# ── API 路由 ──────────────────────────────
app_include_js = [
    "oa_ai.bundle.js"
]

# ── 权限 ──────────────────────────────────
# 不需要额外权限，依赖 ERPNext 自有 Role

# ── 调度任务 ──────────────────────────────
scheduler_events = {
    "all": [
        "oa_ai.tasks.auto_classify_purchases"
    ],
    "hourly": [
        "oa_ai.tasks.sync_ai_insights"
    ],
    "daily": [
        "oa_ai.tasks.daily_compliance_check"
    ]
}
