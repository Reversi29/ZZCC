# scripts/modules/__init__.py
"""独立 Python 自动化脚本 — 可直接运行或由 AI Agent 调用"""

# 统一返回格式
def ok(data):
    return {"status": "ok", "data": data}

def fail(msg):
    return {"status": "error", "message": str(msg)}
