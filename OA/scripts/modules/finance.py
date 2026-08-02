# scripts/modules/finance.py
"""财务自动化：发票分类、费用对账、预算跟踪"""

from . import ok, fail


def classify_invoice(params: dict) -> dict:
    """
    发票自动分类
    params: {"supplier": "腾讯云", "amount": 12500, "description": "云服务器3个月"}
    """
    desc = params.get("description", "").lower()
    supplier = params.get("supplier", "").lower()

    # 关键词规则分类
    rules = [
        ("云计算|服务器|域名|带宽|OSS|CDN", "IT基础设施"),
        ("招聘|猎头|社保|公积金|薪资", "人力成本"),
        ("差旅|机票|酒店|打车|高铁|餐饮", "差旅费用"),
        ("广告|推广|投放|SEO|SEM|营销", "市场营销"),
        ("律师|法律|专利|商标|著作权", "法务费用"),
        ("采购|硬件|设备|物料|耗材", "采购成本"),
        ("房租|物业|水电|办公用品|快递", "行政运营"),
    ]

    import re
    for pattern, category in rules:
        if re.search(pattern, desc):
            return ok({"category": category, "confidence": "auto"})

    # 特殊供应商匹配
    supplier_map = {
        "腾讯云": "IT基础设施",
        "阿里云": "IT基础设施",
        "华为云": "IT基础设施",
        "aws": "IT基础设施",
    }
    for key, cat in supplier_map.items():
        if key in supplier:
            return ok({"category": cat, "confidence": "auto"})

    return ok({"category": "待分类", "confidence": "low"})


def reconcile(params: dict) -> dict:
    """
    简单对账
    params: {
        "records": [{"date": "2024-01-01", "amount": 1000, "matched": False}, ...]
    }
    """
    records = params.get("records", [])
    unmatched = [r for r in records if not r["matched"]]
    return ok({
        "total": len(records),
        "matched": len(records) - len(unmatched),
        "unmatched": unmatched,
    })
