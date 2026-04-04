"""Classification pipeline — keyword filter + Ollama LLM classification."""
import json
import re
import httpx
from typing import Any, Optional
from backend.config import config
from backend.pipeline.examples_csv import format_examples_for_prompt, merge_known_names

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
    out["classifications"] = [
        normalize_classification_rubric(dict(c), document_url=document_url, document_title=document_title)
        for c in result["classifications"]
    ]
    return out


def keyword_filter(text: str) -> dict:
    """
    Run keyword filtering against all subcategories.
    Returns dict of matched subcategories with their hit counts.
    """
    text_lower = text.lower()
    matches = {}

    for cat_id, cat_data in KEYWORD_DICTIONARY.items():
        hits = []
        for keyword in cat_data["keywords"]:
            if keyword.lower() in text_lower:
                hits.append(keyword)
        if len(hits) >= 2:  # Need at least 2 keyword hits
            matches[cat_id] = {
                "name": cat_data["name"],
                "hits": hits,
                "count": len(hits),
            }

    return matches


def name_match_filter(text: str, url: str = "", title: str = "") -> dict:
    """Detect known evil AI system names in text, URL, or title.
    Returns matches in the same format as keyword_filter so results can be merged."""
    combined = f"{url} {title} {text}".lower()
    matches: dict = {}

    for name, cat_id in KNOWN_EVIL_AI_NAMES.items():
        if name in combined:
            cat_data = KEYWORD_DICTIONARY.get(cat_id, {})
            cat_name = cat_data.get("name", cat_id)
            if cat_id not in matches:
                matches[cat_id] = {
                    "name": cat_name,
                    "hits": [name],
                    "count": 1,
                }
            else:
                matches[cat_id]["hits"].append(name)
                matches[cat_id]["count"] += 1

    return matches


async def classify_with_ollama(
    text: str,
    title: str = "",
    url: str = "",
    keyword_matches: dict = None,
) -> Optional[dict]:
    """
    Send document to Ollama for LLM rubric classification.
    Returns structured classification result or None on failure.
    """
    if not config.USE_LLM:
        return _keyword_only_classification(
            keyword_matches or {},
            document_url=url,
            document_title=title,
        )

    # Load guidelines
    guidelines_text = ""
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

MULTI-ENTITY RULE: If the document describes MULTIPLE distinct AI systems, create a
SEPARATE entry for EACH one, even under the same subcategory.

For each AI system found, fill in ALL of the following fields:
- category_id: subcategory code (e.g. "1A", "4A")
- category_name: subcategory name from guidelines
- matched: true if evidence supports classification
- confidence: float 0.0-1.0
- ai_system_name: the tool/system name (REQUIRED)
- criminal_or_controversial: "Criminal AI" if designed for harm, or "Controversial Institutional AI" if not designed to harm but critics say it can cause harm
- descriptive_category: a short label like "Cybercrime AI Tool", "Mass Surveillance AI", "Synthetic Media Abuse AI", "Predictive Policing AI", "Kinetic Risk AI", "Synthetic Influence Operations", etc.
- tool_website_url: direct URL to the tool's website (if known, else "N/A")
- developer_org: who made it (company or person, "Unknown" if not known)
- public_tagline: what it claims to do (short phrase, "N/A" if none)
- stated_use_case: what it is designed/used for (1-2 sentences)
- target_victim: who is harmed
- primary_output: what the tool produces
- harm_category: type of harm (e.g. "Phishing / Malware Enablement", "Mass Biometric Surveillance")
- gate_1: "Y" or "N" — Intentionally designed, marketed, or deployed for harm
- gate_2: "Y" or "N" — Harm is the product, not a side effect
- gate_3: "Y" or "N" — Evidence strong enough for near universal consensus
- exclusion_1: "Y" or "N" — Accidental harm only
- exclusion_2: "Y" or "N" — Dual use with unclear intent
- exclusion_3: "Y" or "N" — Grey zone only, not explicitly exploitative
- include_in_repo: "Y" only if gate_1-3 are all "Y" AND exclusion_1-3 are all "N", otherwise "N"
- evidence_summary: 1 sentence summarizing the evidence
- reasoning: 1 sentence assessment
- abuse_description: 1-2 sentence harm summary

Return ONLY valid JSON:
{{
  "classifications": [
    {{
      "category_id": "4A",
      "category_name": "Automated Cyberattack Tools",
      "matched": true,
      "confidence": 0.85,
      "ai_system_name": "FraudGPT",
      "criminal_or_controversial": "Criminal AI",
      "descriptive_category": "Cybercrime AI Tool",
      "tool_website_url": "https://fraudgpt.org",
      "developer_org": "Unknown",
      "public_tagline": "Unrestricted AI Without Limitations",
      "stated_use_case": "Generate uncensored answers without ethical restrictions or content filtering",
      "target_victim": "Individuals and organizations targeted by phishing, scams, and cyber fraud",
      "primary_output": "Phishing emails, scam scripts, malware assistance, fraudulent documents",
      "harm_category": "Automated Social Engineering / Cyber Fraud",
      "gate_1": "Y",
      "gate_2": "Y",
      "gate_3": "Y",
      "exclusion_1": "N",
      "exclusion_2": "N",
      "exclusion_3": "N",
      "include_in_repo": "Y",
      "evidence_summary": "FraudGPT is an AI chatbot advertised on dark-web forums and Telegram that generates phishing emails, malware, and scam content for cybercriminals.",
      "reasoning": "FraudGPT is a malicious LLM designed for phishing and fraud.",
      "abuse_description": "AI chatbot sold on dark web for generating phishing emails and malware."
    }}
  ],
  "overall_confidence": 0.85,
  "is_evil_ai": true
}}

If NO evil AI system is found: {{"classifications": [], "overall_confidence": 0.0, "is_evil_ai": false}}

MANDATORY: In every object inside "classifications", include every field listed above with a string value.
Use "N/A", "Unknown", or "Not specified in extraction" when information is missing — never omit a key.

Return ONLY valid JSON. No preamble or explanation outside the JSON."""

    user_message = f"Document Title: {title}\nSource URL: {url}\n\nDocument Content:\n{text[:6000]}"

    try:
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

            # Parse JSON response
            result = json.loads(content)
            return normalize_classifications_result(
                result,
                document_url=url,
                document_title=title,
            )

    except json.JSONDecodeError as e:
        print(f"[Classifier] JSON parse error: {e}")
        # Try to extract JSON from response
        try:
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                parsed = json.loads(json_match.group())
                return normalize_classifications_result(
                    parsed,
                    document_url=url,
                    document_title=title,
                )
        except Exception:
            pass
        return _keyword_only_classification(
            keyword_matches or {},
            document_url=url,
            document_title=title,
        )

    except Exception as e:
        print(f"[Classifier] Ollama error: {e}")
        return _keyword_only_classification(
            keyword_matches or {},
            document_url=url,
            document_title=title,
        )


def _keyword_only_classification(
    keyword_matches: dict,
    *,
    document_url: str = "",
    document_title: str = "",
) -> dict:
    """Fallback classification using only keyword matches when LLM is unavailable."""
    classifications = []
    for cat_id, match_data in keyword_matches.items():
        confidence = min(0.3 + (match_data["count"] * 0.08), 0.65)
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
        classifications.append(
            normalize_classification_rubric(
                entry,
                document_url=document_url,
                document_title=document_title,
            )
        )

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
