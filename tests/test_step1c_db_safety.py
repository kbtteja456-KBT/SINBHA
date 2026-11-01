"""
Step 1C Item 1 & Item 6 Test Suite: Database & Production Environment Safety
Validates:
1. is_production_database_url correctly detects production databases and branches.
2. Tests and local dev refuse to run against production database.
3. validate_production_config rejects APP_URL pointing to localhost/127.0.0.1 in production.
"""

import os
import pytest
from app.security import is_production_database_url, validate_production_config
from app import database as db


def test_production_database_url_detection(monkeypatch):
    # 1. Neon production endpoint detection
    prod_url = "postgresql://neondb_owner:secret@ep-royal-rain-b3d5qpa9.aws.neon.tech/neondb?sslmode=require"
    assert is_production_database_url(prod_url) is True

    # 2. NEON_BRANCH=production detection
    monkeypatch.setenv("NEON_BRANCH", "production")
    any_neon_url = "postgresql://user:pass@ep-branch-xyz.neon.tech/neondb"
    assert is_production_database_url(any_neon_url) is True

    # 3. Safe dev branch detection
    monkeypatch.setenv("NEON_BRANCH", "dev")
    dev_url = "postgresql://user:pass@ep-dev-branch-xyz.c-4.aws.neon.tech/neondb?sslmode=require"
    assert is_production_database_url(dev_url) is False

    # 4. Safe SQLite test database
    assert is_production_database_url("sqlite:///:memory:") is False
    assert is_production_database_url("sqlite:///tmp/test.db") is False


def test_set_engine_refuses_production_url_in_tests():
    prod_url = "postgresql://user:pass@ep-royal-rain-b3d5qpa9.aws.neon.tech/neondb?sslmode=require"
    with pytest.raises(RuntimeError) as exc_info:
        db.set_engine_url(prod_url)
    assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)
    assert "Attempted to connect to production database" in str(exc_info.value)


def test_validate_production_config_rejects_localhost_app_url(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_valid_prod_key_test_123456789")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db?sslmode=require")

    # Localhost APP_URL must be rejected in production
    monkeypatch.setenv("APP_URL", "http://localhost:8080")
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_config()
    assert "APP_URL cannot point to localhost" in str(exc_info.value)

    # 127.0.0.1 APP_URL must be rejected in production
    monkeypatch.setenv("APP_URL", "http://127.0.0.1:8080")
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_config()
    assert "APP_URL cannot point to localhost" in str(exc_info.value)

    # Valid public domain APP_URL succeeds
    monkeypatch.setenv("APP_URL", "https://sinbha-backend.onrender.com")
    # Should not raise
    validate_production_config()
