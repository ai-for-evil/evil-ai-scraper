from backend.config import config
from sqlalchemy import text
from backend.database import get_db

def migrate():
    with get_db() as db:
        try:
            # We execute a raw ALTER TABLE. If it fails, the column likely already exists.
            db.execute(text("ALTER TABLE runs ADD COLUMN user_name VARCHAR(128);"))
            print("Successfully added user_name column.")
        except Exception as e:
            print(f"Migration likely already completed or failed: {e}")

if __name__ == "__main__":
    migrate()
