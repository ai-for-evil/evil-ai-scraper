"""GitHub scraper — searches for repos related to malicious AI tools."""
from backend.scrapers.base import BaseScraper, ScrapedDocument
import base64

# Search queries to find malicious / evil AI repos
GITHUB_QUERIES = [
    "uncensored AI chatbot",
    "jailbreak LLM tool",
    "WormGPT FraudGPT",
    "deepfake generator",
    "AI phishing tool",
    "malicious AI",
    "offensive AI security",
    "AI exploit tool",
    "AI surveillance tool",
    "autonomous weapon AI",
]

GITHUB_API = "https://api.github.com"


class GitHubScraper(BaseScraper):
    """Scrapes GitHub for repos related to malicious/evil AI tools."""

    SOURCE_NAME = "github"
    DOCUMENT_TYPE = "repo"

    async def scrape(self) -> list[ScrapedDocument]:
        results = []
        seen_repos = set()

        for query in GITHUB_QUERIES:
            if len(results) >= self.max_results:
                break
                
            page = 1
            while len(results) < self.max_results:
                await self._rate_limit()
                try:
                    resp = await self.client.get(
                        f"{GITHUB_API}/search/repositories",
                        params={
                            "q": query,
                            "sort": "updated",
                            "order": "desc",
                            "per_page": min(100, self.max_results - len(results)),
                            "page": page,
                        },
                        headers={"Accept": "application/vnd.github.v3+json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    items = data.get("items", [])
                    
                    if not items:
                        break # no more items

                    for repo in items:
                        if len(results) >= self.max_results:
                            break
                            
                        full_name = repo["full_name"]
                        if full_name in seen_repos:
                            continue
                        seen_repos.add(full_name)

                        # Fetch multiple markdown files to go deeper
                        doc_files_text = await self._fetch_repo_docs(full_name)

                        description = repo.get("description") or ""
                        topics = repo.get("topics", [])

                        text_parts = [
                            f"Repository: {full_name}",
                            f"Description: {description}",
                            f"Topics: {', '.join(topics)}",
                            f"Stars: {repo.get('stargazers_count', 0)}",
                            f"Language: {repo.get('language', 'Unknown')}",
                            "",
                            doc_files_text or "(No markdown docs available)"
                        ]

                        results.append(ScrapedDocument(
                            url=repo["html_url"],
                            title=f"{full_name}: {description[:100]}" if description else full_name,
                            text="\n".join(text_parts),
                            source_name=self.SOURCE_NAME,
                            document_type=self.DOCUMENT_TYPE,
                        ))

                    page += 1
                except Exception as e:
                    print(f"[GitHub] Query '{query}' failed: {e}")
                    break

        return results

    async def _fetch_repo_docs(self, full_name: str) -> str:
        """Fetch README and other relevant markdown files to dig deeper."""
        docs_text = []
        try:
            await self._rate_limit()
            # We attempt to fetch the tree to find interesting files
            resp = await self.client.get(
                f"{GITHUB_API}/repos/{full_name}/git/trees/HEAD?recursive=1",
                headers={"Accept": "application/vnd.github.v3+json"}
            )
            
            interesting_files = []
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("tree", []):
                    path = item.get("path", "").lower()
                    if item.get("type") == "blob":
                        # Look for README, SECURITY, docs/*.md, etc.
                        if path.endswith("readme.md") or path == "security.md" or (path.startswith("docs/") and path.endswith(".md")):
                            interesting_files.append(item.get("path"))

            # sort to prioritize README and SECURITY
            interesting_files.sort(key=lambda x: (
                0 if "readme" in x.lower() else (1 if "security" in x.lower() else 2)
            ))
            
            # Fetch up to 3 interesting files to not hit secondary limits too hard
            for path in interesting_files[:3]:
                await self._rate_limit()
                file_resp = await self.client.get(
                    f"{GITHUB_API}/repos/{full_name}/contents/{path}",
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if file_resp.status_code == 200:
                    file_data = file_resp.json()
                    content = file_data.get("content", "")
                    if content:
                        decoded = base64.b64decode(content).decode("utf-8", errors="replace")
                        docs_text.append(f"--- File: {path} ---\n{decoded[:3000]}")
                        
        except Exception as e:
            pass
            
        return "\n\n".join(docs_text)
