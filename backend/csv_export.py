"""Build CSV exports for run findings (aligned with CLI-style flat entity/review rows)."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from backend.database import get_db
from backend.models import Classification, Document, Entity, Run

# Stable column order for review handoff (matches common pipeline export fields + app rubric).
RUN_FINDINGS_FIELDNAMES = [
    "run_id",
    "run_type",
    "reviewer_name",
    "document_id",
    "document_url",
    "document_title",
    "document_source_name",
    "document_type",
    "document_keyword_matched",
    "classification_id",
    "entity_name",
    "canonical_code",
    "subgroup_name",
    "confidence",
    "review_status",
    "merge_confidence",
    "rationale",
    "source_urls",
    "source_titles",
    "evidence_texts",
    "evidence_quotes_json",
    "criteria_scores_json",
    "developer_org",
    "abuse_description",
    "descriptive_category",
    "criminal_or_controversial",
    "tool_website_url",
    "public_tagline",
    "stated_use_case",
    "target_victim",
    "primary_output",
    "harm_category",
    "gate_1",
    "gate_2",
    "gate_3",
    "exclusion_1",
    "exclusion_2",
    "exclusion_3",
    "include_in_repo",
    "evidence_summary",
    "is_gray_area",
    "relevance_score",
    "signal_debug_json",
    "ambiguous_codes",
    "guidelines_version",
    "classified_at",
]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}" if value == value else ""
    return str(value)


def build_run_findings_csv(run_id: int) -> tuple[bytes, str]:
    """
    Return UTF-8 CSV bytes and suggested filename for matched classifications in a run.
    Rows mirror CLI entity_records-style fields where applicable (entity_name, canonical_code, etc.).
    """
    rows: list[dict[str, str]] = []

    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise ValueError("run not found")

        documents = (
            db.query(Document)
            .filter(Document.run_id == run_id)
            .order_by(Document.id)
            .all()
        )

        reviewer = run.reviewer_name or ""
        run_type = run.run_type or ""

        for doc in documents:
            classifications = (
                db.query(Classification)
                .filter(Classification.document_id == doc.id, Classification.matched == True)
                .order_by(Classification.id)
                .all()
            )
            for c in classifications:
                evidence_quotes = c.evidence_quotes or ""
                try:
                    eq_parsed = json.loads(evidence_quotes) if evidence_quotes else []
                    evidence_texts = " | ".join(
                        str(x) for x in (eq_parsed if isinstance(eq_parsed, list) else [])
                    )
                except json.JSONDecodeError:
                    evidence_texts = evidence_quotes

                criteria = c.criteria_scores or ""
                classified_at = ""
                if c.classified_at:
                    classified_at = c.classified_at.isoformat()

                rows.append(
                    {
                        "run_id": _cell(run_id),
                        "run_type": _cell(run_type),
                        "reviewer_name": _cell(reviewer),
                        "document_id": _cell(doc.id),
                        "document_url": _cell(doc.url),
                        "document_title": _cell(doc.title),
                        "document_source_name": _cell(doc.source_name),
                        "document_type": _cell(doc.document_type),
                        "document_keyword_matched": _cell(doc.keyword_matched),
                        "classification_id": _cell(c.id),
                        "entity_name": _cell(c.ai_system_name),
                        "canonical_code": _cell(c.category_id),
                        "subgroup_name": _cell(c.category_name),
                        "confidence": _cell(c.confidence),
                        "review_status": _cell(c.status),
                        "merge_confidence": _cell(c.confidence),
                        "rationale": _cell(c.reasoning),
                        "source_urls": _cell(doc.url),
                        "source_titles": _cell(doc.title),
                        "evidence_texts": evidence_texts or _cell(c.evidence_summary),
                        "evidence_quotes_json": _cell(c.evidence_quotes),
                        "criteria_scores_json": _cell(criteria),
                        "developer_org": _cell(c.developer_org),
                        "abuse_description": _cell(c.abuse_description),
                        "descriptive_category": _cell(c.descriptive_category),
                        "criminal_or_controversial": _cell(c.criminal_or_controversial),
                        "tool_website_url": _cell(c.tool_website_url),
                        "public_tagline": _cell(c.public_tagline),
                        "stated_use_case": _cell(c.stated_use_case),
                        "target_victim": _cell(c.target_victim),
                        "primary_output": _cell(c.primary_output),
                        "harm_category": _cell(c.harm_category),
                        "gate_1": _cell(c.gate_1),
                        "gate_2": _cell(c.gate_2),
                        "gate_3": _cell(c.gate_3),
                        "exclusion_1": _cell(c.exclusion_1),
                        "exclusion_2": _cell(c.exclusion_2),
                        "exclusion_3": _cell(c.exclusion_3),
                        "include_in_repo": _cell(c.include_in_repo),
                        "evidence_summary": _cell(c.evidence_summary),
                        "is_gray_area": _cell(c.is_gray_area),
                        "relevance_score": _cell(c.relevance_score),
                        "signal_debug_json": _cell(c.signal_debug),
                        "ambiguous_codes": _cell(c.ambiguous_codes),
                        "guidelines_version": _cell(c.guidelines_version),
                        "classified_at": classified_at,
                    }
                )

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=RUN_FINDINGS_FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in RUN_FINDINGS_FIELDNAMES})

    text = buffer.getvalue()
    # UTF-8 BOM helps Excel recognize encoding on Windows.
    data = ("\ufeff" + text).encode("utf-8")
    filename = f"run_{run_id}_entity_records.csv"
    return data, filename
