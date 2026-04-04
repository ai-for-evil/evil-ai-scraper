"""Google Patents scraper — searches for AI-related patents with harmful potential."""
import trafilatura
from backend.scrapers.base import BaseScraper, ScrapedDocument

PATENT_SEARCH_URL = "https://patents.google.com"

# Search queries for AI patents with potentially harmful applications
PATENT_QUERIES = [
    "autonomous weapon targeting system artificial intelligence",
    "deepfake generation synthetic media AI",
    "facial recognition mass surveillance biometric",
    "AI cybersecurity exploit vulnerability scanner",
    "social credit scoring behavioral monitoring AI",
    "predictive policing AI crime prediction",
    "AI disinformation detection generation",
    "automated phishing artificial intelligence",
]


class PatentsScraper(BaseScraper):
    """Scrapes Google Patents for AI-related patent claims with potential for harm."""

    SOURCE_NAME = "patents"
    DOCUMENT_TYPE = "patent"

    def __init__(self, max_results_per_query: int = 5, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results_per_query

    async def scrape(self) -> list[ScrapedDocument]:
        results = []
        seen_urls = set()

        for query in PATENT_QUERIES:
            await self._rate_limit()
            try:
                search_url = f"{PATENT_SEARCH_URL}/?q={query.replace(' ', '+')}&oq={query.replace(' ', '+')}"
                resp = await self.client.get(search_url)

                if resp.status_code != 200:
                    print(f"[Patents] Failed to search: {resp.status_code}")
                    continue

                # Extract any text content from the search results page
                extracted = trafilatura.extract(
                    resp.text,
                    include_comments=False,
                    include_tables=True,
                )

                if extracted and len(extracted.strip()) > 100:
                    url = str(resp.url)
                    if url not in seen_urls:
                        seen_urls.add(url)
                        results.append(ScrapedDocument(
                            url=url,
                            title=f"Patent Search: {query}",
                            text=f"Search Query: {query}\n\nResults:\n{extracted[:6000]}",
                            source_name=self.SOURCE_NAME,
                            document_type=self.DOCUMENT_TYPE,
                        ))

            except Exception as e:
                print(f"[Patents] Query '{query}' failed: {e}")
                continue

        return results
