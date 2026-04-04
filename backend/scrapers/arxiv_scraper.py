"""arXiv API scraper — searches for AI-related papers on misuse/harm."""
import xml.etree.ElementTree as ET
from backend.scrapers.base import BaseScraper, ScrapedDocument


# Search queries designed to find "evil" AI papers
ARXIV_QUERIES = [
    'all:"artificial intelligence" AND (all:"malicious" OR all:"harmful" OR all:"adversarial attack")',
    'all:"deep learning" AND (all:"deepfake" OR all:"disinformation" OR all:"surveillance")',
    'all:"large language model" AND (all:"jailbreak" OR all:"misuse" OR all:"cybercrime")',
    'all:"AI" AND (all:"autonomous weapon" OR all:"lethal" OR all:"military targeting")',
    'all:"machine learning" AND (all:"exploitation" OR all:"manipulation" OR all:"fraud")',
    'all:"facial recognition" AND (all:"mass surveillance" OR all:"privacy violation")',
    'all:"generative AI" AND (all:"synthetic media" OR all:"impersonation" OR all:"non-consensual")',
]

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


class ArxivScraper(BaseScraper):
    """Scrapes arXiv for AI misuse / evil AI papers."""

    SOURCE_NAME = "arxiv"
    DOCUMENT_TYPE = "paper"

    def __init__(self, max_results_per_query: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results_per_query

    async def scrape(self) -> list[ScrapedDocument]:
        results = []
        seen_ids = set()

        for query in ARXIV_QUERIES:
            await self._rate_limit()
            try:
                resp = await self.client.get(
                    ARXIV_API,
                    params={
                        "search_query": query,
                        "start": 0,
                        "max_results": self.max_results,
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                    },
                )
                resp.raise_for_status()
                docs = self._parse_atom(resp.text, seen_ids)
                results.extend(docs)
            except Exception as e:
                print(f"[arXiv] Query failed: {e}")
                continue

        return results

    def _parse_atom(self, xml_text: str, seen_ids: set) -> list[ScrapedDocument]:
        """Parse arXiv Atom XML response."""
        docs = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return docs

        for entry in root.findall(f"{ATOM_NS}entry"):
            arxiv_id = entry.findtext(f"{ATOM_NS}id", "")
            if arxiv_id in seen_ids:
                continue
            seen_ids.add(arxiv_id)

            title = entry.findtext(f"{ATOM_NS}title", "Untitled").strip().replace("\n", " ")
            summary = entry.findtext(f"{ATOM_NS}summary", "").strip().replace("\n", " ")

            # Get authors
            authors = []
            for author in entry.findall(f"{ATOM_NS}author"):
                name = author.findtext(f"{ATOM_NS}name", "")
                if name:
                    authors.append(name)

            # Build full text from title + summary + authors
            full_text = f"Title: {title}\n\nAuthors: {', '.join(authors)}\n\nAbstract: {summary}"

            # Get link
            link = arxiv_id
            for link_el in entry.findall(f"{ATOM_NS}link"):
                if link_el.get("type") == "text/html":
                    link = link_el.get("href", arxiv_id)
                    break

            docs.append(ScrapedDocument(
                url=link,
                title=title,
                text=full_text,
                source_name=self.SOURCE_NAME,
                document_type=self.DOCUMENT_TYPE,
            ))

        return docs
