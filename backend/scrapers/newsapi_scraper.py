"""NewsAPI scraper — searches for news articles about AI harm/misuse."""
import asyncio
import re
from urllib.parse import urlparse

import trafilatura

from backend.scrapers.base import BaseScraper, ScrapedDocument
from backend.config import config

NEWSAPI_URL = "https://newsapi.org/v2/everything"

# Targeted queries for evil AI news
NEWS_QUERIES = [
    '"artificial intelligence" AND (malicious OR harmful OR cyberattack)',
    '"AI" AND (deepfake OR disinformation OR surveillance)',
    '"machine learning" AND (fraud OR exploitation OR weapon)',
    '"AI tool" AND (phishing OR scam OR cybercrime)',
    '"facial recognition" AND (privacy OR mass surveillance)',
    '"autonomous weapon" OR "killer robot" OR "AI targeting"',
]

_HREF_RE = re.compile(
    r"""href\s*=\s*["'](https?://[^"'>\s#]+)["']""",
    re.IGNORECASE,
)

_SKIP_HOST_SUBSTR = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "doubleclick",
    "googleadservices",
    "googlesyndication",
    "youtube.com/watch",
)


class NewsAPIScraper(BaseScraper):
    """Scrapes news articles about AI harm/misuse via NewsAPI."""

    SOURCE_NAME = "newsapi"
    DOCUMENT_TYPE = "news"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = config.NEWS_API_KEY

    async def scrape(self) -> list[ScrapedDocument]:
        if not self.api_key:
            print("[NewsAPI] No API key configured, skipping")
            return []

        results = []
        seen_urls = set()

        for query in NEWS_QUERIES:
            if len(results) >= self.max_results:
                break

            page = 1
            while len(results) < self.max_results:
                await self._rate_limit()
                try:
                    resp = await self.client.get(
                        NEWSAPI_URL,
                        params={
                            "q": query,
                            "apiKey": self.api_key,
                            "language": "en",
                            "sortBy": "publishedAt",
                            "pageSize": min(100, self.max_results - len(results)),
                            "page": page,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    if data.get("status") != "ok":
                        print(f"[NewsAPI] Error: {data.get('message', 'Unknown')}")
                        break

                    articles = data.get("articles", [])
                    if not articles:
                        break

                    for article in articles:
                        if len(results) >= self.max_results:
                            break

                        url = article.get("url", "")
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)

                        title = article.get("title", "Untitled")
                        description = article.get("description", "")
                        content = article.get("content", "")
                        source = article.get("source", {}).get("name", "")
                        published = article.get("publishedAt", "")
                        author = article.get("author", "")

                        full_text, raw_html = await self._fetch_full_article(url)

                        linked_extras = ""
                        if raw_html and config.MAX_OUTBOUND_LINK_FETCHES > 0:
                            linked_extras = await self._fetch_linked_page_excerpts(
                                raw_html, article_url=url
                            )

                        text_parts = [
                            f"Title: {title}",
                            f"Source: {source}",
                            f"Author: {author}",
                            f"Published: {published}",
                            "",
                            f"Description: {description}",
                            "",
                            "Full Article:",
                            full_text or content or description,
                        ]
                        if linked_extras:
                            text_parts.extend(["", "Related / linked sources (extracts):", linked_extras])

                        await self._emit_doc(results, ScrapedDocument(
                            url=url,
                            title=title or "Untitled",
                            text="\n".join(text_parts),
                            source_name=self.SOURCE_NAME,
                            document_type=self.DOCUMENT_TYPE,
                        ))

                    page += 1
                except Exception as e:
                    print(f"[NewsAPI] Query '{query}' failed: {e}")
                    break

        return results

    async def _fetch_full_article(self, url: str) -> tuple[str, str]:
        """Fetch article HTML; return (extracted text, raw html) for link mining."""
        try:
            resp = await self.client.get(url, timeout=20.0)
            if resp.status_code == 200:
                html = resp.text
                extracted = trafilatura.extract(html, include_tables=True)
                cap = min(12000, max(4000, config.LLM_DOCUMENT_MAX_CHARS // 2))
                if extracted:
                    return extracted[:cap], html
                return "", html
        except Exception:
            pass
        return "", ""

    async def _fetch_linked_page_excerpts(self, html: str, article_url: str) -> str:
        """Follow a small number of outbound https links for extra context."""
        max_n = config.MAX_OUTBOUND_LINK_FETCHES
        if max_n <= 0:
            return ""

        base_host = urlparse(article_url).netloc.lower()
        hrefs = _HREF_RE.findall(html or "")
        seen: set[str] = set()
        chunks: list[str] = []
        delay_extra = self.delay * config.SCRAPE_DEPTH_DELAY_MULTIPLIER

        for raw in hrefs:
            if len(chunks) >= max_n:
                break
            u = raw.split("#")[0].strip()
            if not u or u in seen:
                continue
            seen.add(u)
            try:
                host = urlparse(u).netloc.lower()
            except Exception:
                continue
            if host == base_host:
                continue
            if any(s in u.lower() for s in _SKIP_HOST_SUBSTR):
                continue

            await asyncio.sleep(delay_extra)
            try:
                r = await self.client.get(u, timeout=14.0)
                if r.status_code != 200:
                    continue
                ex = trafilatura.extract(r.text)
                if ex and len(ex.strip()) > 120:
                    chunks.append(f"--- Linked page ({u}) ---\n{ex[:2800]}")
            except Exception:
                continue

        return "\n\n".join(chunks)
