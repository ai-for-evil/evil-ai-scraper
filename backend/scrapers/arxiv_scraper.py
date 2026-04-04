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

    async def scrape(self) -> list[ScrapedDocument]:
        results = []
        seen_ids = set()

        for query in ARXIV_QUERIES:
            if len(results) >= self.max_results:
                break
            
            start = 0
            while len(results) < self.max_results:
                batch_size = min(50, self.max_results - len(results))
                await self._rate_limit()
                try:
                    resp = await self.client.get(
                        ARXIV_API,
                        params={
                            "search_query": query,
                            "start": start,
                            "max_results": batch_size,
                            "sortBy": "submittedDate",
                            "sortOrder": "descending",
                        },
                    )
                    resp.raise_for_status()
                    
                    batch_docs = self._parse_atom(resp.text, seen_ids)
                    if not batch_docs:
                        break # No more results for this query
                        
                    for raw_doc in batch_docs:
                        if len(results) >= self.max_results:
                            break
                        
                        pdf_url = raw_doc.get("pdf_url")
                        pdf_text = ""
                        if pdf_url:
                            print(f"[arXiv] Downloading PDF for {raw_doc['title'][:30]}...")
                            pdf_text = await self._download_and_parse_pdf(pdf_url)
                        
                        full_text = raw_doc["text"]
                        if pdf_text:
                            full_text += f"\n\n--- FULL PAPER TEXT ---\n{pdf_text}"

                        results.append(ScrapedDocument(
                            url=raw_doc["url"],
                            title=raw_doc["title"],
                            text=full_text,
                            source_name=self.SOURCE_NAME,
                            document_type=self.DOCUMENT_TYPE,
                        ))
                    
                    start += len(batch_docs)
                    
                except Exception as e:
                    print(f"[arXiv] Query failed: {e}")
                    break

        return results

    def _parse_atom(self, xml_text: str, seen_ids: set) -> list[dict]:
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

            # Build core text
            full_text = f"Title: {title}\n\nAuthors: {', '.join(authors)}\n\nAbstract: {summary}"

            # Get link and pdf link
            link = arxiv_id
            pdf_url = None
            for link_el in entry.findall(f"{ATOM_NS}link"):
                if link_el.get("type") == "text/html":
                    link = link_el.get("href", arxiv_id)
                elif link_el.get("title") == "pdf":
                    pdf_url = link_el.get("href")
            
            if not pdf_url and link:
                pdf_url = link.replace("abs", "pdf") + ".pdf"

            docs.append({
                "url": link,
                "title": title,
                "text": full_text,
                "pdf_url": pdf_url,
            })

        return docs
