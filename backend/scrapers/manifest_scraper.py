"""Approved-source manifest crawl (RSS, sitemaps, news search, direct URLs) → cleaned articles."""
import asyncio

from backend.scrapers.base import BaseScraper, ScrapedDocument


class ManifestScraper(BaseScraper):
    """Runs the research pipeline crawl+clean stages and emits ScrapedDocument records."""

    SOURCE_NAME = "manifest"
    DOCUMENT_TYPE = "news"

    def __init__(
        self,
        manifest_preset: str = "high_yield",
        fresh: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.manifest_preset = manifest_preset
        self.fresh = fresh

    async def scrape(self) -> list[ScrapedDocument]:
        from backend.research_pipeline.adapter import resolve_manifest_path, run_manifest_documents_sync

        manifest_path = resolve_manifest_path(self.manifest_preset)
        results: list[ScrapedDocument] = []

        docs = await asyncio.to_thread(
            run_manifest_documents_sync,
            manifest_path,
            fresh=self.fresh,
            max_documents=self.max_results,
            ensure_taxonomy=True,
        )

        for doc in docs:
            await self._emit_doc(results, doc)
        return results
