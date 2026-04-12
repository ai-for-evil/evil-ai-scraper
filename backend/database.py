"""Database session helpers."""
import sqlite3
from contextlib import contextmanager
from backend.models import get_session_factory, init_db, Base
from backend.config import config


SessionFactory = None


def _migrate_missing_columns():
    """Add any columns defined in models but missing from the SQLite schema."""
    db_path = config.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for table in Base.metadata.sorted_tables:
        cursor.execute(f"PRAGMA table_info({table.name})")
        existing = {row[1] for row in cursor.fetchall()}
        for col in table.columns:
            if col.name not in existing:
                type_str = "TEXT"
                type_name = type(col.type).__name__.upper()
                if "INT" in type_name:
                    type_str = "INTEGER"
                elif "FLOAT" in type_name or "REAL" in type_name:
                    type_str = "REAL"
                elif "BOOL" in type_name:
                    type_str = "INTEGER"
                elif "VARCHAR" in type_name or "STRING" in type_name:
                    type_str = "TEXT"
                try:
                    cursor.execute(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {type_str}")
                except Exception:
                    pass

    conn.commit()
    conn.close()


def setup_database():
    """Initialize the database and create session factory."""
    global SessionFactory
    init_db()
    if config.DATABASE_URL.startswith("sqlite"):
        _migrate_missing_columns()
    SessionFactory = get_session_factory()


@contextmanager
def get_db():
    """Yield a database session and auto-close it."""
    if SessionFactory is None:
        setup_database()
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
