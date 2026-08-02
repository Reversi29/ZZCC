# ============================================
# ai/services/erpnext_client.py
# ERPNext REST API 客户端
# ============================================
import os
import json
import httpx


class ERPNextClient:
    """对接 Frappe REST API"""

    def __init__(self):
        self.base_url = os.getenv("FRAPPE_URL", "http://backend:8000")
        self.api_key = os.getenv("FRAPPE_API_KEY", "")
        self.api_secret = os.getenv("FRAPPE_API_SECRET", "")
        self._httpx = httpx.Client(base_url=self.base_url, timeout=30)

    def _headers(self):
        return {
            "Authorization": f"token {self.api_key}:{self.api_secret}",
            "Content-Type": "application/json",
        }

    # ── 通用 CRUD ────────────────────────

    def get_doc(self, doctype: str, name: str) -> dict:
        resp = self._httpx.get(
            f"/api/resource/{doctype}/{name}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()["data"]

    def create_doc(self, doctype: str, data: dict) -> dict:
        resp = self._httpx.post(
            f"/api/resource/{doctype}",
            json={"data": data},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()["data"]

    def update_doc(self, doctype: str, name: str, data: dict) -> dict:
        resp = self._httpx.put(
            f"/api/resource/{doctype}/{name}",
            json={"data": data},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()["data"]

    # ── AI 任务查询 ──────────────────────

    def query_pending_ai_tasks(self) -> list:
        """查询需要 AI 处理的记录"""
        # 通过自定义 DocType AI Task 轮询
        resp = self._httpx.get(
            "/api/resource/AI Task",
            params={
                "filters": json.dumps([["status", "=", "Pending"]]),
                "limit_page_length": 10,
            },
            headers=self._headers(),
        )
        if resp.status_code == 200:
            return resp.json().get("data", [])
        return []

    def submit_ai_result(self, task_id: str, result: dict):
        """写回 AI 结果"""
        self.update_doc("AI Task", task_id, {
            "result": json.dumps(result, ensure_ascii=False),
            "status": "Completed",
        })
