"""Pipeline processor — orchestrates scrape → classify → store."""
import json
import datetime
import traceback
from backend.database import get_db
from backend.models import Run, Document, Classification
from backend.config import config
from backend.scrapers.base import ScrapedDocument
from backend.scrapers.url_scraper import URLScraper
from backend.scrapers.arxiv_scraper import ArxivScraper
from backend.scrapers.github_scraper import GitHubScraper
from backend.scrapers.huggingface_scraper import HuggingFaceScraper
from backend.scrapers.newsapi_scraper import NewsAPIScraper
from backend.scrapers.euaiact_scraper import EUAIActScraper
from backend.scrapers.patents_scraper import PatentsScraper
from backend.pipeline.classifier import keyword_filter, name_match_filter, classify_with_ollama, apply_confidence_gate

# Map source names to scraper classes
SCRAPER_MAP = {
    "arxiv": ArxivScraper,
    "github": GitHubScraper,
    "huggingface": HuggingFaceScraper,
    "newsapi": NewsAPIScraper,
    "eu_ai_act": EUAIActScraper,
    "patents": PatentsScraper,
}


async def run_url_scrape(run_id: int, url: str):
    """Run a scrape on a single URL."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return
        run.status = "running"
        db.commit()

    try:
        # Scrape
        async with URLScraper(url=url, user_agent=config.SCRAPE_USER_AGENT) as scraper:
            docs = await scraper.scrape()

        # Process results
        await _process_documents(run_id, docs)

        # Update run status
        _finalize_run(run_id)

    except Exception as e:
        _fail_run(run_id, str(e))
        traceback.print_exc()


async def run_source_scrape(run_id: int, sources: list[str], max_results: int = 60):
    """Run a scrape on selected sources."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return
        run.status = "running"
        db.commit()

    try:
        all_docs = []

        for source_name in sources:
            scraper_class = SCRAPER_MAP.get(source_name)
            if not scraper_class:
                print(f"[Processor] Unknown source: {source_name}")
                continue

            print(f"[Processor] Scraping {source_name}...")
            try:
                async with scraper_class(
                    user_agent=config.SCRAPE_USER_AGENT,
                    delay=config.SCRAPE_DELAY_SECONDS,
                    max_results=max_results,
                ) as scraper:
                    docs = await scraper.scrape()
                    all_docs.extend(docs)
                    print(f"[Processor] {source_name}: found {len(docs)} documents")
            except Exception as e:
                print(f"[Processor] {source_name} failed: {e}")
                continue

        # Process results
        await _process_documents(run_id, all_docs)

        # Update run status
        _finalize_run(run_id)

    except Exception as e:
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
                    with get_db() as db:
                        for cls in result["classifications"]:
                            if not cls.get("matched", False):
                                continue

                            cat_id = cls.get("category_id", "")
                            confidence = cls.get("confidence", 0.0)
                            status = apply_confidence_gate(confidence, cat_id)

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
                            )
                            db.add(classification)
                        db.commit()

            except Exception as e:
                print(f"[Processor] Classification failed for '{doc.title}': {e}")


def _finalize_run(run_id: int):
    """Update run with final metrics."""
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
