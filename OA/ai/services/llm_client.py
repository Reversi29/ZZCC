# ============================================
# ai/services/llm_client.py
# AI 大模型客户端 — 支持 Ollama / OpenAI
# ============================================
import os
import json
from typing import Optional

import httpx


class LLMClient:
    """统一 LLM 调用接口"""

    def __init__(self):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self._httpx = httpx.Client(timeout=120)

    # ── 通用调用 ────────────────────────

    def chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> str:
        """流式/非流式对话"""
        if self.openai_key:
            return self._chat_openai(system_prompt, user_prompt, model or "gpt-4o-mini")
        return self._chat_ollama(system_prompt, user_prompt, model or "qwen2.5:7b")

    def chat_json(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> dict:
        """返回结构化 JSON"""
        text = self.chat(system_prompt, user_prompt + "\n\n请严格输出 JSON，不要额外说明。", model)
        return self._extract_json(text)

    # ── Ollama ───────────────────────────

    def _chat_ollama(self, system: str, user: str, model: str) -> str:
        resp = self._httpx.post(
            f"{self.ollama_host}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.3},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    # ── OpenAI ───────────────────────────

    def _chat_openai(self, system: str, user: str, model: str) -> str:
        resp = self._httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.openai_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # ── 工具 ─────────────────────────────

    @staticmethod
    def _extract_json(text: str) -> dict:
        # 尝试直接解析；失败则摘取 {} 包裹段
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise
