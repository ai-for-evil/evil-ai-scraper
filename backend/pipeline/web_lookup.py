"""Web search: optional URL enrichment + multi-query snippets for LLM refinement."""
from __future__ import annotations

import asyncio
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from backend.config import config

# Skip obvious non-product URLs when picking a search hit
_BLOCKED_NETLOC_SUBSTR = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "pinterest.com",
    "linkedin.com",
)


def _url_ok(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https") or not p.netloc:
        return False
    host = p.netloc.lower()
    for b in _BLOCKED_NETLOC_SUBSTR:
        if b in host:
            return False
    return True


def _search_available() -> bool:
    p = (config.WEB_SEARCH_PROVIDER or "none").strip().lower()
    if p == "brave" and config.BRAVE_SEARCH_API_KEY:
        return True
    if p == "serpapi" and config.SERPAPI_KEY:
        return True
    return False


def web_search_configured() -> bool:
    """True when Brave or SerpAPI can be used for snippet search / URL lookup."""
    return _search_available()


async def search_tool_url_web(ai_system_name: str) -> Optional[str]:
    """
    Return a candidate official/product URL from Brave or SerpAPI, or None.
    Requires WEB_SEARCH_PROVIDER and corresponding API key in config.
    """
    provider = (config.WEB_SEARCH_PROVIDER or "none").strip().lower()
    name = (ai_system_name or "").strip()
    if provider in ("", "none") or len(name) < 2:
        return None
    if "unnamed system" in name.lower():
        return None

    q = f'"{name}" AI tool OR official website OR github'
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        if provider == "brave" and config.BRAVE_SEARCH_API_KEY:
            return await _search_brave(client, q)
        if provider == "serpapi" and config.SERPAPI_KEY:
            return await _search_serpapi(client, q)
    return None


async def _search_brave(client: httpx.AsyncClient, q: str) -> Optional[str]:
    try:
        r = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": q, "count": 8},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": config.BRAVE_SEARCH_API_KEY,
            },
        )
        r.raise_for_status()
        data = r.json()
        for item in data.get("web", {}).get("results", []) or []:
            u = item.get("url") or ""
            if _url_ok(u):
                return u
    except Exception as e:
        print(f"[web_lookup] Brave search failed: {e}")
    return None


async def _search_serpapi(client: httpx.AsyncClient, q: str) -> Optional[str]:
    try:
        r = await client.get(
            "https://serpapi.com/search.json",
            params={
                "q": q,
                "api_key": config.SERPAPI_KEY,
                "engine": "google",
                "num": 8,
            },
        )
        r.raise_for_status()
        data = r.json()
        for item in data.get("organic_results", []) or []:
            u = item.get("link") or ""
            if _url_ok(u):
                return u
    except Exception as e:
        print(f"[web_lookup] SerpAPI search failed: {e}")
    return None


async def _brave_snippet_results(client: httpx.AsyncClient, q: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        r = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": q, "count": 6},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": config.BRAVE_SEARCH_API_KEY,
            },
        )
        r.raise_for_status()
        data = r.json()
        for item in data.get("web", {}).get("results", []) or []:
            u = item.get("url") or ""
            if not _url_ok(u):
                continue
            out.append({
                "url": u,
                "title": (item.get("title") or "")[:300],
                "snippet": (item.get("description") or item.get("snippet") or "")[:1200],
            })
    except Exception as e:
        print(f"[web_lookup] Brave snippet search failed for {q[:40]}: {e}")
    return out


async def _serpapi_snippet_results(client: httpx.AsyncClient, q: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        r = await client.get(
            "https://serpapi.com/search.json",
            params={
                "q": q,
                "api_key": config.SERPAPI_KEY,
                "engine": "google",
                "num": 6,
            },
        )
        r.raise_for_status()
        data = r.json()
        for item in data.get("organic_results", []) or []:
            u = item.get("link") or ""
            if not _url_ok(u):
                continue
            out.append({
                "url": u,
                "title": (item.get("title") or "")[:300],
                "snippet": (item.get("snippet") or "")[:1200],
            })
    except Exception as e:
        print(f"[web_lookup] SerpAPI snippet search failed for {q[:40]}: {e}")
    return out


async def fetch_snippets_for_queries(queries: list[str]) -> str:
    """
    Run up to LLM_WEB_SEARCH_MAX_QUERIES web searches in parallel; return a text block for the LLM.
    """
    if not queries or not _search_available():
        return ""
    cap = max(1, config.LLM_WEB_SEARCH_MAX_QUERIES)
    qs = [q.strip() for q in queries if q and q.strip()][:cap]
    if not qs:
        return ""

    provider = (config.WEB_SEARCH_PROVIDER or "none").strip().lower()
    async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
        if provider == "brave" and config.BRAVE_SEARCH_API_KEY:
            tasks = [_brave_snippet_results(client, q) for q in qs]
        elif provider == "serpapi" and config.SERPAPI_KEY:
            tasks = [_serpapi_snippet_results(client, q) for q in qs]
        else:
            return ""

        all_batches = await asyncio.gather(*tasks)

    lines: list[str] = []
    for q, batch in zip(qs, all_batches):
        lines.append(f"### Query: {q}")
        if not batch:
            lines.append("(no results)\n")
            continue
        for i, row in enumerate(batch, 1):
            lines.append(f"{i}. {row['title']}")
            lines.append(f"   URL: {row['url']}")
            lines.append(f"   Snippet: {row['snippet']}\n")
    return "\n".join(lines)


def _is_placeholder_tool_url(url: str, document_url: str) -> bool:
    u = (url or "").strip()
    if not u or u.upper() in ("N/A", "NONE", "UNKNOWN"):
        return True
    doc = (document_url or "").strip()
    if doc and u.rstrip("/") == doc.rstrip("/"):
        return True
    return False


async def maybe_enrich_tool_url_from_web(cls: dict, *, document_url: str = "") -> None:
    """
    If tool_website_url is missing or only repeats the article URL, try web search.
    Mutates cls in place; appends a note to evidence_summary when a URL is inferred.
    """
    provider = (config.WEB_SEARCH_PROVIDER or "none").strip().lower()
    if provider in ("", "none"):
        return

    name = (cls.get("ai_system_name") or "").strip()
    if not name or "N/A" == name.upper():
        return

    tw = (cls.get("tool_website_url") or "").strip()
    if not _is_placeholder_tool_url(tw, document_url):
        return

    found = await search_tool_url_web(name)
    if not found:
        return

    cls["tool_website_url"] = found
    note = " [Product/tool URL inferred via web search — verify manually.]"
    summary = (cls.get("evidence_summary") or "").strip()
    if note.strip(" []") not in summary:
        cls["evidence_summary"] = (summary + note).strip()
