"""
Regression test for Version Source of Truth consistency.
Ensures /api/health and get_app_version() strictly match package.json (1.4.28)
and never regress to arbitrary hardcoded strings like 1.0.0.
"""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.version import get_app_version


def test_api_health_version_matches_package_json():
    # Read package.json version
    pkg_path = Path(__file__).resolve().parent.parent / "package.json"
    assert pkg_path.exists(), "package.json not found"
    with open(pkg_path, "r", encoding="utf-8") as f:
        pkg_data = json.load(f)
    expected_version = pkg_data.get("version")
    assert expected_version == "1.4.31"

    # Verify get_app_version() helper matches
    assert get_app_version() == expected_version

    # Verify /api/health endpoint returns expected version
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "version" in data
    assert data["version"] == expected_version, f"Expected {expected_version}, got {data['version']}"

