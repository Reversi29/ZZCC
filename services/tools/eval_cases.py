"""SNN 权威 eval 用例——生产决策回归基准。

用例来源：原定义于容器 /tmp/eval_prod_full.py（容器重启即丢失，已恢复并入库）。
从 LCM 历史恢复，为 12 场景硬约束基准。

每个用例：(signal_type, payload, urgency, expected_decision)

判据（2026-11-13 实测，权威口径）：
- 干净拓扑（create_default + 结构化隐藏层）= 12/12
- 生产漂移网络 = 10/12（#5、#11 失败）
- 备份基线 20261028 = 6/12（旧版，不可作基线）

漂移会让 eval 掉分，故本模块与 snn_drift_guard.py 联动：
护栏检测到漂移即自动恢复，恢复后本 eval 应回到 12/12。
"""

from typing import List, Tuple

# 权威 12 用例
EVAL_CASES: List[Tuple[str, dict, int, str]] = [
    ("expense", {"amount": 88000, "category": "equipment", "supplier_risk": "high"}, 90, "escalate"),
    ("expense", {"amount": 500, "category": "office", "invoice_status": "complete"}, 50, "auto_approve"),
    ("expense", {"amount": 35000, "category": "travel", "supplier_risk": "medium"}, 70, "escalate"),
    ("expense", {"amount": 800, "category": "meals", "invoice_status": "complete"}, 40, "auto_approve"),
    ("user_request", {"question": "hello"}, 30, "chat"),
    ("user_request", {"question": "cancel order #12345"}, 60, "escalate"),
    ("approval_pending", {"amount": 15000, "category": "services", "urgency": "high"}, 80, "escalate"),
    ("approval_pending", {"amount": 500, "category": "consumables", "urgency": "low"}, 30, "auto_approve"),
    ("threshold_breach", {"risk_level": "critical", "vendor": "new_co"}, 95, "escalate"),
    ("threshold_breach", {"risk_level": "low", "vendor": "established"}, 20, "auto_approve"),
    ("approval_pending", {"amount": 300, "status": "pending"}, 60, "flag"),
    ("approval_pending", {"amount": 80000, "status": "pending", "urgency": "high"}, 90, "escalate"),
]


def run(region):
    """对一个 SNNRegion 跑 12 用例，返回 (通过数, 失败列表)。

    region 需实现 async reason(signal, context, db)。
    """
    import asyncio
    from models.brain import NeuralSignal

    async def _run():
        ok, fails = 0, []
        for i, (t, pl, urg, exp) in enumerate(EVAL_CASES, 1):
            sig = NeuralSignal(id=f"eval{i}", type=t, payload=pl,
                               source="eval", urgency=urg)
            r = await region.reason(sig, {}, None)
            d = r.result.decision if r.result else None
            if d == exp:
                ok += 1
            else:
                fails.append({"index": i, "type": t, "urgency": urg,
                             "expected": exp, "got": d})
        return ok, fails

    return asyncio.run(_run())
