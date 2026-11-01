import os
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure root dir is in path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Create temporary SQLite DB for testing
TEMP_DIR = tempfile.mkdtemp()
TEST_DB_PATH = Path(TEMP_DIR) / "pytest_shared.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["ENV"] = "development"
os.environ["DEV_MODE"] = "true"
os.environ["DATA_ENCRYPTION_KEY"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
os.environ["JWT_SECRET"] = "test_jwt_secret_pytest"

from app import database as db
db.set_engine_url(f"sqlite:///{TEST_DB_PATH}")
db.init_db()

@pytest.fixture(autouse=True)
def setup_test_db():
    db.init_db()
    # Create default verified test user (id=1) for mock/unit tests using user_id=1
    with db.get_db_session() as session:
        u1 = session.get(db.User, 1)
        if not u1:
            u1 = db.User(
                id=1,
                email="default_test_user_1@sinbha.local",
                password_hash=db.hash_password("Password123!"),
                is_verified=True,
                created_at=db.utc_now()
            )
            session.add(u1)
            try:
                session.commit()
            except Exception:
                session.rollback()
    yield

