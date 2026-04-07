"""Classification pipeline — keyword filter + Shiv hybrid pre-score + Ollama LLM classification."""
import json
import re
import httpx
from typing import Any, Optional
from backend.config import config
from backend.pipeline.examples_csv import format_examples_for_prompt, merge_known_names
from backend.schemas import ClassificationResult, ClassificationSignal


# ---------------------------------------------------------------------------
# Shiv Hybrid Pre-Scorer (rule + prototype + optional ML scoring)
# Loaded lazily on first use since taxonomy parsing takes a moment.
# ---------------------------------------------------------------------------

_hybrid_scorer = None
_relevance_scorer = None


def _load_scorers():
    """Lazily load taxonomy, seeds, and build the scorers."""
    global _hybrid_scorer, _relevance_scorer
    if _hybrid_scorer is not None:
        return

    from backend.pipeline.taxonomy import load_taxonomy, load_seed_examples
    from backend.pipeline.ml_models import KeywordScorer, PrototypeClassifier
    from backend.pipeline.taxonomy import build_code_lexicons, build_reference_texts

    try:
        nodes = load_taxonomy(config.SEED_PDF_PATH)
        seeds = load_seed_examples(config.SEED_CSV_PATH, nodes)
    except Exception as e:
        print(f"[Classifier] Warning: Could not load taxonomy/seeds: {e}")
        print("[Classifier] Hybrid pre-scoring disabled; using keyword+LLM only.")
        _hybrid_scorer = False  # sentinel: disabled
        _relevance_scorer = False
        return

    lexicons = build_code_lexicons(nodes, seeds)
    reference_texts = build_reference_texts(nodes, seeds)

    _hybrid_scorer = {
        "nodes": nodes,
        "seeds": seeds,
        "keyword_scorer": KeywordScorer(lexicons),
        "prototype": PrototypeClassifier().fit(reference_texts),
        "taxonomy_map": {n.code: n for n in nodes},
    }

    try:
        from backend.pipeline.relevance import RelevanceScorer
        _relevance_scorer = RelevanceScorer(nodes, seeds)
    except Exception as e:
        print(f"[Classifier] Warning: RelevanceScorer failed: {e}")
        _relevance_scorer = False


def hybrid_pre_score(text: str, title: str = "", url: str = "") -> Optional[ClassificationResult]:
    """Run Shiv-style rule+prototype pre-scoring. Returns None if scorers aren't loaded."""
    _load_scorers()
    if not _hybrid_scorer or _hybrid_scorer is False:
        return None

    combined_text = f"{title} {text}"
    keyword_scores = _hybrid_scorer["keyword_scorer"].score(combined_text)
    prototype_scores = _hybrid_scorer["prototype"].score(combined_text)
    reason_map = _hybrid_scorer["keyword_scorer"].reasons(combined_text)
    taxonomy_map = _hybrid_scorer["taxonomy_map"]

    # Combine scores
    combined_scores = {}
    for code in set(list(keyword_scores.keys()) + list(prototype_scores.keys())):
        kw = keyword_scores.get(code, 0.0)
        pt = prototype_scores.get(code, 0.0)
        combined_scores[code] = 0.55 * kw + 0.45 * pt

    if not combined_scores:
        return None

    best_code = max(combined_scores, key=combined_scores.get)
    best_score = combined_scores[best_code]

    if best_score < config.CLASSIFICATION_THRESHOLD:
        return None

    node = taxonomy_map.get(best_code)
    subgroup_name = node.subgroup_name if node else "Unknown"
    gray_area = node.gray_area if node else False

    # Ambiguous codes: other codes close to the best score
    ambiguous = [
        code for code, score in combined_scores.items()
        if code != best_code and score >= best_score * 0.7
    ]

    signals = [
        ClassificationSignal(
            name="keyword_rules",
            code_scores=keyword_scores,
            reasons=reason_map.get(best_code, [])[:4],
            weight=0.55,
        ),
        ClassificationSignal(
            name="prototype_similarity",
            code_scores=prototype_scores,
            weight=0.45,
        ),
    ]

    return ClassificationResult(
        final_code=best_code,
        subgroup_name=subgroup_name,
        confidence=best_score,
        rationale=f"Rule+prototype pre-score: {best_code} ({subgroup_name}) at {best_score:.2f}",
        signal_scores=combined_scores,
        debug_signals=signals,
        ambiguous_codes=ambiguous,
        gray_area=gray_area,
    )


def get_relevance_score(text: str) -> Optional[dict]:
    """Get relevance score for a text using the Shiv scorer. Returns None if not available."""
    _load_scorers()
    if not _relevance_scorer or _relevance_scorer is False:
        return None
    return _relevance_scorer.score_text(text)

# ---------------------------------------------------------------------------
# Keyword dictionaries for all 15 subcategories
# Each list contains indicator terms for that subcategory.
# ---------------------------------------------------------------------------

KEYWORD_DICTIONARY = {
    "1A": {
        "name": "Automated Disinformation Systems",
        "keywords": [
            "disinformation", "misinformation", "fake news", "fabricated content",
            "propaganda", "information warfare", "bot farm", "bot network",
            "coordinated inauthentic", "influence operation", "troll farm",
            "AI-generated news", "synthetic news", "false narrative",
            "election interference", "state-sponsored", "computational propaganda",
            "astroturfing", "narrative manipulation", "information manipulation",
        ],
    },
    "1B": {
        "name": "Synthetic Media Deception",
        "keywords": [
            "deepfake", "face swap", "voice cloning", "synthetic media",
            "impersonation", "non-consensual", "nudify", "undress",
            "fake nude", "AI-generated porn", "face generation", "GAN",
            "audio deepfake", "video manipulation", "identity theft",
            "image abuse", "revenge porn", "NCII", "clothoff",
            "nonconsensual intimate", "deepswap",
        ],
    },
    "1C": {
        "name": "Narrative Amplification Engines",
        "keywords": [
            "outrage amplification", "polarization", "radicalization",
            "engagement optimization", "filter bubble", "echo chamber",
            "extremism", "hate speech amplification", "inflammatory content",
            "algorithmic radicalization", "rage bait", "divisive content",
            "emotional manipulation", "ideological clustering",
        ],
    },
    "2A": {
        "name": "Predatory Targeting Systems",
        "keywords": [
            "predatory targeting", "vulnerable population", "behavioral profiling",
            "exploitation", "dark pattern", "manipulative design",
            "scam", "romance fraud", "phishing", "social engineering",
            "identity fraud", "fake identity", "KYC bypass", "fake ID",
            "catfishing", "romance scam", "predatory lending",
            "targeting vulnerable", "adaptive manipulation",
        ],
    },
    "2B": {
        "name": "Addiction Optimization Systems",
        "keywords": [
            "addiction optimization", "compulsive engagement", "infinite scroll",
            "dopamine", "attention exploitation", "screen time",
            "engagement maximization", "content escalation",
            "reinforcement loop", "habit forming", "time spent optimization",
        ],
    },
    "2C": {
        "name": "Financial Extraction Algorithms",
        "keywords": [
            "financial extraction", "predatory pricing", "dynamic pricing",
            "debt maximization", "fee exploitation", "economic dependency",
            "invoice fraud", "wire fraud", "payment fraud",
            "financial manipulation", "algorithmic discrimination",
            "business email compromise", "BEC", "price discrimination",
        ],
    },
    "3A": {
        "name": "Mass Surveillance Systems",
        "keywords": [
            "mass surveillance", "facial recognition", "biometric tracking",
            "population monitoring", "warrantless", "bulk collection",
            "CCTV AI", "video analytics", "person tracking",
            "clearview", "facewatch", "briefcam", "biometric database",
            "real-time identification", "watchlist", "behavioral tracking",
            "surveillance state", "panopticon",
        ],
    },
    "3B": {
        "name": "Predictive Suppression Systems",
        "keywords": [
            "predictive policing", "crime prediction", "pre-crime",
            "social scoring", "risk scoring", "behavioral prediction",
            "dissent suppression", "protest monitoring", "political surveillance",
            "predictive suppression", "predpol", "geolitica",
            "freedom restriction", "automated profiling",
        ],
    },
    "3C": {
        "name": "Social Scoring Mechanisms",
        "keywords": [
            "social credit", "citizen score", "trustworthiness score",
            "behavioral score", "loyalty score", "social scoring",
            "access restriction", "credit system", "compliance score",
            "social rating", "blacklist system",
        ],
    },
    "4A": {
        "name": "Automated Cyberattack Tools",
        "keywords": [
            "cyberattack", "malware", "ransomware", "phishing tool",
            "exploit", "vulnerability scanner", "hacking tool",
            "wormgpt", "fraudgpt", "ghostgpt", "evil-gpt",
            "darkbert", "uncensored AI", "jailbreak", "offensive AI",
            "penetration testing", "reverse shell", "payload generator",
            "cybercrime", "credential theft", "infostealer",
            "malicious LLM", "no-filter AI", "xanthorox",
            "spamgpt", "kawaiigpt", "darkwizard",
            "crime llm", "malicious chatbot", "dark web llm", "uncensored llm",
            "stolen model", "warez llm", "hacking gpt",
        ],
    },
    "4B": {
        "name": "Infrastructure Disruption Systems",
        "keywords": [
            "infrastructure attack", "power grid", "SCADA",
            "critical infrastructure", "hospital disruption",
            "transportation attack", "ICS attack", "OT security",
            "cyber-physical", "grid disruption", "utility attack",
        ],
    },
    "4C": {
        "name": "Autonomous Weaponization",
        "keywords": [
            "autonomous weapon", "killer robot", "lethal autonomous",
            "LAWS", "military AI", "drone strike", "automated targeting",
            "combat drone", "weaponized AI", "target selection",
            "habsora", "lavender", "gospel", "lethal force",
            "autonomous drone", "attack drone", "kamikaze drone",
            "military targeting", "where's daddy", "reaper",
        ],
    },
    "5A": {
        "name": "Metric Gaming Systems",
        "keywords": [
            "metric gaming", "Goodhart", "performance manipulation",
            "reporting fraud", "metric manipulation", "KPI gaming",
            "audit manipulation", "compliance gaming", "benchmark cheating",
        ],
    },
    "5B": {
        "name": "Market Manipulation Systems",
        "keywords": [
            "market manipulation", "algorithmic trading abuse",
            "price manipulation", "pump and dump", "spoofing",
            "wash trading", "front running", "insider trading",
            "high-frequency manipulation", "market distortion",
        ],
    },
    "5C": {
        "name": "Accountability Evasion Systems",
        "keywords": [
            "accountability evasion", "opacity", "black box",
            "unauditable", "untraceable", "anonymous operator",
            "deliberate opacity", "regulatory evasion", "audit barrier",
            "decision concealment", "responsibility obfuscation",
        ],
    },
}

# Gray area subcategories
GRAY_AREA_SUBCATEGORIES = {"2B", "5B"}
# Undecided criteria subcategories
UNDECIDED_CRITERIA = {"3C", "5A"}

# Well-known malicious AI systems mapped to their primary subcategory.
# Used for guaranteed detection even when keyword density is low.
_BASE_KNOWN_EVIL_AI_NAMES: dict[str, str] = {
    "fraudgpt": "4A",
    "wormgpt": "4A",
    "ghostgpt": "4A",
    "darkbert": "4A",
    "darkbard": "4A",
    "evil-gpt": "4A",
    "evilgpt": "4A",
    "xanthorox": "4A",
    "spamgpt": "4A",
    "kawaiigpt": "4A",
    "darkwizard": "4A",
    "pentest-gpt": "4A",
    "hackedgpt": "4A",
    "chaosgpt": "4A",
    "poisongpt": "4A",
    "escapegpt": "4A",
    "xxxgpt": "2A",
    "lovegpt": "2A",
    "onlyfakes": "1B",
    "clothoff": "1B",
    "deepswap": "1B",
    "clearview": "3A",
    "facewatch": "3A",
    "briefcam": "3A",
    "predpol": "3B",
    "geolitica": "3B",
    "habsora": "4C",
    "lavender": "4C",
    "gospel": "4C",
}

# Merged at import: built-in names + non-conflicting aliases from examples.csv
KNOWN_EVIL_AI_NAMES: dict[str, str] = merge_known_names(_BASE_KNOWN_EVIL_AI_NAMES)


def _normalize_yn(value: Any) -> str:
    """Map model output to Y or N (default N when unclear)."""
    if value is None:
        return "N"
    s = str(value).strip().upper()
    if s in ("Y", "YES", "TRUE", "1"):
        return "Y"
    if s in ("N", "NO", "FALSE", "0"):
        return "N"
    return "N"


def _nonempty_str(value: Any, default: str) -> str:
    if value is None:
        return default
    t = str(value).strip()
    return t if t else default


def _fallback_tool_url(document_url: str) -> str:
    u = (document_url or "").strip()
    if u.lower().startswith(("http://", "https://")):
        return u
    return "N/A"


def build_document_excerpt_for_llm(text: str, max_chars: Optional[int] = None) -> str:
    """Use head + tail of long documents so abstracts and conclusions both reach the model."""
    limit = max_chars if max_chars is not None else config.LLM_DOCUMENT_MAX_CHARS
    t = text or ""
    if len(t) <= limit:
        return t
    sep = "\n\n[... middle of document omitted for length ...]\n\n"
    budget = limit - len(sep)
    head_n = budget // 2
    tail_n = budget - head_n
    return t[:head_n] + sep + t[-tail_n:]


def coerce_matched_field(value: Any) -> bool:
    """
    Normalize LLM / JSON matched field. Non-empty strings like 'false' must be treated as False
    (otherwise Python truthiness breaks filtering).
    """
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value) and value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes", "y"):
            return True
        return False
    return bool(value)


def _infer_name_clarity(ai_system_name: str) -> str:
    """Heuristic when the model omits name_clarity."""
    name = (ai_system_name or "").strip().lower()
    if not name:
        return "unknown"
    if name.startswith("unnamed system"):
        return "unknown"
    generic = (
        "the model", "the system", "this ai", "the ai", "a model",
        "large language model", "generative ai", "ai system",
    )
    if name in generic or any(g in name for g in ("the model", "this system")):
        return "generic"
    if len(ai_system_name.strip()) <= 2:
        return "generic"
    return "named_product"


def apply_confidence_adjustments(cls: dict) -> None:
    """
    Lower confidence for vague or unnamed systems; slight boost for known evil-AI names.
    Merges name_clarity into criteria_scores for storage.
    """
    raw = float(cls.get("confidence") or 0.0)
    nc = (cls.get("name_clarity") or "").strip().lower()
    if not nc or nc not in ("named_product", "concept_only", "generic", "unknown"):
        nc = _infer_name_clarity(cls.get("ai_system_name", ""))
    cls["name_clarity"] = nc

    mult = 1.0
    if nc == "unknown":
        mult *= 0.52
    elif nc == "generic":
        mult *= 0.58
    elif nc == "concept_only":
        mult *= 0.78
    elif nc == "named_product":
        mult *= 1.0

    aname = (cls.get("ai_system_name") or "").lower()
    if "unnamed system" in aname:
        mult *= 0.48
    if len((cls.get("ai_system_name") or "").strip()) <= 2:
        mult *= 0.5

    for known in KNOWN_EVIL_AI_NAMES:
        if known in aname:
            mult = min(1.0, mult * 1.12)
            break

    new_conf = max(0.0, min(1.0, raw * mult))

    cs = cls.get("criteria_scores")
    if isinstance(cs, str):
        try:
            cs = json.loads(cs)
        except (json.JSONDecodeError, TypeError):
            cs = {}
    if not isinstance(cs, dict):
        cs = {}
    cs["name_clarity"] = nc
    cs["confidence_raw"] = round(raw, 4)
    cs["confidence_multiplier"] = round(mult, 4)
    cls["criteria_scores"] = cs
    cls["confidence"] = new_conf


def normalize_classification_rubric(
    cls: dict,
    *,
    document_url: str = "",
    document_title: str = "",
) -> dict:
    """
    Ensure every rubric field is a non-empty string suitable for display/storage.
    Recomputes include_in_repo from gates and exclusions after Y/N normalization.
    """
    cls["matched"] = coerce_matched_field(cls.get("matched"))

    cat_id = _nonempty_str(cls.get("category_id"), "Unknown")
    cat_name = _nonempty_str(
        cls.get("category_name"),
        KEYWORD_DICTIONARY.get(cat_id, {}).get("name", "Unknown subcategory"),
    )

    cls["category_id"] = cat_id
    cls["category_name"] = cat_name

    title_hint = _nonempty_str(document_title, "this document")[:200]
    cls["ai_system_name"] = _nonempty_str(
        cls.get("ai_system_name"),
        f"Unnamed system ({cat_name})",
    )
    cls["criminal_or_controversial"] = _nonempty_str(
        cls.get("criminal_or_controversial"),
        "Not specified in extraction; see evidence summary",
    )
    cls["descriptive_category"] = _nonempty_str(
        cls.get("descriptive_category"),
        f"Match: {cat_name}",
    )
    tw = _nonempty_str(cls.get("tool_website_url"), "")
    if tw.upper() in ("", "N/A", "NONE", "UNKNOWN"):
        cls["tool_website_url"] = _fallback_tool_url(document_url)
    else:
        cls["tool_website_url"] = tw

    cls["developer_org"] = _nonempty_str(cls.get("developer_org"), "Unknown")
    cls["public_tagline"] = _nonempty_str(cls.get("public_tagline"), "N/A")
    cls["stated_use_case"] = _nonempty_str(
        cls.get("stated_use_case"),
        _nonempty_str(cls.get("abuse_description"), "Not stated in the excerpt"),
    )
    cls["target_victim"] = _nonempty_str(
        cls.get("target_victim"),
        "Not specified in extraction",
    )
    cls["primary_output"] = _nonempty_str(
        cls.get("primary_output"),
        "Not specified in extraction",
    )
    cls["harm_category"] = _nonempty_str(
        cls.get("harm_category"),
        cat_name,
    )

    for key in ("gate_1", "gate_2", "gate_3", "exclusion_1", "exclusion_2", "exclusion_3"):
        cls[key] = _normalize_yn(cls.get(key))

    if (
        _normalize_yn(cls.get("gate_1")) == "Y"
        and _normalize_yn(cls.get("gate_2")) == "Y"
        and _normalize_yn(cls.get("gate_3")) == "Y"
        and _normalize_yn(cls.get("exclusion_1")) == "N"
        and _normalize_yn(cls.get("exclusion_2")) == "N"
        and _normalize_yn(cls.get("exclusion_3")) == "N"
    ):
        cls["include_in_repo"] = "Y"
    else:
        cls["include_in_repo"] = "N"

    reason = _nonempty_str(cls.get("reasoning"), "")
    abuse = _nonempty_str(cls.get("abuse_description"), "")
    cls["evidence_summary"] = _nonempty_str(
        cls.get("evidence_summary"),
        reason or abuse or f"Document “{title_hint}” relates to {cat_name}.",
    )
    cls["reasoning"] = reason or cls["evidence_summary"]
    cls["abuse_description"] = abuse or cls["evidence_summary"]

    # Verbatim quotes (LLM); default empty list for DB JSON
    eq = cls.get("evidence_quotes")
    if eq is None:
        cls["evidence_quotes"] = []
    elif isinstance(eq, str):
        cls["evidence_quotes"] = [eq] if eq.strip() else []
    elif isinstance(eq, list):
        cls["evidence_quotes"] = [str(x)[:800] for x in eq[:15]]
    else:
        cls["evidence_quotes"] = []

    return cls


def normalize_classifications_result(
    result: dict,
    *,
    document_url: str = "",
    document_title: str = "",
) -> dict:
    """Normalize each classification entry; no-op if structure is missing."""
    if not result or "classifications" not in result:
        return result
    out = dict(result)
    normalized = []
    for c in result["classifications"]:
        row = normalize_classification_rubric(
            dict(c), document_url=document_url, document_title=document_title
        )
        apply_confidence_adjustments(row)
        normalized.append(row)
    out["classifications"] = normalized
    return out


def keyword_filter(text: str) -> dict:
    """
    Run keyword filtering against all subcategories.
    Returns dict of matched subcategories with their hit counts.
    Two hits normally required; a single hit counts if it is a known malicious-AI name
    (e.g. fraudgpt) so obvious tools are not missed.
    """
    text_lower = text.lower()
    compact = re.sub(r"[^a-z0-9]+", "", text_lower)
    matches = {}

    for cat_id, cat_data in KEYWORD_DICTIONARY.items():
        hits = []
        for keyword in cat_data["keywords"]:
            if keyword.lower() in text_lower:
                hits.append(keyword)
        ok = len(hits) >= 2
        if not ok and len(hits) == 1:
            h0 = hits[0].lower()
            if h0 in KNOWN_EVIL_AI_NAMES:
                ok = True
            else:
                nk = re.sub(r"[^a-z0-9]+", "", h0)
                for kn in KNOWN_EVIL_AI_NAMES:
                    if nk == re.sub(r"[^a-z0-9]+", "", kn):
                        ok = True
                        break
        if ok:
            matches[cat_id] = {
                "name": cat_data["name"],
                "hits": hits,
                "count": len(hits),
            }

    return matches


def name_match_filter(text: str, url: str = "", title: str = "") -> dict:
    """Detect known evil AI system names in text, URL, or title.
    Uses substring and compact (alphanumeric-only) matching so "Fraud GPT" still hits."""
    combined = f"{url} {title} {text}".lower()
    compact = re.sub(r"[^a-z0-9]+", "", combined)
    matches: dict = {}

    for name, cat_id in KNOWN_EVIL_AI_NAMES.items():
        hit = False
        if name in combined:
            hit = True
        else:
            key = re.sub(r"[^a-z0-9]+", "", name.lower())
            if len(key) >= 4 and key in compact:
                hit = True
        if not hit:
            continue

        cat_data = KEYWORD_DICTIONARY.get(cat_id, {})
        cat_name = cat_data.get("name", cat_id)
        if cat_id not in matches:
            matches[cat_id] = {
                "name": cat_name,
                "hits": [name],
                "count": 1,
            }
        else:
            if name not in matches[cat_id]["hits"]:
                matches[cat_id]["hits"].append(name)
            matches[cat_id]["count"] = len(matches[cat_id]["hits"])

    return matches


def _detectors_suggest_evil(
    keyword_matches: dict,
    text: str,
    title: str = "",
    url: str = "",
) -> bool:
    """True if keyword/name heuristics indicate the doc may discuss a harmful AI system."""
    if keyword_matches:
        return True
    combined = f"{url} {title} {text}".lower()
    compact = re.sub(r"[^a-z0-9]+", "", combined)
    for name in KNOWN_EVIL_AI_NAMES:
        key = re.sub(r"[^a-z0-9]+", "", name.lower())
        if len(key) >= 4 and key in compact:
            return True
        if name in combined:
            return True
    return False


def _result_has_matched_evil(raw: dict) -> bool:
    for c in raw.get("classifications") or []:
        if coerce_matched_field(c.get("matched")):
            return True
    return False


def _merge_keyword_and_name_matches(
    keyword_matches: dict,
    text: str,
    title: str = "",
    url: str = "",
) -> dict:
    """Union of keyword_filter-style matches and name_match_filter (known evil-AI names)."""
    merged = dict(keyword_matches or {})
    nm = name_match_filter(text, url=url, title=title)
    for cat_id, match_data in nm.items():
        if cat_id not in merged:
            merged[cat_id] = match_data
        else:
            seen = set(merged[cat_id]["hits"])
            for h in match_data.get("hits", []):
                if h not in seen:
                    merged[cat_id]["hits"].append(h)
                    seen.add(h)
            merged[cat_id]["count"] = len(merged[cat_id]["hits"])
    return merged


def _parse_ollama_json_content(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            return json.loads(json_match.group())
        raise


async def _ollama_chat_json(system_prompt: str, user_message: str) -> dict:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{config.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_predict": config.LLM_MAX_TOKENS,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        return _parse_ollama_json_content(content)


async def _ollama_chat_text(system_prompt: str, user_message: str) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{config.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": config.LLM_MAX_TOKENS,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")


def _format_detector_hints(keyword_matches: dict, text: str, title: str, url: str) -> str:
    parts = [
        "Automated detectors found the following signals (use them — do not return empty if a named harmful AI is clearly indicated):",
        f"- URL: {url}",
        f"- Title: {title}",
    ]
    if keyword_matches:
        parts.append("- Keyword / category hits:")
        for cat_id, data in keyword_matches.items():
            parts.append(f"  * {cat_id} ({data.get('name', '')}): {', '.join(data.get('hits', [])[:12])}")
    else:
        parts.append("- No multi-keyword bucket match; still scan for proper names of malicious AI tools.")
    tail = (text or "")[:4000]
    parts.append(f"- Document excerpt (start):\n{tail}")
    return "\n".join(parts)


def _heuristic_web_queries_from_raw(raw: dict) -> list[str]:
    """If the model omitted needs_web_search, suggest queries for matched rows missing URLs."""
    out: list[str] = []
    for c in raw.get("classifications") or []:
        if not c.get("matched"):
            continue
        name = (c.get("ai_system_name") or "").strip()
        if not name or "unnamed" in name.lower():
            continue
        tw = (c.get("tool_website_url") or "").strip().upper()
        if tw not in ("", "N/A", "NONE", "UNKNOWN"):
            continue
        out.append(f'"{name}" AI tool malware OR official website OR github')
        if len(out) >= config.LLM_WEB_SEARCH_MAX_QUERIES:
            break
    return out


async def _maybe_refine_with_web_search(
    raw: dict,
    text: str,
    title: str,
    url: str,
) -> dict:
    from backend.pipeline.web_lookup import fetch_snippets_for_queries, web_search_configured

    if not config.LLM_REFINE_WITH_SEARCH or not web_search_configured():
        return raw

    queries = list(raw.get("web_search_queries") or [])
    if raw.get("needs_web_search"):
        pass
    elif not queries:
        queries = _heuristic_web_queries_from_raw(raw)

    if not queries:
        return raw

    queries = queries[: config.LLM_WEB_SEARCH_MAX_QUERIES]
    snippets = await fetch_snippets_for_queries(queries)
    if not snippets.strip():
        return raw

    body = build_document_excerpt_for_llm(text)
    refine_system = """You refine an existing JSON classification using optional WEB SEARCH SNIPPETS.
Rules:
- Return ONLY valid JSON with the same schema as before (classifications array + top-level needs_web_search: false, web_search_queries: [], web_search_reason: "").
- Use snippets only to fill tool_website_url, developer_org, public_tagline, or to disambiguate names when snippets clearly refer to the same system as the document.
- Do not fabricate evidence_quotes — copy verbatim from the ORIGINAL DOCUMENT TEXT section only; leave shorter if needed.
- If the document already named a malicious AI (e.g. crime LLMs, uncensored harm bots), keep matched:true.
- Merge duplicate systems; preserve the strongest rubric per system."""

    refine_user = f"""Document Title: {title}
Source URL: {url}

ORIGINAL DOCUMENT TEXT:
{body}

PREVIOUS JSON (may be incomplete):
{json.dumps(raw, ensure_ascii=False)[:12000]}

WEB SEARCH SNIPPETS (third party; may be noisy):
{snippets[:14000]}

Return the updated full JSON object."""

    try:
        refined = await _ollama_chat_json(refine_system, refine_user)
        if refined.get("classifications"):
            return refined
    except Exception as e:
        print(f"[Classifier] Web refine pass failed: {e}")
    return raw


async def classify_with_ollama(
    text: str,
    title: str = "",
    url: str = "",
    keyword_matches: dict = None,
) -> Optional[dict]:
    """
    Multi-stage classification:
    1. Shiv hybrid pre-score (rule + prototype + optional ML)
    2. Primary LLM pass (prosecutor/defense/judge)
    3. Optional guided retry when detectors fire but model returns nothing
    4. Optional web-search snippet pass
    5. Confidence reconciliation with pre-score signals
    """
    km = keyword_matches or {}

    # Stage 1: Shiv hybrid pre-score
    pre_score = hybrid_pre_score(text, title=title, url=url)
    relevance = get_relevance_score(text)

    if not config.USE_LLM:
        return _keyword_only_classification(
            km,
            document_url=url,
            document_title=title,
            pre_score=pre_score,
            relevance=relevance,
        )

    try:
        guidelines_text = config.GUIDELINES_PATH.read_text()
    except Exception:
        guidelines_text = "Guidelines file not found."

    examples_block = format_examples_for_prompt()
    if examples_block:
        guidelines_text = f"{guidelines_text}\n\n{examples_block}"

    system_prompt = f"""You are a classification assistant for the "AI for Evil" research project.
You will be given a document that may describe one or MORE AI systems.

Classification guidelines:

{guidelines_text}

DETECTION PRIORITY (read carefully):
- If the document names a malicious AI product (crime LLMs sold on forums/Telegram/dark web, uncensored "harm" chatbots, well-known rogue models like FraudGPT/WormGPT-style tools, biometric surveillance products named in reporting, etc.), you MUST set matched:true for that system and name_clarity:"named_product" when the name appears — even in a short article.
- matched:false is ONLY for pure generic AI policy commentary with NO identifiable system, product, or clearly described operational deployment.
- Confidence can be lower for thin articles, but do NOT suppress a real named harmful AI.

MULTI-ENTITY RULE: If the document describes MULTIPLE distinct AI systems, create a
SEPARATE entry for EACH one, even under the same subcategory.

Also include at the ROOT of the JSON object:
- needs_web_search: boolean — true if you need external web results to fill tool_website_url, developer_org, tagline, or to verify a name not fully described in the document.
- web_search_queries: array of 1-3 concise search strings ONLY if needs_web_search is true (e.g. "FraudGPT cybercrime Telegram"); else [].
- web_search_reason: one short sentence, or "".

For each AI system found, fill in ALL of the following fields:
- category_id: subcategory code (e.g. "1A", "4A")
- category_name: subcategory name from guidelines
- matched: see DETECTION PRIORITY above
- confidence: float 0.0-1.0 — HIGH (>=0.75) when the text names a product OR gives concrete operational detail; LOWER for vague pieces, but still report named systems.
- name_clarity: one of "named_product" | "concept_only" | "generic" | "unknown"
- evidence_quotes: JSON array of 1-4 SHORT verbatim quotes from the document (not invented). Use [] only if matched is false.
- ai_system_name: the tool/system name (REQUIRED unless matched is false — then use "N/A")
- criminal_or_controversial: "Criminal AI" or "Controversial Institutional AI"
- descriptive_category: short label (e.g. "Cybercrime AI Tool")
- tool_website_url: direct URL to the tool (if known, else "N/A")
- developer_org: who made it ("Unknown" if not known)
- public_tagline: what it claims to do ("N/A" if none)
- stated_use_case: what it is designed/used for (1-2 sentences)
- target_victim: who is harmed
- primary_output: what the tool produces
- harm_category: type of harm
- gate_1, gate_2, gate_3, exclusion_1, exclusion_2, exclusion_3: "Y" or "N"
- include_in_repo: "Y" only if all gates Y and all exclusions N
- evidence_summary: 1 sentence
- reasoning: 1 sentence
- abuse_description: 1-2 sentences

Return ONLY valid JSON:
{{
  "classifications": [
    {{
      "category_id": "4A",
      "category_name": "Automated Cyberattack Tools",
      "matched": true,
      "confidence": 0.85,
      "name_clarity": "named_product",
      "evidence_quotes": ["verbatim from document"],
      "ai_system_name": "FraudGPT",
      "criminal_or_controversial": "Criminal AI",
      "descriptive_category": "Cybercrime AI Tool",
      "tool_website_url": "N/A",
      "developer_org": "Unknown",
      "public_tagline": "N/A",
      "stated_use_case": "...",
      "target_victim": "...",
      "primary_output": "...",
      "harm_category": "...",
      "gate_1": "Y",
      "gate_2": "Y",
      "gate_3": "Y",
      "exclusion_1": "N",
      "exclusion_2": "N",
      "exclusion_3": "N",
      "include_in_repo": "Y",
      "evidence_summary": "...",
      "reasoning": "...",
      "abuse_description": "..."
    }}
  ],
  "overall_confidence": 0.85,
  "is_evil_ai": true,
  "needs_web_search": false,
  "web_search_queries": [],
  "web_search_reason": ""
}}

If NO evil AI system is found: {{"classifications": [], "overall_confidence": 0.0, "is_evil_ai": false, "needs_web_search": false, "web_search_queries": [], "web_search_reason": ""}}

MANDATORY: Include every key shown. Use "N/A" or "Unknown" when unknown.
evidence_quotes must be verbatim from the document when matched is true.

Return ONLY valid JSON. No preamble or explanation outside the JSON."""

    body = build_document_excerpt_for_llm(text)
    user_message = f"Document Title: {title}\nSource URL: {url}\n\nDocument Content:\n{body}"

    # Inject hybrid pre-score hints into the LLM context
    if pre_score:
        hint_lines = [
            "\n\n--- AUTOMATED PRE-ANALYSIS (rule + prototype scoring) ---",
            f"Suggested code: {pre_score.final_code} ({pre_score.subgroup_name})",
            f"Pre-score confidence: {pre_score.confidence:.2f}",
        ]
        if pre_score.ambiguous_codes:
            hint_lines.append(f"Ambiguous alternatives: {', '.join(pre_score.ambiguous_codes)}")
        if pre_score.gray_area:
            hint_lines.append("NOTE: This subcategory is flagged as a gray area.")
        top_signals = sorted(
            pre_score.signal_scores.items(), key=lambda x: x[1], reverse=True
        )[:5]
        hint_lines.append(
            "Top signal scores: " + ", ".join(f"{k}={v:.2f}" for k, v in top_signals)
        )
        hint_lines.append("Use these hints to guide but not override your analysis. The final label must be grounded in document evidence.")
        user_message += "\n".join(hint_lines)

    try:
        # Phase 1: Prosecutor Agent
        prosecutor_sys = f"You are the Prosecutor for the AI for Evil tribunal. Guidelines:\n{guidelines_text}\nArgue vigorously WHICH AI systems in the document meet the criteria for being malicious or controversial. Highlight evidence. Keep it under 250 words."
        prosecutor_arg = await _ollama_chat_text(prosecutor_sys, user_message)

        # Phase 2: Defense Agent
        defense_sys = f"You are the Defense Attorney. Guidelines:\n{guidelines_text}\nArgue why the systems mentioned do NOT meet the strict criteria for being malicious, or why the evidence is weak. Defend the AI. Keep it under 250 words."
        defense_user = f"{user_message}\n\n---\nPROSECUTOR'S ARGUMENT:\n{prosecutor_arg}"
        defense_arg = await _ollama_chat_text(defense_sys, defense_user)

        # Phase 3: Judge Agent
        judge_sys = f"You are the presiding Judge. Review the Document, the Prosecutor's Argument, and Defense's Argument. Synthesize them and output the definitive JSON.\n\n{system_prompt}"
        judge_user = f"{user_message}\n\n---\nPROSECUTOR:\n{prosecutor_arg}\n\n---\nDEFENSE:\n{defense_arg}\n\nNow, render your final verdict as JSON."

        raw = await _ollama_chat_json(judge_sys, judge_user)
    except Exception as e:
        print(f"[Classifier] Ollama error (multi-agent): {e}")
        return _keyword_only_classification(
            km,
            document_url=url,
            document_title=title,
        )

    if (
        config.LLM_GUIDED_RETRY_ON_MISS
        and not _result_has_matched_evil(raw)
        and _detectors_suggest_evil(km, text, title, url)
    ):
        retry_user = (
            judge_user
            + "\n\n---\n"
            + _format_detector_hints(km, text, title, url)
            + "\n\nYou MUST return at least one matched:true entry if any named malicious AI or clearly described harmful AI product appears in the document or detector hints."
        )
        retry_system = judge_sys + "\n\nThis is a SECOND PASS because the first pass found no matched systems despite detector signals. Prefer extracting real product names (crime LLMs, surveillance tools, etc.)."
        try:
            raw_retry = await _ollama_chat_json(retry_system, retry_user)
            if _result_has_matched_evil(raw_retry):
                raw = raw_retry
        except Exception as e:
            print(f"[Classifier] Guided retry failed: {e}")

    try:
        raw = await _maybe_refine_with_web_search(raw, text, title, url)
    except Exception as e:
        print(f"[Classifier] Web refine orchestration failed: {e}")

    # If the model still reports no matched evil AI, use detector-driven keyword/name fallback
    # so obvious cases (e.g. FraudGPT) are never dropped when text actually mentions them.
    if not _result_has_matched_evil(raw):
        merged = _merge_keyword_and_name_matches(km, text, title=title, url=url)
        if merged and _detectors_suggest_evil(merged, text, title, url):
            fb = _keyword_only_classification(
                merged,
                document_url=url,
                document_title=title,
            )
            if _result_has_matched_evil(fb):
                print(
                    "[Classifier] Using keyword/name fallback — LLM returned no matched evil-AI rows "
                    "but detectors found known-name or keyword signals."
                )
                return fb

    result = normalize_classifications_result(
        raw,
        document_url=url,
        document_title=title,
    )

    # Stage 5: Confidence reconciliation — blend Shiv pre-score with LLM confidence
    if pre_score and result.get("classifications"):
        for cls in result["classifications"]:
            llm_conf = cls.get("confidence", 0.0)
            pre_conf = pre_score.confidence
            # Weighted blend: LLM gets more weight but pre-score stabilizes
            reconciled = (0.70 * llm_conf) + (0.30 * pre_conf)
            cls["confidence"] = max(0.0, min(1.0, reconciled))
            # Attach signal debug data
            cls["_signal_debug"] = {
                "pre_score_code": pre_score.final_code,
                "pre_score_confidence": pre_conf,
                "pre_score_signals": pre_score.signal_scores,
                "ambiguous_codes": pre_score.ambiguous_codes,
                "gray_area": pre_score.gray_area,
            }

    if relevance and result.get("classifications"):
        for cls in result["classifications"]:
            cls["_relevance_score"] = relevance.get("score", 0.0)
            cls["_relevance_reasons"] = relevance.get("reasons", [])

    return result


def _keyword_only_classification(
    keyword_matches: dict,
    *,
    document_url: str = "",
    document_title: str = "",
    pre_score=None,
    relevance=None,
) -> dict:
    """Fallback classification using only keyword matches when LLM is unavailable.
    Optionally boosted by Shiv pre-score signals.
    """
    classifications = []
    for cat_id, match_data in keyword_matches.items():
        confidence = min(0.3 + (match_data["count"] * 0.08), 0.65)
        # Boost from Shiv pre-score if available and codes match
        if pre_score and pre_score.final_code == cat_id:
            confidence = max(confidence, pre_score.confidence * 0.8)
        hits_preview = ", ".join(match_data["hits"][:8])
        named_hit = None
        for h in match_data["hits"]:
            if h.lower() in KNOWN_EVIL_AI_NAMES:
                named_hit = h
                break
        entry = {
            "category_id": cat_id,
            "category_name": match_data["name"],
            "matched": True,
            "confidence": confidence,
            "name_clarity": "named_product" if named_hit else "unknown",
            "evidence_quotes": [],
            "criteria_scores": {kw: "PARTIAL" for kw in match_data["hits"][:5]},
            "reasoning": f"Keyword / name signal: {hits_preview}",
            "ai_system_name": named_hit,
            "developer_org": None,
            "abuse_description": (
                f"The document matches indicators for {match_data['name']}: {hits_preview}."
            ),
            "criminal_or_controversial": None,
            "descriptive_category": None,
            "tool_website_url": None,
            "public_tagline": None,
            "stated_use_case": None,
            "target_victim": None,
            "primary_output": None,
            "harm_category": None,
            "gate_1": None,
            "gate_2": None,
            "gate_3": None,
            "exclusion_1": None,
            "exclusion_2": None,
            "exclusion_3": None,
            "include_in_repo": None,
            "evidence_summary": None,
        }
        row = normalize_classification_rubric(
            entry,
            document_url=document_url,
            document_title=document_title,
        )
        apply_confidence_adjustments(row)
        classifications.append(row)

    overall_conf = max((c["confidence"] for c in classifications), default=0.0)
    return {
        "classifications": classifications,
        "overall_confidence": overall_conf,
        "is_evil_ai": len(classifications) > 0,
    }


def apply_confidence_gate(confidence: float, category_id: str) -> str:
    """Determine status based on confidence and category."""
    if category_id in GRAY_AREA_SUBCATEGORIES:
        return "gray_area"
    if category_id in UNDECIDED_CRITERIA:
        return "pending_criteria"
    if confidence >= config.CONFIDENCE_CONFIRMED:
        return "confirmed"
    if confidence >= config.CONFIDENCE_REJECTED:
        return "contested"
    return "rejected"
