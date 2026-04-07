"""HTML→text cleaner with source-specific rules.

Ported from Shiv-Evil-AI-Finder/src/cleaner.py, extended with trafilatura.
"""
from __future__ import annotations

import re
from typing import List

from backend.pipeline.io_utils import normalize_whitespace, stable_hash
from backend.schemas import CleanDocument, FetchedDocument


# Minimum text length to keep a document
_MIN_TEXT_CHARS = 80

# Section markers we strip from cleaned text
_BOILERPLATE_RE = re.compile(
    r"(?:cookie|privacy\s+policy|terms\s+of\s+service|copyright\s+©|"
    r"all\s+rights\s+reserved|subscribe\s+to\s+our\s+newsletter|follow\s+us\s+on)"
    r".*",
    re.IGNORECASE,
)


def clean_html(raw_html: str, *, source_name: str = "") -> str:
    """Extract readable article text from raw HTML.

    Uses trafilatura if available, falls back to simplistic tag stripping.
    """
    text = ""

    # Try trafilatura first
    try:
        import trafilatura

        text = trafilatura.extract(raw_html, include_comments=False) or ""
    except Exception:
        pass

    # Fallback: strip tags
    if not text or len(text) < _MIN_TEXT_CHARS:
        text = _strip_tags(raw_html)

    # Source-specific cleaning
    if source_name and "misp" in source_name.lower():
        text = _clean_misp_page(text)

    # Remove boilerplate tails
    text = _BOILERPLATE_RE.sub("", text).strip()

    return text


def _strip_tags(html: str) -> str:
    """Naive HTML tag stripper."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", " ", text)
    return normalize_whitespace(text)


def _clean_misp_page(text: str) -> str:
    """Remove MISP galaxy navigation noise."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Galaxy:") or stripped.startswith("Cluster:"):
            continue
        if re.match(r"^[A-Z]{2,}\s*$", stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def split_paragraphs(text: str) -> List[str]:
    """Split cleaned text into paragraphs (non-empty lines)."""
    return [
        normalize_whitespace(p)
        for p in re.split(r"\n\s*\n", text)
        if normalize_whitespace(p)
    ]


def clean_fetched_document(doc: FetchedDocument, raw_body: str) -> CleanDocument | None:
    """Clean a fetched document, returning None if too short."""
    cleaned = clean_html(raw_body, source_name=doc.source_name)
    if len(cleaned) < _MIN_TEXT_CHARS:
        return None
    return CleanDocument(
        document_id=doc.document_id,
        source_url=doc.url,
        source_title=doc.title or "",
        source_type=doc.source_type,
        publication_date=doc.publication_date,
        cleaned_text=cleaned,
        paragraphs=split_paragraphs(cleaned),
    )
