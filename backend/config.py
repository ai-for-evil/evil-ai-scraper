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
    SCRAPE_USER_AGENT: str = os.getenv(
        "SCRAPE_USER_AGENT", "AIForEvilResearchBot/1.0"
    )

    # Classification thresholds
    SEMANTIC_THRESHOLD: float = float(os.getenv("SEMANTIC_THRESHOLD", "0.45"))
    CONFIDENCE_CONFIRMED: float = float(
        os.getenv("CONFIDENCE_CONFIRMED_THRESHOLD", "0.70")
    )
    CONFIDENCE_REJECTED: float = float(
        os.getenv("CONFIDENCE_REJECTED_THRESHOLD", "0.40")
    )
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "6000"))
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


config = Config()
