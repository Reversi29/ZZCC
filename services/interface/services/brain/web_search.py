"""services/brain/web_search.py — 联网搜索 provider 抽象

支持两种实现（通过环境变量 WEB_SEARCH_PROVIDER 切换）：
  - searxng (默认): 自建开源元搜索引擎 http://127.0.0.1:8888/search?format=json
  - tavily: Tavily SaaS API，https://api.tavily.com/search，需要 TAVILY_API_KEY

Brain AI 通过 tool calling 调用此模块的 search() 函数。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("brain.web_search")


# ═══════════════════════════════════════════════════════════
# 统一搜索结果结构
# ═══════════════════════════════════════════════════════════
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float = 0.0
    source: str = ""
    engine: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResponse:
    ok: bool
    query: str
    results: List[SearchResult]
    provider: str
    elapsed_ms: int = 0
    error: Optional[str] = None
    unresponsive_engines: List[str] = field(default_factory=list)

    def to_text(self, max_results: int = 8) -> str:
        """转成适合喂给 LLM 的纯文本。"""
        if not self.ok:
            return f"[搜索失败] provider={self.provider} error={self.error}"
        lines = [f"# 搜索结果（provider={self.provider}, query={self.query!r}）"]
        for i, r in enumerate(self.results[:max_results], 1):
            lines.append(f"\n## {i}. {r.title}")
            lines.append(f"URL: {r.url}")
            if r.snippet:
                lines.append(f"摘要: {r.snippet}")
            if r.source:
                lines.append(f"来源: {r.source}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# Searxng provider (默认)
# ═══════════════════════════════════════════════════════════
class SearxngProvider:
    """SearXNG 自建元搜索引擎。

    默认端点 http://127.0.0.1:8888（ZZCC docker-compose 内启动）。
    在容器网络内部可直接访问 kt-searxng:8080。
    """
    name = "searxng"

    def __init__(self, base_url: Optional[str] = None, timeout: float = 10.0):
        self.base_url = (
            base_url
            or os.environ.get("SEARXNG_BASE_URL")
            or os.environ.get("WEB_SEARCH_SEARXNG_URL")
            or "http://kt-searxng:8080"  # 容器网络内可达（已加入 interface_default 网络）
        ).rstrip("/")
        self.timeout = timeout

    async def search(self, query: str, max_results: int = 5, **kwargs) -> SearchResponse:
        import time
        start = time.time()
        url = f"{self.base_url}/search"
        params = {
            "q": query,
            "format": "json",
            "pageno": 1,
            # 关键：默认 categories=general 会让 SearXNG 按 default_categories 过滤掉
            # 部分可用引擎（如 naver 在 web 分类）。用 web 分类可保留更多可用引擎。
            "categories": "web",
        }
        if kwargs.get("categories"):
            params["categories"] = kwargs["categories"]
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            elapsed = int((time.time() - start) * 1000)
            results = []
            for r in data.get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=str(r.get("title", "")).strip(),
                    url=str(r.get("url", "")).strip(),
                    snippet=str(r.get("content", "") or r.get("description", "")).strip(),
                    score=float(r.get("score", 0) or 0),
                    source=str(r.get("engine", "") or r.get("category", "")).strip(),
                    engine=self.name,
                    meta={"engines": r.get("engines", [])},
                ))
            unresponsive = [e[0] for e in data.get("unresponsive_engines", []) if isinstance(e, list) and e]
            return SearchResponse(
                ok=True,
                query=query,
                results=results,
                provider=self.name,
                elapsed_ms=elapsed,
                unresponsive_engines=unresponsive,
            )
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            logger.warning("searxng_search_failed url=%s error=%s", url, str(e))
            return SearchResponse(
                ok=False,
                query=query,
                results=[],
                provider=self.name,
                elapsed_ms=elapsed,
                error=str(e),
            )


# ═══════════════════════════════════════════════════════════
# Tavily provider (备选)
# ═══════════════════════════════════════════════════════════
class TavilyProvider:
    """Tavily SaaS 搜索 API。https://tavily.com

    需要 TAVILY_API_KEY 环境变量。免费额度 1000 次/月。
    """
    name = "tavily"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 15.0):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY") or ""
        self.base_url = (base_url or os.environ.get("TAVILY_BASE_URL") or "https://api.tavily.com").rstrip("/")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, max_results: int = 5, **kwargs) -> SearchResponse:
        import time
        start = time.time()
        if not self.api_key:
            return SearchResponse(
                ok=False,
                query=query,
                results=[],
                provider=self.name,
                error="TAVILY_API_KEY 未配置",
            )
        url = f"{self.base_url}/search"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": kwargs.get("depth", "advanced"),
            "max_results": max_results,
            "include_answer": kwargs.get("include_answer", False),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            elapsed = int((time.time() - start) * 1000)
            results = []
            for r in data.get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=str(r.get("title", "")).strip(),
                    url=str(r.get("url", "")).strip(),
                    snippet=str(r.get("content", "")).strip(),
                    score=float(r.get("score", 0) or 0),
                    source="tavily",
                    engine=self.name,
                    meta={"published_date": r.get("published_date")},
                ))
            return SearchResponse(
                ok=True,
                query=query,
                results=results,
                provider=self.name,
                elapsed_ms=elapsed,
                error=None,
                unresponsive_engines=[],
            )
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            logger.warning("tavily_search_failed error=%s", str(e))
            return SearchResponse(
                ok=False,
                query=query,
                results=[],
                provider=self.name,
                elapsed_ms=elapsed,
                error=str(e),
            )


# ═══════════════════════════════════════════════════════════
# 工厂 + 单例
# ═══════════════════════════════════════════════════════════
def _make_provider() -> SearxngProvider | TavilyProvider:
    """根据 WEB_SEARCH_PROVIDER 环境变量选择 provider。

    优先级：
    1. WEB_SEARCH_PROVIDER=tavily 且 TAVILY_API_KEY 存在 → Tavily
    2. 其他情况 → Searxng（默认，本地 Docker）
    """
    p = (os.environ.get("WEB_SEARCH_PROVIDER") or "searxng").lower().strip()
    if p == "tavily":
        t = TavilyProvider()
        if t.available:
            logger.info("web_search_provider=tavily")
            return t
        logger.warning("WEB_SEARCH_PROVIDER=tavily but TAVILY_API_KEY missing, falling back to searxng")
    s = SearxngProvider()
    logger.info("web_search_provider=searxng base_url=%s", s.base_url)
    return s


_provider: Optional[SearxngProvider | TavilyProvider] = None


def get_provider() -> SearxngProvider | TavilyProvider:
    """获取 provider 单例。"""
    global _provider
    if _provider is None:
        _provider = _make_provider()
    return _provider


def reset_provider() -> None:
    """重置 provider（测试用）。"""
    global _provider
    _provider = None


async def search(query: str, max_results: int = 5, **kwargs) -> SearchResponse:
    """联网搜索入口。Brain AI tool calling 调用此函数。"""
    p = get_provider()
    return await p.search(query, max_results=max_results, **kwargs)
