"""Base scraper class and shared types."""
import asyncio
import httpx
from dataclasses import dataclass, field
from typing import Optional


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

    def __init__(self, user_agent: str = "AIForEvilResearchBot/1.0", delay: float = 1.0):
        self.user_agent = user_agent
        self.delay = delay
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
