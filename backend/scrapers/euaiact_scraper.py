"""EU AI Act scraper — fetches regulatory content about AI regulation."""
import trafilatura
from backend.scrapers.base import BaseScraper, ScrapedDocument

# Key EU AI Act and regulatory pages
EU_AI_ACT_URLS = [
    {
        "url": "https://artificialintelligenceact.eu/high-level-summary/",
        "title": "EU AI Act - High Level Summary",
    },
    {
        "url": "https://artificialintelligenceact.eu/the-act/",
        "title": "EU AI Act - The Act",
    },
    {
        "url": "https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/",
        "title": "EU AI Act - Compliance Checker",
    },
    {
        "url": "https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai",
        "title": "EU Digital Strategy - AI Regulatory Framework",
    },
    {
        "url": "https://www.europarl.europa.eu/topics/en/article/20230601STO93804/eu-ai-act-first-regulation-on-artificial-intelligence",
        "title": "European Parliament - EU AI Act Summary",
    },
    {
        "url": "https://artificialintelligenceact.eu/annex/3/",
        "title": "EU AI Act - Annex III High-Risk AI Systems",
    },
    {
        "url": "https://artificialintelligenceact.eu/article/5/",
        "title": "EU AI Act - Article 5 Prohibited AI Practices",
    },
    {
        "url": "https://artificialintelligenceact.eu/article/6/",
        "title": "EU AI Act - Article 6 Classification Rules for High-Risk AI",
    },
]


class EUAIActScraper(BaseScraper):
    """Scrapes EU AI Act regulatory content."""

    SOURCE_NAME = "eu_ai_act"
    DOCUMENT_TYPE = "regulation"

    async def scrape(self) -> list[ScrapedDocument]:
        results = []

        for page in EU_AI_ACT_URLS:
            await self._rate_limit()
            try:
                resp = await self.client.get(page["url"])
                if resp.status_code != 200:
                    print(f"[EU AI Act] Failed to fetch {page['url']}: {resp.status_code}")
                    continue

                extracted = trafilatura.extract(
                    resp.text,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False,
                )

                if not extracted or len(extracted.strip()) < 100:
                    continue

                results.append(ScrapedDocument(
                    url=page["url"],
                    title=page["title"],
                    text=extracted[:8000],
                    source_name=self.SOURCE_NAME,
                    document_type=self.DOCUMENT_TYPE,
                ))

            except Exception as e:
                print(f"[EU AI Act] Error fetching {page['url']}: {e}")
                continue

        return results
