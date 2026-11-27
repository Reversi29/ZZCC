"""services/brain/multimodal_dataset_builder.py — 多模态数据集构建器

从本地真实数据源构建训练样本，灌入 MultimodalDataset。

数据源（按可用性/许可/贴合度排序）：
  1. 本地真实图标图像 — flutter_chat_ui 图标（语义明确，无许可风险）
  2. 本地真实结构化表 — OA 业务模型（ExpenseClaim/PurchaseOrder 字段）
  3. 本地文本语料 — 业务话术（审批/报销/危险/紧急）

设计原则：
  - 离线构建：宿主机跑，产出纯 JSON，落 /app/config_data/multimodal_dataset.json
  - 不新增重依赖：只用 multimodal_features（stdlib+PIL）
  - 与 cognitive_coder 的 CONCEPT_NAMES 对齐

用法：
    from services.brain.multimodal_dataset_builder import build_dataset
    ds = build_dataset(icon_dir=..., oa_models=...)
    coder.contrastive_align(ds.samples(), eta=0.05)
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from services.brain.multimodal_features import MultimodalExtractor

# ── 图标语义 → 概念映射 ──
# icon-*.png 的语义直接对应 brain 概念。这是"无感映射"的核心：
# 同一语义在视觉模态（图标）和文本模态（话术）下应有相同概念激活。
ICON_CONCEPT_MAP: Dict[str, str] = {
    "icon-send": "approval",       # 发送=确认动作
    "icon-delivered": "approval",  # 已送达=完成
    "icon-seen": "approval",       # 已读=确认
    "icon-document": "query",      # 文档=查询/信息
    "icon-error": "danger",        # 错误=危险
    "icon-attachment": "query",    # 附件=待处理信息
    "icon-arrow": "urgency",       # 箭头=流程/推进
}

# ── 业务话术语料：概念 → 自然语言样本 ──
# 这些是 ZZCC OA 审批场景的真实业务用语
BIZ_TEXT_CORPUS: Dict[str, List[str]] = {
    "approval": [
        "同意，批准这个申请",
        "同意，通过审批",
        "同意报销申请",
        "批准差旅费用",
        "同意，付款吧",
        "approved",
        "ok，同意",
    ],
    "rejection": [
        "驳回，不同意",
        "驳回，超预算",
        "不同意，理由不充分",
        "rejected",
        "不同意报销",
    ],
    "danger": [
        "检测到危险信号，需要立即处理",
        "danger critical risk",
        "超预算审批，存在风险",
        "异常交易，风控触发",
        "金额异常，请核查",
    ],
    "urgency": [
        "紧急！这个审批必须马上处理",
        "urgent asap now",
        "加急报销，今天必须批",
        "紧急付款申请",
        "asap，立即处理",
    ],
    "query": [
        "请问这个怎么处理？",
        "查询申请进度",
        "这个单据状态是什么？",
        "请查一下审批状态",
        "query",
    ],
    "chitchat": [
        "hello 你好呀",
        "在吗",
        "hi，早上好",
        "good morning",
    ],
    "novelty": [
        "发现一个全新的东西",
        "新的报销类型",
        "未见过的项目类别",
        "new category",
    ],
}

# ── OA 真实业务单据 → 结构化样本 ──
# 字段取自 OA/backend/models/documents.py（ExpenseClaim/PurchaseOrder）
OA_TABLE_SAMPLES: List[Dict[str, Any]] = [
    {
        "concept": "approval",
        "payload": {
            "columns": 5, "rows": 6, "cells": 30,
            "fields": {"employee": "张三", "expense_type": "Travel",
                       "claim_amount": 500.0, "approval_status": "Submitted",
                       "purpose": "客户拜访"},
            "header": ["employee", "expense_type", "claim_amount",
                       "approval_status", "purpose"],
        },
        "text": "差旅报销申请，金额 500 元，客户拜访",
    },
    {
        "concept": "danger",
        "payload": {
            "columns": 5, "rows": 6, "cells": 30,
            "fields": {"employee": "李四", "expense_type": "Entertainment",
                       "claim_amount": 88000.0, "approval_status": "Submitted",
                       "purpose": "客户招待"},
            "header": ["employee", "expense_type", "claim_amount",
                       "approval_status", "purpose"],
        },
        "text": "招待费报销申请，金额 88000 元，超出部门预算",
    },
    {
        "concept": "urgency",
        "payload": {
            "columns": 5, "rows": 6, "cells": 30,
            "fields": {"employee": "王五", "expense_type": "Travel",
                       "claim_amount": 1200.0, "approval_status": "Draft",
                       "purpose": "紧急出差"},
            "header": ["employee", "expense_type", "claim_amount",
                       "approval_status", "purpose"],
        },
        "text": "紧急出差报销，1200 元，今天必须批",
    },
    {
        "concept": "query",
        "payload": {
            "columns": 3, "rows": 4, "cells": 12,
            "fields": {"doc_no": "EXP-2026-0042", "status": "Approved",
                       "submitter": "赵六"},
            "header": ["doc_no", "status", "submitter"],
        },
        "text": "查询单据 EXP-2026-0042 的审批状态",
    },
]


def build_dataset(
    ds: Any,
    icon_dir: Optional[str] = None,
    extract_images: bool = True,
) -> Any:
    """构建多模态数据集并灌入 samples。

    Args:
        ds: MultimodalDataset 实例
        icon_dir: 图标目录（含 icon-*.png），None 则跳过图像
        extract_images: 是否提真实图像特征（False 则只加文本/表格）

    Returns:
        灌入后的 ds（已调用 add_sample/save）
    """
    ext = MultimodalExtractor()
    added = 0

    # 幂等：跳过已存在来源的样本（防重复灌库——add_sample 本身不去重）
    existing_src = {s.get("_src") for s in ds.samples() if s.get("_src")}

    def _skip(src: str) -> bool:
        return src in existing_src

    # ── 1. 真实图标图像 → visual 特征 ──
    if icon_dir and extract_images and os.path.isdir(icon_dir):
        for fn in os.listdir(icon_dir):
            if not fn.endswith(".png"):
                continue
            base = fn[:-4] if fn.endswith(".png") else fn
            concept = ICON_CONCEPT_MAP.get(base)
            if not concept:
                continue
            src = f"icon:{fn}"
            if _skip(src):
                continue
            try:
                visual = ext.image(os.path.join(icon_dir, fn))
            except Exception:
                continue
            if visual:
                ds.add_sample({
                    "concept": concept,
                    "visual": visual,
                    "text": f"图标：{base}",
                    "_src": src,
                })
                existing_src.add(src)
                added += 1

    # ── 2. 业务话术 → text 样本 ──
    for concept, texts in BIZ_TEXT_CORPUS.items():
        for idx, t in enumerate(texts):
            src = f"biztext:{concept}:{idx}"
            if _skip(src):
                continue
            ds.add_sample({"concept": concept, "text": t, "_src": src})
            existing_src.add(src)
            added += 1

    # ── 3. OA 真实业务表 → payload 结构化样本 ──
    for idx, s in enumerate(OA_TABLE_SAMPLES):
        src = f"oa:{idx}"
        if _skip(src):
            continue
        ds.add_sample({**s, "_src": src})
        existing_src.add(src)
        added += 1

    return {"added": added, "total": len(ds.samples())}


__all__ = [
    "build_dataset",
    "ICON_CONCEPT_MAP",
    "BIZ_TEXT_CORPUS",
    "OA_TABLE_SAMPLES",
]