"""SQLAlchemy database models."""
import datetime
import json
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, JSON, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from backend.config import config

Base = declarative_base()


class Run(Base):
    """A single scrape run."""
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), default="pending")  # pending, running, completed, failed
    run_type = Column(String(16), default="source")  # "url" or "source"
    input_url = Column(Text, nullable=True)  # for URL runs
    sources = Column(Text, nullable=True)  # JSON list of source names for source runs
    total_documents = Column(Integer, default=0)
    evil_found = Column(Integer, default=0)
    confirmed_count = Column(Integer, default=0)
    contested_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    avg_confidence = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    reviewer_name = Column(String(128), nullable=True)

    documents = relationship("Document", back_populates="run", cascade="all, delete-orphan")

    @property
    def sources_list(self):
        if self.sources:
            return json.loads(self.sources)
        return []

    @sources_list.setter
    def sources_list(self, value):
        self.sources = json.dumps(value)


class Document(Base):
    """A scraped document."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=True)
    source_name = Column(String(64), nullable=True)  # arxiv, github, etc.
    document_type = Column(String(32), nullable=True)  # paper, news, repo, patent, product
    raw_text = Column(Text, nullable=True)
    cleaned_text = Column(Text, nullable=True)
    scraped_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Keyword filter results
    keyword_matched = Column(Boolean, default=False)
    keyword_categories = Column(Text, nullable=True)  # JSON list

    run = relationship("Run", back_populates="documents")
    classifications = relationship("Classification", back_populates="document", cascade="all, delete-orphan")


class Classification(Base):
    """LLM classification result for a document."""
    __tablename__ = "classifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(String(8), nullable=False)  # e.g. "1A", "3B"
    category_name = Column(String(128), nullable=True)
    matched = Column(Boolean, default=False)
    confidence = Column(Float, default=0.0)
    status = Column(String(32), default="pending")  # confirmed, contested, rejected, gray_area, pending_criteria
    reasoning = Column(Text, nullable=True)
    criteria_scores = Column(Text, nullable=True)  # JSON dict
    ai_system_name = Column(String(256), nullable=True)
    developer_org = Column(String(256), nullable=True)
    abuse_description = Column(Text, nullable=True)
    evidence_quotes = Column(Text, nullable=True)  # JSON list
    classified_at = Column(DateTime, default=datetime.datetime.utcnow)
    guidelines_version = Column(Integer, default=1)
    is_gray_area = Column(Boolean, default=False)

    # Full rubric fields (matching examples.csv structure)
    criminal_or_controversial = Column(String(64), nullable=True)
    descriptive_category = Column(String(128), nullable=True)
    tool_website_url = Column(Text, nullable=True)
    public_tagline = Column(Text, nullable=True)
    stated_use_case = Column(Text, nullable=True)
    target_victim = Column(Text, nullable=True)
    primary_output = Column(Text, nullable=True)
    harm_category = Column(String(128), nullable=True)
    gate_1 = Column(String(1), nullable=True)
    gate_2 = Column(String(1), nullable=True)
    gate_3 = Column(String(1), nullable=True)
    exclusion_1 = Column(String(1), nullable=True)
    exclusion_2 = Column(String(1), nullable=True)
    exclusion_3 = Column(String(1), nullable=True)
    include_in_repo = Column(String(1), nullable=True)
    evidence_summary = Column(Text, nullable=True)

    document = relationship("Document", back_populates="classifications")


# ---------- Engine & Session ----------

def _ensure_data_dir():
    """Make sure the data/ directory exists."""
    import os
    from pathlib import Path
    data_dir = Path(config.DATABASE_URL.replace("sqlite:///", "")).parent
    os.makedirs(data_dir, exist_ok=True)


def get_engine():
    _ensure_data_dir()
    return create_engine(config.DATABASE_URL, echo=False)


def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine)


def init_db():
    """Create all tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine
