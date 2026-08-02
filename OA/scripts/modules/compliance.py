# scripts/modules/compliance.py
"""合规自动化：合同关键词检查、知识产权状态查询"""

from . import ok, fail


def contract_scan(params: dict) -> dict:
    """
    合同条款扫描
    params: {"title": "...", "content": "合同正文..."}
    """
    content = params.get("content", "").lower()

    findings = []
    # 检查高风险条款
    checks = {
        "违约金过高": ["违约金.*[5-9]0%", "违约金.*[1-9][0-9]0%"],
        "自动续期": ["自动续期", "自动续约", "到期自动"],
        "排他性条款": ["独家", "排他", "不得与其他"],
        "保密义务无限期": ["永久.*保密", "无限期.*保密"],
        "管辖地不利": ["仲裁机构.*[^（(]*北京"],
    }

    import re
    for issue, patterns in checks.items():
        for p in patterns:
            if re.search(p, content):
                findings.append({"issue": issue, "severity": "high"})
                break

    return ok({
        "scanned": params.get("title", "N/A"),
        "findings": findings,
        "risk_level": "high" if findings else "low",
    })


def patent_check(params: dict) -> dict:
    """知识产权状态检查（占位：对接天眼查/企查查 API）"""
    return ok({
        "patent": params.get("name"),
        "status": "待查询",
        "note": "需要配置外部 API 密钥后自动查询",
    })
