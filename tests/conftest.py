import os
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure root dir is in path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Step 1C Item 1: Refuse to run tests if initial DATABASE_URL points to production
init_db_url = os.environ.get("DATABASE_URL", "")
init_neon_branch = os.environ.get("NEON_BRANCH", "")
if ("ep-royal-rain-b3d5qpa9" in init_db_url.lower()) or (init_neon_branch.lower() == "production" and "sqlite" not in init_db_url.lower()):
    # Refuse to run if caller explicitly pointed test at production
    raise RuntimeError(
        "CRITICAL SAFETY GUARD VIOLATION: Pytest execution refused!\n"
        "DATABASE_URL or NEON_BRANCH points to PRODUCTION.\n"
        "Tests must ONLY execute against local SQLite or an isolated Neon dev branch."
    )

# Create temporary SQLite DB for testing
TEMP_DIR = tempfile.mkdtemp()
TEST_DB_PATH = Path(TEMP_DIR) / "pytest_shared.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["NEON_BRANCH"] = "test"
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
    yield

