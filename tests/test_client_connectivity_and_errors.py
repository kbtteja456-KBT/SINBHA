import os
import re
import pytest
from starlette.testclient import TestClient
from app.main import app
from app.security import check_endpoint_rate_limits
from starlette.requests import Request
from starlette.datastructures import Headers, URL
from fastapi import HTTPException

client = TestClient(app)


def test_core_endpoints_return_200_without_rate_limit_blocking():
    """
    Validates that /, /api/health, /static/style.css, and /static/script.js
    return HTTP 200 and are never blocked by rate limiting under rapid sequential requests.
    """
    endpoints = ["/", "/api/health", "/static/style.css", "/static/script.js"]
    for ep in endpoints:
        for _ in range(5):
            res = client.get(ep)
            assert res.status_code == 200, f"Endpoint {ep} failed with status {res.status_code}"
            assert len(res.content) > 0, f"Endpoint {ep} returned empty content"


def test_rate_limiter_exempts_static_and_health_endpoints():
    """
    Validates that check_endpoint_rate_limits explicitly exempts /, /api/health,
    /api/app/version-check, and /static/* paths regardless of request volume.
    """
    def make_dummy_request(path: str) -> Request:
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [(b"host", b"localhost"), (b"x-forwarded-for", b"198.51.100.1")],
        }
        return Request(scope)

    # Health check path should never raise 429 even if called 150 times
    for _ in range(150):
        req = make_dummy_request("/api/health")
        check_endpoint_rate_limits(req)

    # Version check path should never raise 429
    for _ in range(150):
        req = make_dummy_request("/api/app/version-check")
        check_endpoint_rate_limits(req)

    # Static CSS path should never raise 429
    for _ in range(150):
        req = make_dummy_request("/static/style.css")
        check_endpoint_rate_limits(req)


def test_waking_recovery_html_structure_and_diagnostics():
    """
    Validates that the waking recovery screen exists in both Electron and Android assets,
    contains the required diagnostic and recovery elements, and contains 0 flower emojis.
    """
    paths_to_check = [
        os.path.join("electron", "waking.html"),
        os.path.join("www", "waking.html"),
        os.path.join("static", "waking.html"),
    ]

    for p in paths_to_check:
        assert os.path.exists(p), f"Missing recovery file: {p}"
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()

        # Zero flower emoji rule
        assert "\U0001F338" not in content, f"Flower emoji found in {p}"

        # Must have recovery & diagnostic UI
        assert 'id="statusText"' in content, f"Missing #statusText in {p}"
        assert 'id="countdown"' in content, f"Missing #countdown in {p}"
        assert 'id="retryBtn"' in content, f"Missing #retryBtn in {p}"
        assert 'id="diagStatus"' in content, f"Missing #diagStatus in {p}"
        assert '429' in content, f"Missing 429 status handling in {p}"
        assert 'checkHealth' in content, f"Missing health check loop in {p}"


def test_android_main_activity_handles_http_errors_and_waking_fallback():
    """
    Validates that MainActivity.kt specifies waking.html as FALLBACK_URL,
    implements onReceivedHttpError, and propagates error status to avoid blank screens.
    """
    kt_path = os.path.join("android", "app", "src", "main", "java", "com", "sinbha", "app", "MainActivity.kt")
    assert os.path.exists(kt_path), f"Missing {kt_path}"

    with open(kt_path, "r", encoding="utf-8") as f:
        kt_source = f.read()

    assert 'const val FALLBACK_URL = "file:///android_asset/public/waking.html"' in kt_source, \
        "MainActivity.kt must point FALLBACK_URL to waking.html, not index.html"
    assert "onReceivedHttpError" in kt_source, "MainActivity.kt must implement onReceivedHttpError"
    assert "statusCode == 429 || statusCode >= 500" in kt_source, \
        "MainActivity.kt must intercept 429 and 5xx errors"


def test_electron_main_handles_navigation_status_and_avoids_blank_window():
    """
    Validates that electron/main.js intercepts both did-fail-load and HTTP 429/5xx status
    codes on main frame navigation, loading waking.html with query parameters.
    """
    electron_main = os.path.join("electron", "main.js")
    with open(electron_main, "r", encoding="utf-8") as f:
        src = f.read()

    assert "did-fail-load" in src, "electron/main.js must handle did-fail-load"
    assert "code === 429 || code >= 500" in src, \
        "electron/main.js must intercept 429 and 5xx navigation status codes"
    assert "waking.html" in src, "electron/main.js must route to waking.html"
    assert "desktopCommandBackoffUntil" in src, \
        "electron/main.js must have 429 rate limit backoff in command poller loop"
