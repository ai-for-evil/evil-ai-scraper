"""Pipeline dataclass schemas — intermediate objects used between pipeline stages.

Ported from Shiv-Evil-AI-Finder/src/schemas.py with additions for the merged system.
These are NOT the SQLAlchemy DB models (those are in models.py).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional


class SchemaMixin:
    """All pipeline dataclasses gain .to_dict() for serialization."""

    def to_dict(self) -> Dict[str, Any]:
        return _convert(asdict(self))


def _convert(value: Any) -> Any:
    if is_dataclass(value):
        return _convert(asdict(value))
    if isinstance(value, list):
        return [_convert(item) for item in value]
    if isinstance(value, dict):
        return {key: _convert(item) for key, item in value.items()}
    return value


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

@dataclass
class TaxonomyNode(SchemaMixin):
    """One node of the 15-subcategory taxonomy, parsed from the PDF."""
    code: str
    subgroup_name: str
    major_group: str
    definition: str
    criteria: List[str] = field(default_factory=list)
    gray_area: bool = False
    confidence_notes: str = ""


@dataclass
class SeedExample(SchemaMixin):
    """One column from the classification_guideline.csv seed sheet."""
    entity_name: str
    final_code: str
    subgroup_name: str
    broad_category: str = ""
    source_url: str = ""
    developer: str = ""
    tagline: str = ""
    stated_use_case: str = ""
    target_victim: str = ""
    primary_output: str = ""
    harm_category: str = ""
    evidence_summary: str = ""
    evidence_links: List[str] = field(default_factory=list)
    reviewer_notes: str = ""
    reviewer_name: str = ""
    criminality_frame: str = ""
    gates: Dict[str, bool] = field(default_factory=dict)
    exclusions: Dict[str, bool] = field(default_factory=dict)
    include_in_repo: Optional[bool] = None
    aliases: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Source ingestion
# ---------------------------------------------------------------------------

@dataclass
class SourceDefinition(SchemaMixin):
    """An approved source from a manifest JSON file."""
    name: str
    kind: str  # url | rss | sitemap | article_list | bing_news_search | google_news_search
    url: str
    source_type: str = "news"
    allowed_domains: List[str] = field(default_factory=list)
    article_url_patterns: List[str] = field(default_factory=list)
    credibility: str = "high"
    queries: List[str] = field(default_factory=list)
    limit_per_query: int = 25


@dataclass
class FetchedDocument(SchemaMixin):
    """Raw fetched document before cleaning."""
    document_id: str
    url: str
    source_name: str
    source_type: str
    domain: str
    status: str
    fetched_at: str
    title: str = ""
    publication_date: str = ""
    raw_path: str = ""
    text_path: str = ""
    http_status: Optional[int] = None
    error: str = ""


@dataclass
class CleanDocument(SchemaMixin):
    """Document after HTML→text cleaning."""
    document_id: str
    source_url: str
    source_title: str
    source_type: str
    publication_date: str
    cleaned_text: str
    paragraphs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentChunk(SchemaMixin):
    """A chunk of a document for per-chunk classification."""
    chunk_id: str
    document_id: str
    source_url: str
    source_title: str
    source_type: str
    publication_date: str
    text: str
    start_offset: int
    end_offset: int
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@dataclass
class ClassificationSignal(SchemaMixin):
    """One scoring signal (rules, prototype, model, hard_boosts)."""
    name: str
    code_scores: Dict[str, float]
    reasons: List[str] = field(default_factory=list)
    weight: float = 1.0


@dataclass
class ClassificationResult(SchemaMixin):
    """Output of the HybridClassifier (Shiv-style, before LLM deep-dive)."""
    final_code: str
    subgroup_name: str
    confidence: float
    rationale: str
    evidence_snippets: List[str] = field(default_factory=list)
    signal_scores: Dict[str, float] = field(default_factory=dict)
    debug_signals: List[ClassificationSignal] = field(default_factory=list)
    ambiguous_codes: List[str] = field(default_factory=list)
    gray_area: bool = False


# ---------------------------------------------------------------------------
# Evidence extraction & entity management
# ---------------------------------------------------------------------------

@dataclass
class CandidateCase(SchemaMixin):
    """A candidate evil AI case extracted from a document chunk."""
    case_id: str
    entity_name: str
    aliases: List[str]
    source_url: str
    source_title: str
    publication_date: str
    source_type: str
    evidence_text: str
    suspected_function: str
    final_code: str
    subgroup_name: str
    confidence: float
    rationale: str
    review_status: str
    relevance_score: float
    relevance_reasons: List[str] = field(default_factory=list)
    classification_debug: Dict[str, Any] = field(default_factory=dict)
    document_id: str = ""
    chunk_id: str = ""


@dataclass
class EntityRecord(SchemaMixin):
    """A deduplicated entity — the final output."""
    entity_id: str
    entity_name: str
    aliases: List[str]
    canonical_code: str
    subgroup_name: str
    confidence: float
    rationale: str
    source_urls: List[str] = field(default_factory=list)
    source_titles: List[str] = field(default_factory=list)
    publication_dates: List[str] = field(default_factory=list)
    source_types: List[str] = field(default_factory=list)
    evidence_texts: List[str] = field(default_factory=list)
    suspected_functions: List[str] = field(default_factory=list)
    related_case_ids: List[str] = field(default_factory=list)
    review_status: str = "pending_review"
    merge_confidence: float = 1.0
    seed_overlap: bool = False


@dataclass
class ReviewItem(SchemaMixin):
    """An item flagged for human review."""
    review_id: str
    reason: str
    severity: str
    entity_name: str
    source_url: str
    case_id: str
    details: str
    suggested_code: str = ""


@dataclass
class CrawlLogEntry(SchemaMixin):
    """One row in the crawl log."""
    url: str
    source_name: str
    status: str
    fetched_at: str
    http_status: Optional[int] = None
    raw_path: str = ""
    error: str = ""
