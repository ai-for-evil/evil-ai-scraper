"""Scrape a single URL and extract text content."""
import trafilatura
from bs4 import BeautifulSoup
from backend.scrapers.base import BaseScraper, ScrapedDocument


class URLScraper(BaseScraper):
    """Scrapes a single user-provided URL."""

    SOURCE_NAME = "url"
    DOCUMENT_TYPE = "webpage"

    def __init__(self, url: str, **kwargs):
        super().__init__(**kwargs)
        self.url = url

    def _bs4_deep_extract(self, html: str) -> str:
        """Fallback extraction using BeautifulSoup for pages where trafilatura
        returns very little (JS-heavy landing pages, SPAs, etc.)."""
        soup = BeautifulSoup(html, "html.parser")
        parts: list[str] = []

        # Meta description and OG tags carry high-signal summaries
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or meta.get("property") or "").lower()
            content = (meta.get("content") or "").strip()
            if content and name in (
                "description", "og:description", "og:title",
                "twitter:description", "twitter:title", "keywords",
            ):
                parts.append(content)

        # All headings
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = tag.get_text(separator=" ", strip=True)
            if text:
                parts.append(text)

        # Paragraphs and list items
        for tag in soup.find_all(["p", "li", "span", "div"]):
            text = tag.get_text(separator=" ", strip=True)
            if text and len(text) > 20:
                parts.append(text)

        seen: set[str] = set()
        unique: list[str] = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        return "\n".join(unique)

    async def scrape(self) -> list[ScrapedDocument]:
        resp = await self.client.get(self.url)
        resp.raise_for_status()
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            title = self.url

        # Primary extraction via trafilatura
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if not extracted:
            extracted = trafilatura.extract(html, no_fallback=True) or ""

        # If trafilatura returned very little, supplement with BS4 deep extract
        if len(extracted) < 200:
            bs4_text = self._bs4_deep_extract(html)
            extracted = f"{extracted}\n{bs4_text}".strip() if extracted else bs4_text

        return [ScrapedDocument(
            url=self.url,
            title=title,
            text=extracted or "Could not extract text from this page.",
            source_name=self.SOURCE_NAME,
            document_type=self.DOCUMENT_TYPE,
        )]
