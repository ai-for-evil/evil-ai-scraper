"""Pipeline processor — orchestrates scrape → classify → dedupe → store.

Unified pipeline merging the original processor with Shiv's evidence extraction,
entity deduplication, and review queue generation.
"""
import json
import datetime
import traceback
from backend.database import get_db
from backend.models import Run, Document, Classification, Entity, ReviewItemDB
from backend.config import config
from backend.scrapers.base import ScrapedDocument
from backend.scrapers.url_scraper import URLScraper
from backend.scrapers.arxiv_scraper import ArxivScraper
from backend.scrapers.github_scraper import GitHubScraper
from backend.scrapers.huggingface_scraper import HuggingFaceScraper
from backend.scrapers.newsapi_scraper import NewsAPIScraper
from backend.scrapers.euaiact_scraper import EUAIActScraper
from backend.scrapers.patents_scraper import PatentsScraper
from backend.scrapers.manifest_scraper import ManifestScraper
from backend.pipeline.classifier import (
    keyword_filter,
    name_match_filter,
    classify_with_ollama,
    apply_confidence_gate,
    coerce_matched_field,
)
from backend.pipeline.web_lookup import maybe_enrich_tool_url_from_web

# Map source names to scraper classes
SCRAPER_MAP = {
    "arxiv": ArxivScraper,
    "github": GitHubScraper,
    "huggingface": HuggingFaceScraper,
    "newsapi": NewsAPIScraper,
    "eu_ai_act": EUAIActScraper,
    "patents": PatentsScraper,
}


def _manifest_preset_from_source_key(source_name: str) -> str | None:
    if source_name.startswith("manifest:"):
        return source_name.split(":", 1)[1].strip() or "high_yield"
    if source_name == "manifest":
        return "high_yield"
    return None


def _split_max_results_across_sources(max_results: int, num_sources: int) -> list[int]:
    """Split total document budget across sources; remainder goes to the first sources."""
    if num_sources <= 0:
        return []
    total = max(1, max_results)
    base, rem = divmod(total, num_sources)
    return [base + (1 if i < rem else 0) for i in range(num_sources)]


async def run_url_scrape(run_id: int, url: str):
    """Run a scrape on a single URL."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return
        run.status = "running"
        db.commit()

    def is_cancelled():
        with get_db() as db:
            r = db.query(Run).filter(Run.id == run_id).first()
            return r and r.status == "cancelled"

    async def on_doc_found(doc):
        await _process_documents(run_id, [doc])
        _finalize_run(run_id, is_final=False)

    try:
        if is_cancelled():
            return
        # Scrape
        async with URLScraper(
            url=url, 
            user_agent=config.SCRAPE_USER_AGENT,
            on_doc_found=on_doc_found,
            is_cancelled=is_cancelled
        ) as scraper:
            await scraper.scrape()

        if not is_cancelled():
            # Run post-processing (deduplication, review queue)
            _run_post_processing(run_id)
            _finalize_run(run_id, is_final=True)

    except Exception as e:
        if "RunCancelled" in str(e) or is_cancelled():
            return
        _fail_run(run_id, str(e))
        traceback.print_exc()


async def run_source_scrape(
    run_id: int,
    sources: list[str],
    max_results: int = 60,
    *,
    manifest_fresh: bool = False,
):
    """Run a scrape on selected sources."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return
        run.status = "running"
        db.commit()

    def is_cancelled():
        with get_db() as db:
            r = db.query(Run).filter(Run.id == run_id).first()
            return r and r.status == "cancelled"

    async def on_doc_found(doc):
        await _process_documents(run_id, [doc])
        _finalize_run(run_id, is_final=False)

    try:
        valid = [
            s for s in sources
            if s in SCRAPER_MAP or _manifest_preset_from_source_key(s) is not None
        ]
        quotas = _split_max_results_across_sources(max_results, len(valid))

        for source_name, per_source_cap in zip(valid, quotas):
            if is_cancelled():
                return
            manifest_preset = _manifest_preset_from_source_key(source_name)
            if manifest_preset is not None:
                print(
                    f"[Processor] Manifest scrape preset={manifest_preset} "
                    f"(quota {per_source_cap} of total {max(1, max_results)})..."
                )
                try:
                    async with ManifestScraper(
                        user_agent=config.SCRAPE_USER_AGENT,
                        delay=config.SCRAPE_DELAY_SECONDS,
                        max_results=per_source_cap,
                        on_doc_found=on_doc_found,
                        is_cancelled=is_cancelled,
                        manifest_preset=manifest_preset,
                        fresh=manifest_fresh,
                    ) as scraper:
                        await scraper.scrape()
                except Exception as e:
                    if "RunCancelled" in str(e) or is_cancelled():
                        return
                    print(f"[Processor] manifest ({manifest_preset}) failed: {e}")
                continue

            scraper_class = SCRAPER_MAP.get(source_name)
            if not scraper_class:
                print(f"[Processor] Unknown source: {source_name}")
                continue

            print(f"[Processor] Scraping {source_name} (quota {per_source_cap} of total {max(1, max_results)})...")
            try:
                async with scraper_class(
                    user_agent=config.SCRAPE_USER_AGENT,
                    delay=config.SCRAPE_DELAY_SECONDS,
                    max_results=per_source_cap,
                    on_doc_found=on_doc_found,
                    is_cancelled=is_cancelled
                ) as scraper:
                    await scraper.scrape()
            except Exception as e:
                if "RunCancelled" in str(e) or is_cancelled():
                    return
                print(f"[Processor] {source_name} failed: {e}")
                continue

        if not is_cancelled():
            # Run post-processing (deduplication, review queue)
            _run_post_processing(run_id)
            _finalize_run(run_id, is_final=True)

    except Exception as e:
        if "RunCancelled" in str(e) or is_cancelled():
            return
        _fail_run(run_id, str(e))
        traceback.print_exc()


async def _process_documents(run_id: int, scraped_docs: list[ScrapedDocument]):
    """Process scraped documents: store, filter, classify."""
    for doc in scraped_docs:
        with get_db() as db:
            # Store document
            db_doc = Document(
                run_id=run_id,
                url=doc.url,
                title=doc.title,
                source_name=doc.source_name,
                document_type=doc.document_type,
                raw_text=doc.text,
                cleaned_text=doc.text,  # Already cleaned by trafilatura
                scraped_at=datetime.datetime.utcnow(),
            )

            # Keyword filter — include URL and title in the text for matching
            enriched_text = f"URL: {doc.url}\nTitle: {doc.title}\n\n{doc.text}"
            keyword_matches = keyword_filter(enriched_text)

            # Known evil AI name detection (guaranteed match for high-profile systems)
            name_matches = name_match_filter(doc.text, url=doc.url, title=doc.title)
            for cat_id, match_data in name_matches.items():
                if cat_id not in keyword_matches:
                    keyword_matches[cat_id] = match_data
                else:
                    existing_hits = set(keyword_matches[cat_id]["hits"])
                    for hit in match_data["hits"]:
                        if hit not in existing_hits:
                            keyword_matches[cat_id]["hits"].append(hit)
                    keyword_matches[cat_id]["count"] = len(keyword_matches[cat_id]["hits"])

            db_doc.keyword_matched = len(keyword_matches) > 0
            db_doc.keyword_categories = json.dumps(list(keyword_matches.keys()))

            db.add(db_doc)
            db.commit()
            doc_id = db_doc.id

        # LLM Classification (for keyword-matched docs, or all if LLM enabled)
        if keyword_matches or config.USE_LLM:
            try:
                result = await classify_with_ollama(
                    text=doc.text,
                    title=doc.title,
                    url=doc.url,
                    keyword_matches=keyword_matches,
                )

                if result and result.get("classifications"):
                    for cls in result["classifications"]:
                        if not coerce_matched_field(cls.get("matched")):
                            continue
                        try:
                            await maybe_enrich_tool_url_from_web(
                                cls, document_url=doc.url or ""
                            )
                        except Exception as e:
                            print(f"[Processor] Web URL enrichment failed: {e}")

                    with get_db() as db:
                        for cls in result["classifications"]:
                            if not coerce_matched_field(cls.get("matched")):
                                continue

                            cat_id = cls.get("category_id", "")
                            confidence = cls.get("confidence", 0.0)
                            status = apply_confidence_gate(confidence, cat_id)

                            # Extract signal debug data from hybrid pre-scorer
                            signal_debug = cls.pop("_signal_debug", None)
                            relevance_score = cls.pop("_relevance_score", None)
                            relevance_reasons = cls.pop("_relevance_reasons", None)
                            ambiguous_codes_data = None
                            if signal_debug:
                                ambiguous_codes_data = json.dumps(
                                    signal_debug.get("ambiguous_codes", [])
                                )

                            classification = Classification(
                                document_id=doc_id,
                                category_id=cat_id,
                                category_name=cls.get("category_name", ""),
                                matched=True,
                                confidence=confidence,
                                status=status,
                                reasoning=cls.get("reasoning", ""),
                                criteria_scores=json.dumps(cls.get("criteria_scores", {})),
                                ai_system_name=cls.get("ai_system_name"),
                                developer_org=cls.get("developer_org"),
                                abuse_description=cls.get("abuse_description"),
                                evidence_quotes=json.dumps(cls.get("evidence_quotes", [])),
                                classified_at=datetime.datetime.utcnow(),
                                guidelines_version=config.GUIDELINES_VERSION,
                                is_gray_area=cat_id in {"2B", "5B"},
                                criminal_or_controversial=cls.get("criminal_or_controversial"),
                                descriptive_category=cls.get("descriptive_category"),
                                tool_website_url=cls.get("tool_website_url"),
                                public_tagline=cls.get("public_tagline"),
                                stated_use_case=cls.get("stated_use_case"),
                                target_victim=cls.get("target_victim"),
                                primary_output=cls.get("primary_output"),
                                harm_category=cls.get("harm_category"),
                                gate_1=cls.get("gate_1"),
                                gate_2=cls.get("gate_2"),
                                gate_3=cls.get("gate_3"),
                                exclusion_1=cls.get("exclusion_1"),
                                exclusion_2=cls.get("exclusion_2"),
                                exclusion_3=cls.get("exclusion_3"),
                                include_in_repo=cls.get("include_in_repo"),
                                evidence_summary=cls.get("evidence_summary"),
                                # New: Shiv signal data
                                relevance_score=relevance_score,
                                signal_debug=(
                                    json.dumps(signal_debug)
                                    if signal_debug else None
                                ),
                                ambiguous_codes=ambiguous_codes_data,
                            )
                            db.add(classification)
                        db.commit()

            except Exception as e:
                print(f"[Processor] Classification failed for '{doc.title}': {e}")


def _run_post_processing(run_id: int):
    """Run entity deduplication and review queue generation after all docs processed."""
    try:
        from backend.pipeline.deduper import EntityDeduper
        from backend.pipeline.review_queue import build_review_queue
        from backend.schemas import CandidateCase as CandidateCaseSchema
        from backend.pipeline.io_utils import stable_hash

        with get_db() as db:
            classifications = (
                db.query(Classification)
                .join(Document)
                .filter(Document.run_id == run_id, Classification.matched == True)
                .all()
            )
            if not classifications:
                return

            # Build CandidateCase records from classifications
            candidates = []
            for c in classifications:
                doc = db.query(Document).filter(Document.id == c.document_id).first()
                if not doc:
                    continue
                candidates.append(CandidateCaseSchema(
                    case_id=stable_hash(str(c.id), c.ai_system_name or "", c.category_id),
                    entity_name=c.ai_system_name or "",
                    aliases=[],
                    source_url=doc.url or "",
                    source_title=doc.title or "",
                    publication_date="",
                    source_type=doc.document_type or "news",
                    evidence_text=c.evidence_summary or c.reasoning or "",
                    suspected_function=c.category_name or "",
                    final_code=c.category_id or "",
                    subgroup_name=c.category_name or "",
                    confidence=c.confidence or 0.0,
                    rationale=c.reasoning or "",
                    review_status=c.status or "pending",
                    relevance_score=c.relevance_score or 0.0,
                    document_id=str(doc.id),
                    chunk_id="",
                ))

            if not candidates:
                return

            # Deduplicate
            deduper = EntityDeduper()
            entities, dedup_reviews = deduper.dedupe(candidates)

            # Build review queue
            review_items = build_review_queue(
                entities, candidates,
                review_confidence=config.REVIEW_CONFIDENCE_THRESHOLD,
                high_confidence=config.HIGH_CONFIDENCE_THRESHOLD,
            )
            all_reviews = dedup_reviews + review_items

            # Store entities
            for entity in entities:
                db_entity = Entity(
                    run_id=run_id,
                    entity_id=entity.entity_id,
                    entity_name=entity.entity_name,
                    aliases=json.dumps(entity.aliases),
                    canonical_code=entity.canonical_code,
                    subgroup_name=entity.subgroup_name,
                    confidence=entity.confidence,
                    rationale=entity.rationale,
                    source_urls=json.dumps(entity.source_urls),
                    source_titles=json.dumps(entity.source_titles),
                    evidence_texts=json.dumps(entity.evidence_texts[:5]),
                    suspected_functions=json.dumps(entity.suspected_functions),
                    review_status=entity.review_status,
                    merge_confidence=entity.merge_confidence,
                    seed_overlap=entity.seed_overlap,
                )
                db.add(db_entity)

            # Store review items
            for review in all_reviews:
                db_review = ReviewItemDB(
                    run_id=run_id,
                    review_id=review.review_id,
                    reason=review.reason,
                    severity=review.severity,
                    entity_name=review.entity_name,
                    source_url=review.source_url,
                    case_id=review.case_id,
                    details=review.details,
                    suggested_code=review.suggested_code,
                )
                db.add(db_review)

            db.commit()
            print(
                f"[Processor] Post-processing: {len(entities)} entities, "
                f"{len(all_reviews)} review items for run #{run_id}"
            )

    except Exception as e:
        print(f"[Processor] Post-processing failed for run #{run_id}: {e}")
        traceback.print_exc()


def _finalize_run(run_id: int, is_final: bool = True):
    """Update run with final metrics. Call occasionally during run to push stats."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return

        total_docs = db.query(Document).filter(Document.run_id == run_id).count()
        classifications = (
            db.query(Classification)
            .join(Document)
            .filter(Document.run_id == run_id)
            .all()
        )

        # Count unique AI systems (by name), falling back to document_id for unnamed ones
        evil_identifiers = set()
        for c in classifications:
            if not c.matched:
                continue
            if c.ai_system_name:
                evil_identifiers.add(c.ai_system_name.strip().lower())
            else:
                evil_identifiers.add(f"_doc_{c.document_id}")
        evil_found = len(evil_identifiers)
        confirmed = sum(1 for c in classifications if c.status == "confirmed")
        contested = sum(1 for c in classifications if c.status == "contested")
        rejected = sum(1 for c in classifications if c.status == "rejected")
        confidences = [c.confidence for c in classifications if c.matched]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        if is_final and run.status == "running":
            run.status = "completed"
            run.finished_at = datetime.datetime.utcnow()
            
        run.total_documents = total_docs
        run.evil_found = evil_found
        run.confirmed_count = confirmed
        run.contested_count = contested
        run.rejected_count = rejected
        run.avg_confidence = round(avg_conf, 3)
        db.commit()


def _fail_run(run_id: int, error: str):
    """Mark a run as failed."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if run:
            run.status = "failed"
            run.finished_at = datetime.datetime.utcnow()
            run.error_message = error[:2000]
            db.commit()
