"""Connect manifest-based crawl + clean stages to app-level document processing."""
from __future__ import annotations

import json
from pathlib import Path

from backend.scrapers.base import ScrapedDocument

_MANIFEST_PRESETS: dict[str, str | None] = {
    "high_yield": "high_yield_sources.json",
    "approved": "approved_sources.example.json",
    "continuous": "continuous_sources.json",
    "autonomous": "autonomous_sources.json",
    "demo": None,
}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def resolve_manifest_path(preset_or_path: str) -> Path:
    """Map a short preset name or a project-relative path to a manifest JSON file."""
    root = project_root()
    seeds = root / "data" / "research_seeds"
    key = (preset_or_path or "high_yield").strip()
    if key in _MANIFEST_PRESETS:
        if key == "demo":
            return _write_demo_manifest(seeds)
        name = _MANIFEST_PRESETS[key]
        assert name is not None
        return seeds / name
    path = Path(key)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _write_demo_manifest(seeds_dir: Path) -> Path:
    """Offline demo using local HTML fixtures under data/research_seeds/demo_articles/."""
    articles = seeds_dir / "demo_articles"
    triples = [
        ("Demo FraudGPT Article", "fraudgpt_article.html", "news"),
        ("Demo FraudGPT Follow Up", "fraudgpt_followup.html", "threat_report"),
        ("Demo Clearview Article", "clearview_article.html", "news"),
    ]
    sources = []
    for name, fname, stype in triples:
        fp = articles / fname
        if not fp.exists():
            continue
        sources.append(
            {
                "name": name,
                "kind": "url",
                "url": fp.as_uri(),
                "source_type": stype,
                "allowed_domains": [],
            }
        )
    out = seeds_dir / "_demo_manifest.local.json"
    out.write_text(json.dumps({"sources": sources}, indent=2), encoding="utf-8")
    return out


def clean_dicts_to_scraped(items: list[dict], *, limit: int | None = None) -> list[ScrapedDocument]:
    """Turn clean_documents.jsonl rows into ScrapedDocument for the main classifier."""
    out: list[ScrapedDocument] = []
    for item in items:
        text = (item.get("cleaned_text") or "").strip()
        if len(text) < 50:
            continue
        url = item.get("source_url") or ""
        title = (item.get("source_title") or url or "Untitled").strip()
        doc_type = (item.get("source_type") or "news").strip() or "news"
        out.append(
            ScrapedDocument(
                url=url,
                title=title,
                text=text,
                source_name="manifest",
                document_type=doc_type,
            )
        )
        if limit is not None and len(out) >= limit:
            break
    return out


def run_manifest_documents_sync(
    manifest_path: Path,
    *,
    fresh: bool = False,
    max_documents: int | None = None,
    ensure_taxonomy: bool = True,
) -> list[ScrapedDocument]:
    """Run seed load (if needed), crawl, and clean; return documents for LLM classification."""
    from backend.research_pipeline.config import load_settings
    from backend.research_pipeline.io_utils import read_jsonl
    from backend.research_pipeline.pipeline import Pipeline

    settings = load_settings()
    pipeline = Pipeline(settings)
    if ensure_taxonomy:
        tax = settings.processed_dir / "taxonomy.json"
        if not tax.exists():
            pipeline.seed_load()
    pipeline.crawl(manifest_path, incremental=not fresh)
    pipeline.clean()
    cleaned = read_jsonl(settings.processed_dir / "clean_documents.jsonl")
    return clean_dicts_to_scraped(cleaned, limit=max_documents)
