import re
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

    async def scrape(self) -> list[ScrapedDocument]:
        results = []
        seen_urls = set()

        # Regex to find patent links from the basic search page
        patent_link_pattern = re.compile(r'href="(/patent/[A-Z0-9]+/[a-zA-Z]+)(?:\?[^"]*)?"')

        for query in PATENT_QUERIES:
            if len(results) >= self.max_results:
                break
                
            page = 0
            while len(results) < self.max_results:
                await self._rate_limit()
                try:
                    search_url = f"{PATENT_SEARCH_URL}/?q={query.replace(' ', '+')}&oq={query.replace(' ', '+')}&page={page}"
                    resp = await self.client.get(search_url)

                    if resp.status_code != 200:
                        break

                    # find all patent links
                    matches = patent_link_pattern.findall(resp.text)
                    unique_paths = list(dict.fromkeys(matches)) # preserve order, remove duplicates
                    
                    if not unique_paths:
                        # Fallback to general page text if no specific links found
                        extracted = trafilatura.extract(resp.text, include_comments=False)
                        if extracted and len(extracted) > 100:
                            if search_url not in seen_urls:
                                seen_urls.add(search_url)
                                await self._emit_doc(results, ScrapedDocument(
                                    url=search_url,
                                    title=f"Patent Search: {query}",
                                    text=extracted[:8000],
                                    source_name=self.SOURCE_NAME,
                                    document_type=self.DOCUMENT_TYPE,
                                ))
                        break # no deep pages, proceed to next query
                    
                    for path in unique_paths:
                        if len(results) >= self.max_results:
                            break
                            
                        url = f"{PATENT_SEARCH_URL}{path}"
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        
                        await self._rate_limit()
                        doc_resp = await self.client.get(url)
                        if doc_resp.status_code == 200:
                            extracted = trafilatura.extract(
                                doc_resp.text,
                                include_comments=False,
                                include_tables=True,
                            )
                            if extracted and len(extracted.strip()) > 100:
                                await self._emit_doc(results, ScrapedDocument(
                                    url=url,
                                    title=f"Patent {path.split('/')[-2]}",
                                    text=f"Search Query: {query}\n\nPatent Details:\n{extracted[:8000]}",
                                    source_name=self.SOURCE_NAME,
                                    document_type=self.DOCUMENT_TYPE,
                                ))
                    
                    page += 1

                except Exception as e:
                    print(f"[Patents] Query '{query}' failed: {e}")
                    break

        return results
