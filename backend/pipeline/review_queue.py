"""Review queue builder — flags cases for human review.

Ported from Shiv-Evil-AI-Finder/src/review_queue.py.
"""
from __future__ import annotations

from typing import List

from backend.pipeline.io_utils import stable_hash
from backend.schemas import CandidateCase, EntityRecord, ReviewItem


def build_review_queue(
    entities: List[EntityRecord],
    cases: List[CandidateCase],
    *,
    review_confidence: float = 0.60,
    high_confidence: float = 0.75,
    seed_names: List[str] | None = None,
) -> List[ReviewItem]:
    """Generate review items from entities and cases that need human attention."""
    reviews: List[ReviewItem] = []
    normalized_seeds = {
        name.strip().lower() for name in (seed_names or []) if name
    }

    for entity in entities:
        # Low confidence entities
        if entity.confidence < review_confidence:
            reviews.append(
                ReviewItem(
                    review_id=stable_hash("review", entity.entity_id, "low_conf"),
                    reason="low_confidence",
                    severity="medium",
                    entity_name=entity.entity_name,
                    source_url=entity.source_urls[0] if entity.source_urls else "",
                    case_id=entity.related_case_ids[0] if entity.related_case_ids else "",
                    details=(
                        f"Entity '{entity.entity_name}' has confidence "
                        f"{entity.confidence:.2f}, below review threshold {review_confidence:.2f}."
                    ),
                    suggested_code=entity.canonical_code,
                )
            )

        # Novel entities (not in seed data)
        if not entity.seed_overlap and entity.confidence >= review_confidence:
            reviews.append(
                ReviewItem(
                    review_id=stable_hash("review", entity.entity_id, "novel"),
                    reason="novel_entity",
                    severity="low",
                    entity_name=entity.entity_name,
                    source_url=entity.source_urls[0] if entity.source_urls else "",
                    case_id=entity.related_case_ids[0] if entity.related_case_ids else "",
                    details=(
                        f"Entity '{entity.entity_name}' ({entity.canonical_code}) "
                        f"is not in the seed examples — confirm classification."
                    ),
                    suggested_code=entity.canonical_code,
                )
            )

    # Cases with missing entity names
    for case in cases:
        if not case.entity_name:
            reviews.append(
                ReviewItem(
                    review_id=stable_hash("review", case.case_id, "no_name"),
                    reason="missing_entity_name",
                    severity="high",
                    entity_name="",
                    source_url=case.source_url,
                    case_id=case.case_id,
                    details=(
                        f"Classification found code {case.final_code} at "
                        f"confidence {case.confidence:.2f} but no entity name "
                        f"could be extracted."
                    ),
                    suggested_code=case.final_code,
                )
            )

    return reviews
