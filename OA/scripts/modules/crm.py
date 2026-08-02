# scripts/modules/crm.py
"""商务自动化：线索打分、客户分组、报价计算"""

from . import ok, fail


def lead_scoring(params: dict) -> dict:
    """
    线索自动打分
    params: {"budget": "50-100万", "industry": "互联网", "position": "CTO", "source": "展会"}
    """
    score = 50  # base

    # 预算
    budget = params.get("budget", "")
    if "万" in budget:
        try:
            amt = float(budget.replace("万", "").replace("+", "").split("-")[-1])
            if amt >= 100:
                score += 20
            elif amt >= 30:
                score += 10
            else:
                score += 5
        except:
            pass

    # 职位
    position = params.get("position", "").lower()
    if any(t in position for t in ["cto", "cio", "vp", "副总裁", "总监"]):
        score += 15
    elif any(t in position for t in ["经理", "主管"]):
        score += 8

    # 来源
    source = params.get("source", "").lower()
    source_score = {"推荐": 15, "展会": 10, "官网": 5, "广告": 3, "陌拜": -5}
    score += source_score.get(source, 0)

    score = max(0, min(100, score))  # clamp

    level = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"
    return ok({"score": score, "level": level})


def quote_calc(params: dict) -> dict:
    """
    快速报价计算
    params: {"cost": 10000, "margin": 0.25, "quantity": 10}
    """
    cost = params.get("cost", 0)
    margin = params.get("margin", 0.2)
    qty = params.get("quantity", 1)
    unit_price = round(cost / (1 - margin), 2)
    total = round(unit_price * qty, 2)
    return ok({
        "unit_price": unit_price,
        "total": total,
        "margin_pct": margin * 100,
        "memo": f"报价 {total}，利润率 {margin*100:.0f}%",
    })
