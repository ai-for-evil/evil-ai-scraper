import re
import trafilatura
from backend.scrapers.base import BaseScraper, ScrapedDocument
import urllib.parse

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
        seen_urls = set()
        
        pdf_link_pattern = re.compile(r'href=["\']([^"\']+\.pdf)["\']', re.IGNORECASE)

        for page in EU_AI_ACT_URLS:
            if len(results) >= self.max_results:
                break
                
            await self._rate_limit()
            try:
                if page["url"] in seen_urls:
                    continue
                seen_urls.add(page["url"])

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

                pdf_text = ""
                # Search for pdf links to dig deeper
                pdf_matches = pdf_link_pattern.findall(resp.text)
                for pdf_href in dict.fromkeys(pdf_matches):
                    pdf_url = urllib.parse.urljoin(page["url"], pdf_href)
                    if pdf_url not in seen_urls:
                        seen_urls.add(pdf_url)
                        print(f"[EU AI Act] Downloading linked PDF {pdf_url}...")
                        found_pdf_text = await self._download_and_parse_pdf(pdf_url, max_pages=100) # EU AI Act PDFs can be long
                        if found_pdf_text:
                            pdf_text += f"\n\n--- Linked PDF ({pdf_url}) ---\n{found_pdf_text}"
                
                full_content = ""
                if extracted and len(extracted.strip()) >= 100:
                    full_content += extracted[:15000]
                if pdf_text:
                    full_content += pdf_text
                    
                if not full_content:
                    continue

                results.append(ScrapedDocument(
                    url=page["url"],
                    title=page["title"],
                    text=full_content,
                    source_name=self.SOURCE_NAME,
                    document_type=self.DOCUMENT_TYPE,
                ))

            except Exception as e:
                print(f"[EU AI Act] Error fetching {page['url']}: {e}")
                continue

        return results
