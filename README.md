# AI for Evil — Scouting Pipeline

> An automated research pipeline for identifying AI systems that meet evidence-based criteria
> for harmful deployment, developed by **MIT Critical Data**.

---

## What This Is

AI systems are increasingly deployed in ways that cause measurable harm — from synthetic
media used for impersonation, to surveillance systems that suppress dissent, to algorithms
optimized to maximize financial extraction from vulnerable populations.

This project builds an automated scouting pipeline that continuously monitors trusted
public sources, filters and classifies content against a structured harm rubric, and
surfaces documented findings for expert human review. The goal is to build an evidence-based,
living registry of AI deployments that qualify as harmful under our classification guidelines.

The classification framework is organized around 5 harm categories, each with specific,
auditable criteria. Because the field is moving fast and our own guidelines are still
being refined, the system is designed from the ground up to support versioned rules and
retroactive re-scoring.

---

## Classification Categories

| # | Category | Subcategories |
|---|---|---|
| 1 | **Information & Perception Manipulation** | Automated disinformation · Synthetic media deception · Narrative amplification |
| 2 | **Exploitation & Manipulation** | Predatory targeting · Addiction optimization · Financial extraction |
| 3 | **Surveillance & Control** | Mass surveillance · Predictive suppression · Social scoring |
| 4 | **Cyber & Infrastructure Harm** | Automated cyberattack tools · Infrastructure disruption · Autonomous weaponization |
| 5 | **Institutional & Structural Manipulation** | Metric gaming · Market manipulation · Accountability evasion |

Each subcategory has explicit criteria scored as **MET / PARTIAL / NOT MET**. Several
subcategories are designated **gray areas** (Addiction Optimization, Market Manipulation)
and always route to human review. Two subcategories (Social Scoring 3C, Metric Gaming 5A)
have criteria still under deliberation — items matching these are held pending finalization.

Full guidelines live in [`config/guidelines_v1.md`](config/guidelines_v1.md).

---

## Pipeline Overview

The pipeline runs in 8 stages. Stages 3a and 3b execute in parallel.

```mermaid
flowchart TD
    A["Stage 1 — Web Collection\narXiv · GitHub · HuggingFace · NewsAPI · EU AI Act · Patents"]
    B["Stage 2 — Clean & Preprocess\nStrip HTML · deduplicate · tokenize · chunk"]
    C["Stage 3a — Keyword Filter\nPer-category term clusters · proximity rules"]
    D["Stage 3b — Semantic Scoring\nsentence-transformers · cosine similarity · threshold gate"]
    E{"Pass 3a OR 3b?"}
    F["Stage 4 — Entity & Evidence Extraction\nAI system name · org · abuse description · evidence quotes"]
    G["Stage 5 — LLM Rubric Classification\nGuidelines as system prompt · per-criterion scoring\nOutput: category · scores · confidence · reasoning"]
    H{"Confidence gate"}
    I["✓ Confirmed\n≥ 0.70"]
    J["⚠ Contested / Gray Area\n0.40 – 0.69 · human review"]
    K["✗ Rejected\n< 0.40"]
    L["Stage 7 — LLM Documentation\nStructured finding report · criteria table · evidence · source"]
    M["Stage 8 — Storage & Review UI\nPostgreSQL · versioned guidelines · Streamlit dashboard"]
    N["🔄 Re-score on\nguidelines update"]

    A --> B
    B --> C & D
    C --> E
    D --> E
    E -- yes --> F
    E -- no --> M
    F --> G
    G --> H
    H --> I & J & K
    I --> L
    J --> L
    K --> N
    N --> G
    L --> M
```

---

## Stage-by-Stage Breakdown

### Stage 1 — Web Collection

Scrapes raw content from trusted, high-signal sources using official APIs wherever available
and `scrapy` / `playwright` for structured and JS-heavy crawls respectively.

**Sources:**
- `arxiv.org` — AI research papers (arXiv API)
- `github.com` — repository READMEs, model cards, release notes
- `huggingface.co` — model and dataset cards (HuggingFace Hub API)
- NewsAPI / GDELT — news articles mentioning AI deployments
- EU AI Act public submissions and regulatory filings
- Patent databases (Google Patents, USPTO)
- Company product pages and press releases (manually curated crawl list)

Each document is stored with: `url`, `source_name`, `scraped_at`, `raw_text`,
and `document_type` (paper / news / repo / patent / product).

---

### Stage 2 — Clean & Preprocess

Transforms raw scraped content into clean, normalized text ready for filtering.

1. Strip HTML, boilerplate, and ads (`trafilatura` / `newspaper3k`)
2. Normalize Unicode (NFC); decode character encodings
3. Deduplicate via SHA-256 hash of cleaned body text
4. Sentence-tokenize using `spaCy` (`en_core_web_trf`)
5. Chunk into overlapping 512-token windows for embedding
6. Retain full cleaned document for LLM stages

---

### Stage 3a — Keyword & Proximity Filtering

Fast, cheap first-pass filter. A version-controlled JSON dictionary maps each
subcategory to a cluster of indicator terms. A document passes if any cluster
has ≥ 2 term hits within a 200-token window (proximity rule).

```json
{
  "1A_disinformation": ["synthetic media", "deepfake", "fabricated content", "LLM-generated news"],
  "1B_synthetic_media": ["voice cloning", "face swap", "impersonation", "GAN"],
  "3A_mass_surveillance": ["biometric tracking", "facial recognition at scale", "population monitoring"]
}
```

---

### Stage 3b — Semantic Scoring *(parallel with 3a)*

Catches documents that describe harmful AI obliquely — without using obvious keywords.

- Model: `sentence-transformers/all-mpnet-base-v2`
- Category descriptions from the guidelines are pre-embedded and cached
- Each document chunk is scored via cosine similarity against all category embeddings
- Default threshold: `0.45` (tunable via env var; calibrate on labeled examples before production)

**Combined pass condition:** a document advances if it passes **3a OR 3b**.
This maximizes recall; precision is recovered downstream by the LLM and human review.

---

### Stage 4 — Entity & Evidence Extraction

Extracts structured signals before the expensive LLM call, keeping prompts focused
and token cost low.

**Extracted fields:**

```json
{
  "doc_id": "uuid",
  "ai_system_name": "string | null",
  "developer_org": "string | null",
  "abuse_description": "1–3 sentence summary of harmful behavior",
  "evidence_quotes": ["up to 3 verbatim supporting sentences"],
  "geo_context": "string | null",
  "top_semantic_category": "string",
  "semantic_score": 0.0
}
```

---

### Stage 5 — LLM Rubric Classification

The core classification step. The full guidelines document is passed as the system prompt.
The LLM scores each subcategory against its explicit criteria.

**Model:** `claude-sonnet-4-20250514` via Anthropic API
(escalate to Opus for low-confidence cases if budget allows)

**Output per subcategory:**

```json
{
  "category": "1A_automated_disinformation",
  "matched": true,
  "confidence": 0.85,
  "criteria_scores": {
    "intentionally_fabricated": "MET",
    "automation_increases_distribution": "MET",
    "designed_to_influence_opinion": "PARTIAL"
  },
  "reasoning": "System generates fabricated news at scale with no fact-checking layer."
}
```

Subcategories with undecided criteria are flagged `requires_criteria_update: true`
and held in `pending_criteria` status regardless of confidence.

---

### Stage 6 — Confidence Gate

| Confidence | Status | Action |
|---|---|---|
| ≥ 0.70 | `confirmed` | Auto-advance to Stage 7 |
| 0.40 – 0.69 | `contested` | Queue for human review; advance after approval |
| < 0.40 | `rejected` | Stored; available for re-scoring |
| Gray area subcategory | `gray_area` | Always human review, regardless of confidence |
| Undecided criteria matched | `pending_criteria` | Held until guidelines updated; auto re-scored on next version |

---

### Stage 7 — LLM Documentation Generation

Generates a structured, human-readable finding report for each confirmed or approved item.

Each report includes: finding title · system summary · harm classification · criteria table ·
supporting evidence with source URL · confidence score · gray area note (if applicable) ·
guidelines version used.

Reports are stored as Markdown, linked to their source document.

---

### Stage 8 — Storage & Review UI

**Database:** PostgreSQL with versioned classifications

**Core tables:** `documents` · `filtered_docs` · `extracted_entities` · `classifications`
· `findings` · `review_log` · `guidelines`

**Streamlit Review Dashboard:**
- Findings by category, status, and date
- Full finding report + original source side-by-side
- Reviewer controls: approve · reject · flag for re-review · add notes
- Export to CSV or JSON
- Filter by category, confidence range, source type, date, guidelines version

**Orchestration:** Prefect — daily scrape runs; classification jobs trigger on batch completion.

**Guidelines versioning:** All classifications reference a `guidelines_version` foreign key.
Incrementing the version automatically queues `pending_criteria` and `rejected` items
for re-scoring.

---

## Tech Stack

| Component | Tool |
|---|---|
| Web scraping (structured) | `scrapy` |
| Web scraping (JS-heavy) | `playwright` |
| Article extraction | `trafilatura` / `newspaper3k` |
| Text preprocessing | `spaCy` (`en_core_web_trf`) |
| Semantic embeddings | `sentence-transformers` (`all-mpnet-base-v2`) |
| NER / entity extraction | `spaCy` + custom entity ruler |
| LLM classification & docs | Anthropic API — `claude-sonnet-4-20250514` |
| Database | PostgreSQL + SQLAlchemy |
| Pipeline orchestration | Prefect |
| Review UI | Streamlit |
| Containerization | Docker + docker-compose |
| Testing | pytest |

---

## Repository Structure

```
ai-for-evil-scout/
├── README.md
├── CONTEXT.md                    # Full technical spec for contributors and AI builders
├── docker-compose.yml
├── .env.example
│
├── config/
│   ├── sources.json              # Trusted source list + scrape configs
│   ├── keywords_v1.json          # Keyword clusters per subcategory (versioned)
│   └── guidelines_v1.md          # Classification guidelines (versioned)
│
├── pipeline/
│   ├── stage1_collection/
│   │   ├── scrapy_spiders/
│   │   └── api_collectors/       # arXiv, HuggingFace, NewsAPI clients
│   ├── stage2_preprocess/
│   ├── stage3_filter/
│   │   ├── keyword_filter.py
│   │   └── semantic_scorer.py
│   ├── stage4_extraction/
│   ├── stage5_classification/
│   │   └── prompts/
│   │       ├── system_prompt.txt
│   │       └── user_prompt_template.txt
│   ├── stage6_confidence_gate/
│   ├── stage7_documentation/
│   └── stage8_storage/
│       ├── models.py
│       └── migrations/
│
├── review_ui/
│   └── app.py
│
├── orchestration/
│   └── flows.py
│
└── tests/
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker & docker-compose
- PostgreSQL 15+
- An [Anthropic API key](https://console.anthropic.com/)
- A [NewsAPI key](https://newsapi.org/) (optional but recommended)

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/ai-for-evil-scout.git
cd ai-for-evil-scout

# Copy and fill in environment variables
cp .env.example .env

# Start the database
docker-compose up -d db

# Install dependencies
pip install -r requirements.txt

# Run database migrations
python pipeline/stage8_storage/migrations/apply.py

# Run the full pipeline
python orchestration/flows.py
```

### Running the Review UI

```bash
streamlit run review_ui/app.py
```

---

## Configuration

All tunable parameters are exposed as environment variables. Copy `.env.example` to `.env`
and configure before running.

```env
# Anthropic
ANTHROPIC_API_KEY=

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/ai_for_evil

# NewsAPI
NEWS_API_KEY=

# Scraping
SCRAPE_DELAY_SECONDS=2
SCRAPE_USER_AGENT=AIForEvilResearchBot/1.0

# Classification thresholds (research parameters — tune empirically)
SEMANTIC_THRESHOLD=0.45
CONFIDENCE_CONFIRMED_THRESHOLD=0.70
CONFIDENCE_REJECTED_THRESHOLD=0.40

# LLM
LLM_MODEL=claude-sonnet-4-20250514
LLM_MAX_TOKENS=2000

# Guidelines version (increment when guidelines are updated)
GUIDELINES_VERSION=1

# Orchestration
PREFECT_API_URL=
```

---

## Classification Guidelines Status

| ID | Subcategory | Gray Area | Criteria Finalized |
|---|---|:---:|:---:|
| 1A | Automated disinformation | — | ✅ |
| 1B | Synthetic media deception | — | ✅ |
| 1C | Narrative amplification engines | — | ✅ |
| 2A | Predatory targeting systems | — | ✅ *(vulnerable def. TBD)* |
| 2B | Addiction optimization | ⚠️ likely removed | ✅ |
| 2C | Financial extraction algorithms | — | ✅ |
| 3A | Mass surveillance systems | — | ✅ |
| 3B | Predictive suppression systems | — | ✅ |
| 3C | Social scoring mechanisms | — | ❌ undecided |
| 4A | Automated cyberattack tools | — | ✅ |
| 4B | Infrastructure disruption systems | — | ✅ |
| 4C | Autonomous weaponization | — | ✅ |
| 5A | Metric gaming systems | — | ❌ undecided |
| 5B | Market manipulation systems | ⚠️ likely removed | ✅ |
| 5C | Accountability evasion systems | — | ✅ |

Guidelines are version-controlled. Any update increments the version and triggers automatic
re-scoring of all held and rejected items against the new criteria.

---

## Research Context

This pipeline was developed as part of the **"AI for Evil"** initiative at
**MIT Critical Data**. The classification framework is
preliminary and will be amended as the project progresses. The goal is to produce a
rigorous, evidence-based, and publicly auditable record of harmful AI deployments.

For questions about the research, contact the MIT Critical Data team.

---

## License

See [`LICENSE`](LICENSE) for details.
