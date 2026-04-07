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

# Broader queries used only when primary queries yield no documents
ARXIV_FALLBACK_QUERIES = [
    'all:"large language model" AND all:misuse',
    'all:"machine learning" AND all:adversarial',
    'all:"AI" AND (all:harmful OR all:malicious)',
    'all:deepfake OR all:disinformation',
    'cat:cs.CR AND all:AI',
]

ARXIV_API = "https://export.arxiv.org/api/query"
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
            await self._collect_query_results(query, seen_ids, results)

        if len(results) == 0:
            print("[arXiv] Primary queries returned no documents; trying fallback queries.")
            for query in ARXIV_FALLBACK_QUERIES:
                if len(results) >= self.max_results:
                    break
                await self._collect_query_results(query, seen_ids, results, fallback=True)

        if len(results) == 0:
            print("[arXiv] Warning: scrape returned 0 documents. Check network, query syntax, or arXiv availability.")

        return results

    async def _collect_query_results(
        self,
        query: str,
        seen_ids: set,
        results: list,
        *,
        fallback: bool = False,
    ) -> None:
        tag = "[fallback] " if fallback else ""
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
                print(f"[arXiv] {tag}GET status={resp.status_code} start={start} max={batch_size} q={query[:72]}...")
                resp.raise_for_status()
                xml_text = resp.text
                total_hits = self._parse_total_results(xml_text)
                entry_count = self._count_atom_entries(xml_text)

                batch_docs = self._parse_atom(xml_text, seen_ids)
                if not batch_docs:
                    if entry_count == 0:
                        print(f"[arXiv] {tag}No atom entries (totalResults={total_hits}); end query.")
                        break
                    print(
                        f"[arXiv] {tag}0 new papers ({entry_count} entries were duplicates); "
                        f"start {start} -> {start + batch_size}"
                    )
                    start += batch_size
                    if total_hits is not None and start >= total_hits:
                        break
                    if start > 10000:
                        print(f"[arXiv] {tag}Pagination cap reached.")
                        break
                    continue

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

                    await self._emit_doc(results, ScrapedDocument(
                        url=raw_doc["url"],
                        title=raw_doc["title"],
                        text=full_text,
                        source_name=self.SOURCE_NAME,
                        document_type=self.DOCUMENT_TYPE,
                    ))

                start += len(batch_docs)

            except Exception as e:
                print(f"[arXiv] {tag}Query failed: {e}")
                break

    def _parse_total_results(self, xml_text: str):
        """Best-effort opensearch:totalResults from feed."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None
        for el in root.iter():
            if el.tag.endswith("totalResults") and el.text and el.text.strip().isdigit():
                return int(el.text.strip())
        return None

    def _count_atom_entries(self, xml_text: str) -> int:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return 0
        return len(root.findall(f"{ATOM_NS}entry"))

    def _parse_atom(self, xml_text: str, seen_ids: set) -> list[dict]:
        """Parse arXiv Atom XML response."""
        docs = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"[arXiv] XML parse error: {e}")
            return docs

        for entry in root.findall(f"{ATOM_NS}entry"):
            arxiv_id = entry.findtext(f"{ATOM_NS}id", "")
            if arxiv_id in seen_ids:
                continue
            seen_ids.add(arxiv_id)

            title = entry.findtext(f"{ATOM_NS}title", "Untitled").strip().replace("\n", " ")
            summary = entry.findtext(f"{ATOM_NS}summary", "").strip().replace("\n", " ")

            authors = []
            for author in entry.findall(f"{ATOM_NS}author"):
                name = author.findtext(f"{ATOM_NS}name", "")
                if name:
                    authors.append(name)

            full_text = f"Title: {title}\n\nAuthors: {', '.join(authors)}\n\nAbstract: {summary}"

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
