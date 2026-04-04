"""Base scraper class and shared types."""
import asyncio
import io
import httpx
from dataclasses import dataclass, field
from typing import Optional
from pypdf import PdfReader


@dataclass
class ScrapedDocument:
    """A single scraped document."""
    url: str
    title: str
    text: str
    source_name: str
    document_type: str = "unknown"  # paper, news, repo, patent, product, regulation


class BaseScraper:
    """Base class for all scrapers."""

    SOURCE_NAME: str = "generic"
    DOCUMENT_TYPE: str = "unknown"

    def __init__(self, user_agent: str = "AIForEvilResearchBot/1.0", delay: float = 1.0, max_results: int = 60, **kwargs):
        self.user_agent = user_agent
        self.delay = delay
        self.max_results = max_results
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()

    async def _rate_limit(self):
        """Respect rate limiting between requests."""
        await asyncio.sleep(self.delay)

    async def scrape(self) -> list[ScrapedDocument]:
        """Override in subclasses. Returns list of scraped documents."""
        raise NotImplementedError

    async def _download_and_parse_pdf(self, url: str, max_pages: int = 50) -> str:
        """Helper to download a PDF and extract text using pypdf."""
        try:
            await self._rate_limit()
            resp = await self.client.get(url, timeout=30.0)
            if resp.status_code == 200:
                with io.BytesIO(resp.content) as pdf_file:
                    reader = PdfReader(pdf_file)
                    text_parts = []
                    for i, page in enumerate(reader.pages):
                        if i >= max_pages:
                            break
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                    return "\n\n".join(text_parts)
        except Exception as e:
            print(f"[BaseScraper] Failed to download/parse PDF from {url}: {e}")
        return ""
