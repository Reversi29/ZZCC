# scripts/modules/quality.py
"""质检自动化：数据统计、异常检测、良率分析"""

from . import ok, fail


def defect_analysis(params: dict) -> dict:
    """
    不良品分析
    params: {"defects": [{"type": "划痕", "count": 5}, ...], "total": 200}
    """
    defects = params.get("defects", [])
    total = params.get("total", 1)
    # Pareto 分析
    sorted_defects = sorted(defects, key=lambda x: x["count"], reverse=True)
    cumulative = 0
    total_count = sum(d["count"] for d in sorted_defects)
    for d in sorted_defects:
        cumulative += d["count"]
        d["cumulative_pct"] = round(cumulative / total_count * 100, 1)

    return ok({
        "total_inspected": total,
        "pass_rate": round((total - total_count) / total * 100, 1),
        "pareto": sorted_defects,
        "top_issues": [d["type"] for d in sorted_defects[:3]],
    })
