# ============================================
# ai/main.py — AI Agent 主入口
# ============================================
# 作为独立服务运行：轮询 ERPNext 中待处理的 AI 任务
# 也可被 Frappe App 通过 HTTP API 直接调用

import os
import sys
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.llm_client import LLMClient
from services.erpnext_client import ERPNextClient


class OAAgent:
    """ZZCC OA AI Agent 主控制器"""

    def __init__(self):
        self.llm = LLMClient()
        self.erp = ERPNextClient()
        self.modules = {}  # lazy load

    def _get_module(self, name: str):
        if name not in self.modules:
            try:
                self.modules[name] = importlib.import_module(f"modules.{name}")
            except ImportError:
                return None
        return self.modules[name]

    # ── 面向业务模块的入口 ──────────────

    def ai_consult(self, module: str, context: dict) -> dict:
        """
        通用 AI 咨询入口
        - module: procurement / finance / quality / compliance / project / crm / hr / contract
        - context: 单据数据上下文字典
        返回: {"advice": "...", "risk_flags": [...], "suggestions": [...]}
        """
        mod = self._get_module(module)
        if mod and hasattr(mod, "consult"):
            return mod.consult(context, self.llm)
        return {"advice": f"{module} 模块尚未注册 AI 咨询逻辑", "risk_flags": []}

    def execute_script(self, module: str, action: str, params: dict) -> dict:
        """
        执行自动化脚本
        - module: procurement / finance / ...
        - action: compare_price / auto_classify / risk_check / ...
        """
        try:
            script_mod = importlib.import_module(f"../scripts.modules.{module}")
            handler = getattr(script_mod, action, None)
            if handler:
                return handler(params)
            return {"error": f"未找到 action: {action}"}
        except Exception as e:
            return {"error": str(e)}

    # ── 运行模式 ────────────────────────

    def run_loop(self):
        """轮询模式（对接到 ERPNext 后台队列）"""
        import time
        while True:
            try:
                pending = self.erp.query_pending_ai_tasks()
                for task in pending:
                    result = self.ai_consult(task["module"], task["context"])
                    self.erp.submit_ai_result(task["id"], result)
            except Exception as e:
                print(f"[AI Agent] loop error: {e}", file=sys.stderr)
            time.sleep(30)


if __name__ == "__main__":
    agent = OAAgent()
    print("[AI Agent] 启动成功")
    agent.run_loop()
