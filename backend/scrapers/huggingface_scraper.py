"""HuggingFace Hub API scraper — searches for models related to harmful AI."""
from backend.scrapers.base import BaseScraper, ScrapedDocument

HF_API = "https://huggingface.co/api"

# Search terms to find potentially harmful models
HF_QUERIES = [
    "uncensored",
    "jailbreak",
    "deepfake",
    "nsfw",
    "malware",
    "offensive",
    "no-filter",
    "unethical",
]


class HuggingFaceScraper(BaseScraper):
    """Scrapes HuggingFace Hub for models related to harmful AI."""

    SOURCE_NAME = "huggingface"
    DOCUMENT_TYPE = "model"

    def __init__(self, max_results_per_query: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results_per_query

    async def scrape(self) -> list[ScrapedDocument]:
        results = []
        seen_models = set()

        for query in HF_QUERIES:
            await self._rate_limit()
            try:
                resp = await self.client.get(
                    f"{HF_API}/models",
                    params={
                        "search": query,
                        "limit": self.max_results,
                        "sort": "downloads",
                        "direction": -1,
                    },
                )
                resp.raise_for_status()
                models = resp.json()

                for model in models:
                    model_id = model.get("modelId", model.get("id", ""))
                    if model_id in seen_models:
                        continue
                    seen_models.add(model_id)

                    # Fetch model card (README)
                    model_card = await self._fetch_model_card(model_id)

                    tags = model.get("tags", [])
                    pipeline_tag = model.get("pipeline_tag", "")
                    downloads = model.get("downloads", 0)
                    likes = model.get("likes", 0)

                    text_parts = [
                        f"Model: {model_id}",
                        f"Pipeline: {pipeline_tag}",
                        f"Tags: {', '.join(tags)}",
                        f"Downloads: {downloads}",
                        f"Likes: {likes}",
                        "",
                        "Model Card:",
                        model_card or "(No model card available)",
                    ]

                    results.append(ScrapedDocument(
                        url=f"https://huggingface.co/{model_id}",
                        title=model_id,
                        text="\n".join(text_parts),
                        source_name=self.SOURCE_NAME,
                        document_type="model",
                    ))

            except Exception as e:
                print(f"[HuggingFace] Query '{query}' failed: {e}")
                continue

        return results

    async def _fetch_model_card(self, model_id: str) -> str:
        """Fetch the model card README for a model."""
        try:
            await self._rate_limit()
            resp = await self.client.get(
                f"https://huggingface.co/{model_id}/raw/main/README.md",
            )
            if resp.status_code == 200:
                return resp.text[:5000]
        except Exception:
            pass
        return ""
