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

    def __init__(self, max_results_per_query: int = 5, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results_per_query

    async def scrape(self) -> list[ScrapedDocument]:
        results = []
        seen_repos = set()

        for query in GITHUB_QUERIES:
            await self._rate_limit()
            try:
                resp = await self.client.get(
                    f"{GITHUB_API}/search/repositories",
                    params={
                        "q": query,
                        "sort": "updated",
                        "order": "desc",
                        "per_page": self.max_results,
                    },
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                resp.raise_for_status()
                data = resp.json()

                for repo in data.get("items", []):
                    full_name = repo["full_name"]
                    if full_name in seen_repos:
                        continue
                    seen_repos.add(full_name)

                    # Try to fetch README
                    readme_text = await self._fetch_readme(full_name)

                    description = repo.get("description") or ""
                    topics = repo.get("topics", [])

                    text_parts = [
                        f"Repository: {full_name}",
                        f"Description: {description}",
                        f"Topics: {', '.join(topics)}",
                        f"Stars: {repo.get('stargazers_count', 0)}",
                        f"Language: {repo.get('language', 'Unknown')}",
                        "",
                        "README:",
                        readme_text or "(No README available)",
                    ]

                    results.append(ScrapedDocument(
                        url=repo["html_url"],
                        title=f"{full_name}: {description[:100]}" if description else full_name,
                        text="\n".join(text_parts),
                        source_name=self.SOURCE_NAME,
                        document_type=self.DOCUMENT_TYPE,
                    ))

            except Exception as e:
                print(f"[GitHub] Query '{query}' failed: {e}")
                continue

        return results

    async def _fetch_readme(self, full_name: str) -> str:
        """Fetch the README content of a repo."""
        try:
            await self._rate_limit()
            resp = await self.client.get(
                f"{GITHUB_API}/repos/{full_name}/readme",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("content", "")
                if content:
                    decoded = base64.b64decode(content).decode("utf-8", errors="replace")
                    # Truncate very long READMEs
                    return decoded[:5000]
        except Exception:
            pass
        return ""
