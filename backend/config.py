"""Configuration loaded from .env file."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    # Ollama LLM
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    # Database
    DATABASE_URL: str = os.getenv(
        "SQLITE_URL",
        f"sqlite:///{PROJECT_ROOT / 'data' / 'evil_ai.db'}",
    )

    # NewsAPI
    NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")

    # Scraping
    SCRAPE_DELAY_SECONDS: float = float(os.getenv("SCRAPE_DELAY_SECONDS", "2"))
    #: Multiplier applied to delay for secondary requests (e.g. outbound link fetches).
    SCRAPE_DEPTH_DELAY_MULTIPLIER: float = float(os.getenv("SCRAPE_DEPTH_DELAY_MULTIPLIER", "1.5"))
    #: Max extra URLs to fetch per news article (linked pages), capped for safety.
    MAX_OUTBOUND_LINK_FETCHES: int = int(os.getenv("MAX_OUTBOUND_LINK_FETCHES", "5"))
    #: Extra markdown files to pull from each GitHub repo (beyond README priority).
    GITHUB_EXTRA_MD_FILES: int = int(os.getenv("GITHUB_EXTRA_MD_FILES", "6"))

    SCRAPE_USER_AGENT: str = os.getenv(
        "SCRAPE_USER_AGENT", "AIForEvilResearchBot/1.0"
    )

    # Optional web search to resolve tool URLs when the article does not list one
    # WEB_SEARCH_PROVIDER: none | brave | serpapi
    WEB_SEARCH_PROVIDER: str = os.getenv("WEB_SEARCH_PROVIDER", "none").strip().lower()
    BRAVE_SEARCH_API_KEY: str = os.getenv("BRAVE_SEARCH_API_KEY", "")
    SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")

    # Classification thresholds
    SEMANTIC_THRESHOLD: float = float(os.getenv("SEMANTIC_THRESHOLD", "0.45"))
    CONFIDENCE_CONFIRMED: float = float(
        os.getenv("CONFIDENCE_CONFIRMED_THRESHOLD", "0.70")
    )
    CONFIDENCE_REJECTED: float = float(
        os.getenv("CONFIDENCE_REJECTED_THRESHOLD", "0.40")
    )
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "8000"))
    #: Max characters of document text sent to the LLM (head + tail if longer).
    LLM_DOCUMENT_MAX_CHARS: int = int(os.getenv("LLM_DOCUMENT_MAX_CHARS", "20000"))
    #: Max Brave/SerpAPI queries per document when the LLM requests web enrichment.
    LLM_WEB_SEARCH_MAX_QUERIES: int = int(os.getenv("LLM_WEB_SEARCH_MAX_QUERIES", "3"))
    #: Second Ollama call to merge web snippets into the rubric (requires search API keys).
    LLM_REFINE_WITH_SEARCH: bool = os.getenv("LLM_REFINE_WITH_SEARCH", "true").lower() == "true"
    #: If the first pass finds no evil AI but detectors fired, run a focused retry (extra LLM call).
    LLM_GUIDED_RETRY_ON_MISS: bool = os.getenv("LLM_GUIDED_RETRY_ON_MISS", "true").lower() == "true"

    GUIDELINES_VERSION: int = int(os.getenv("GUIDELINES_VERSION", "1"))

    # Feature flags
    USE_LLM: bool = os.getenv("AI_EVIL_USE_LLM", "true").lower() == "true"

    # Guidelines file (default: data/rubric/guidelines.txt)
    GUIDELINES_PATH: Path = PROJECT_ROOT / os.getenv(
        "AI_EVIL_GUIDELINES_PATH",
        "data/rubric/guidelines.txt",
    )

    # Curated few-shot + name hints (see backend/pipeline/examples_csv.py)
    EXAMPLES_CSV_PATH: Path = PROJECT_ROOT / os.getenv(
        "AI_EVIL_EXAMPLES_CSV",
        "data/rubric/examples.csv",
    )
    USE_EXAMPLES_CSV: bool = os.getenv("AI_EVIL_USE_EXAMPLES_CSV", "true").lower() == "true"
    EXAMPLES_PROMPT_MAX_CHARS: int = int(os.getenv("AI_EVIL_EXAMPLES_PROMPT_MAX_CHARS", "6000"))

    # --- Shiv pipeline settings (taxonomy, chunking, relevance, classification) ---

    # Seed data paths (PDF taxonomy + seed CSV)
    SEED_PDF_PATH: Path = PROJECT_ROOT / os.getenv(
        "AI_EVIL_SEED_PDF", "data/seeds/ai_for_evil_guidelines.pdf"
    )
    SEED_CSV_PATH: Path = PROJECT_ROOT / os.getenv(
        "AI_EVIL_SEED_CSV", "data/seeds/classification_guideline.csv"
    )
    SOURCE_CONFIG_PATH: Path = Path(os.getenv(
        "AI_EVIL_SOURCE_CONFIG",
        str(PROJECT_ROOT / "data" / "seeds" / "high_yield_sources.json"),
    ))

    # Chunking
    MAX_CHUNK_CHARS: int = int(os.getenv("AI_EVIL_MAX_CHUNK_CHARS", "1200"))

    # Relevance scoring thresholds
    RELEVANCE_THRESHOLD: float = float(os.getenv("AI_EVIL_RELEVANCE_THRESHOLD", "0.38"))

    # Classification thresholds (Shiv-style, used by hybrid pre-scorer)
    CLASSIFICATION_THRESHOLD: float = float(os.getenv("AI_EVIL_CLASSIFICATION_THRESHOLD", "0.46"))
    REVIEW_CONFIDENCE_THRESHOLD: float = float(os.getenv("AI_EVIL_REVIEW_CONFIDENCE_THRESHOLD", "0.60"))
    HIGH_CONFIDENCE_THRESHOLD: float = float(os.getenv("AI_EVIL_HIGH_CONFIDENCE_THRESHOLD", "0.75"))

    # Processed data directory (for taxonomy cache, clean docs, etc.)
    PROCESSED_DIR: Path = PROJECT_ROOT / "data" / "processed"
    SEEDS_DIR: Path = PROJECT_ROOT / "data" / "seeds"
    OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"


config = Config()
