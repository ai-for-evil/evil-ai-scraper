"""NewsAPI scraper — searches for news articles about AI harm/misuse."""
from backend.scrapers.base import BaseScraper, ScrapedDocument
from backend.config import config
import trafilatura

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

                        # Try to fetch full article text
                        full_text = await self._fetch_full_article(url)

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

                        results.append(ScrapedDocument(
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

    async def _fetch_full_article(self, url: str) -> str:
        """Try to fetch and extract the full article text."""
        try:
            resp = await self.client.get(url, timeout=15.0)
            if resp.status_code == 200:
                extracted = trafilatura.extract(resp.text, include_tables=True)
                if extracted:
                    return extracted[:6000]
        except Exception:
            pass
        return ""
