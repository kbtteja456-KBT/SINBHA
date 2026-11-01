"""
Step 1C Item 1 Test: Production Database Refusal Guard
Verifies that:
1. assert_not_production_test_db raises RuntimeError when passed a production URL or production branch.
2. Safe test database URLs (SQLite, dev branch) are accepted.
"""

import pytest
from app.database import assert_not_production_test_db, is_production_database_url


def test_production_url_detection():
    # Production Neon endpoint
    prod_url = "postgresql://neondb_owner:dummy@ep-royal-rain-b3d5qpa9.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    assert is_production_database_url(prod_url) is True

    # Dev branch endpoint
    dev_url = "postgresql://neondb_owner:dummy@ep-weather-mist-12345.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    assert is_production_database_url(dev_url) is False

    # SQLite
    sqlite_url = "sqlite:///pytest_shared.db"
    assert is_production_database_url(sqlite_url) is False


def test_refuse_test_execution_on_production_url():
    prod_url = "postgresql://neondb_owner:dummy@ep-royal-rain-b3d5qpa9.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    with pytest.raises(RuntimeError) as exc_info:
        assert_not_production_test_db(prod_url)
    assert "CRITICAL SAFETY GUARD VIOLATION" in str(exc_info.value)
    assert "PRODUCTION" in str(exc_info.value)


def test_refuse_test_execution_on_production_neon_branch(monkeypatch):
    monkeypatch.setenv("NEON_BRANCH", "production")
    with pytest.raises(RuntimeError) as exc_info:
        assert_not_production_test_db("postgresql://neondb_owner:dummy@ep-dev-test.aws.neon.tech/neondb")
    assert "CRITICAL SAFETY GUARD VIOLATION" in str(exc_info.value)


def test_allow_safe_sqlite_or_dev_db(monkeypatch):
    monkeypatch.setenv("NEON_BRANCH", "dev")
    # Should not raise
    assert_not_production_test_db("sqlite:///pytest_test.db")
    assert_not_production_test_db("postgresql://neondb_owner:dummy@ep-dev-test.aws.neon.tech/neondb")
