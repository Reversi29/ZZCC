# scripts/modules/procurement.py
"""采购自动化：比价分析、价格监控、供应商评估"""

from . import ok, fail


def compare_price(params: dict) -> dict:
    """
    多供应商比价
    params: {
        "item_name": "服务器",
        "spec": "32C 64G",
        "quotations": [
            {"supplier": "A", "price": 15000, "lead_time": 7, "rating": 4.5},
            {"supplier": "B", "price": 14200, "lead_time": 14, "rating": 4.8},
        ]
    }
    """
    try:
        quotes = params.get("quotations", [])
        if not quotes:
            return fail("无报价数据")

        # 加权评分（价格50% + 交期20% + 评分30%）
        for q in quotes:
            score = 0
            min_price = min(qq["price"] for qq in quotes)
            min_lead = min(qq["lead_time"] for qq in quotes)
            score += 50 * (min_price / q["price"])
            score += 20 * (min_lead / q["lead_time"])
            score += 30 * (q.get("rating", 3) / 5)
            q["composite_score"] = round(score, 1)

        ranked = sorted(quotes, key=lambda x: x["composite_score"], reverse=True)
        return ok({
            "ranked": ranked,
            "recommendation": ranked[0],
            "savings": ranked[0]["price"] - min(qq["price"] for qq in quotes),
        })
    except Exception as e:
        return fail(str(e))


def price_monitor(params: dict) -> dict:
    """
    价格异常检测
    params: {"item": "CPU", "current_price": 3200, "historical_avg": 2800}
    """
    try:
        delta = params.get("current_price", 0) - params.get("historical_avg", 0)
        delta_pct = delta / params.get("historical_avg", 1) * 100
        is_abnormal = abs(delta_pct) > 15
        return ok({
            "item": params.get("item"),
            "delta_pct": round(delta_pct, 1),
            "is_abnormal": is_abnormal,
            "alert": f"价格波动 {delta_pct:+.1f}%" if is_abnormal else "正常",
        })
    except Exception as e:
        return fail(str(e))
