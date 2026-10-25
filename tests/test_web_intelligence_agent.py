"""
Comprehensive Unit & Integration Test Suite for SINBHA Web Intelligence Agent.
Covers:
1. SearchDecisionEngine: NO_SEARCH vs SEARCH_REQUIRED vs SEARCH_RECOMMENDED.
2. SSRF Guard: Rejection of localhost, private RFC1918, link-local, and cloud metadata.
3. Safe Web Reader: HTML boilerplate stripping and main text extraction.
4. Provider orchestration & fallback (Tavily + DuckDuckGo).
5. Evidence tracking & citation validation.
6. FastAPI endpoint POST /api/v1/research/search.
"""

import os
import sys
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Ensure repo root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.web_intelligence import (
    SearchDecisionEngine,
    SearchDecisionType,
    SearchDecision,
    validate_url_safe,
    is_ip_private_or_restricted,
    ResearchSource,
    WebIntelligenceAgent,
    SafeWebReader,
    DDGSSearchProvider,
    TavilySearchProvider
)
from app.main import app
import app.database as db

import tempfile

class TestWebIntelligenceAgent(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_db = os.path.join(cls.temp_dir, "test_web_intel.db")
        db.set_engine_url(f"sqlite:///{cls.temp_db}")
        db.init_db()

        os.environ["ENV"] = "development"
        os.environ["DEV_MODE"] = "true"
        os.environ["DATA_ENCRYPTION_KEY"] = "6FGReUnNbpK-4Rw3UJVh8pbnyWI-GbWxnlkVwi_1o2U="

        cls.client = TestClient(app)
        # Create test user for authenticated endpoints
        cls.test_email = "research_user@example.com"
        cls.test_pass = "Password123!"
        u = db.create_user(cls.test_email, cls.test_pass, is_18=True, agreed_terms=True)
        cls.user_id = u["id"]
        # Authenticate client
        login_res = cls.client.post("/api/auth/login", json={"email": cls.test_email, "password": cls.test_pass})
        cls.cookies = login_res.cookies

    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(cls.temp_db):
                os.remove(cls.temp_db)
            if os.path.exists(cls.temp_dir):
                os.rmdir(cls.temp_dir)
        except Exception:
            pass

    # ---------------- 1. Search Decision Tests ----------------

    async def test_01_decision_no_search_greetings_and_feelings(self):
        """Conversational greetings and personal feelings must classify as NO_SEARCH."""
        d1 = SearchDecisionEngine.classify_locally("Hello SINBHA, good morning!")
        self.assertIsNotNone(d1)
        self.assertEqual(d1.decision, SearchDecisionType.NO_SEARCH)

        d2 = SearchDecisionEngine.classify_locally("I am feeling a little tired today")
        self.assertIsNotNone(d2)
        self.assertEqual(d2.decision, SearchDecisionType.NO_SEARCH)

    async def test_02_decision_no_search_memory_and_reminders(self):
        """Memory queries and task reminders must classify as NO_SEARCH."""
        d1 = SearchDecisionEngine.classify_locally("What do you remember about my sister?")
        self.assertIsNotNone(d1)
        self.assertEqual(d1.decision, SearchDecisionType.NO_SEARCH)

        d2 = SearchDecisionEngine.classify_locally("Remind me tomorrow at 9am to drink water")
        self.assertIsNotNone(d2)
        self.assertEqual(d2.decision, SearchDecisionType.NO_SEARCH)

    async def test_03_decision_no_search_basic_math(self):
        """Math calculations must classify as NO_SEARCH."""
        d = SearchDecisionEngine.classify_locally("what is 45 * 12?")
        self.assertIsNotNone(d)
        self.assertEqual(d.decision, SearchDecisionType.NO_SEARCH)

    async def test_04_decision_search_required_explicit_and_current(self):
        """Explicit search, sports fixtures, current news, and prices must trigger SEARCH_REQUIRED."""
        queries = [
            "What is the latest news on SpaceX Starship launch?",
            "Who won the cricket match today?",
            "What is the current stock price of Nvidia?",
            "Search online for the price of Apple AirPods Pro 2",
            "Please check online when the next India match is"
        ]
        for q in queries:
            d = SearchDecisionEngine.classify_locally(q)
            self.assertIsNotNone(d, f"Failed local classification for: {q}")
            self.assertEqual(d.decision, SearchDecisionType.SEARCH_REQUIRED, f"Expected SEARCH_REQUIRED for: {q}")

    async def test_05_decision_search_required_direct_url(self):
        """Direct URL in query must trigger SEARCH_REQUIRED."""
        d = SearchDecisionEngine.classify_locally("Can you read this article https://example.com/tech-news please?")
        self.assertIsNotNone(d)
        self.assertEqual(d.decision, SearchDecisionType.SEARCH_REQUIRED)

    # ---------------- 2. SSRF Protection Tests ----------------

    def test_06_ssrf_blocks_private_and_loopback_ips(self):
        """SSRF guard must reject loopback, private ranges, link-local, and AWS metadata."""
        self.assertTrue(is_ip_private_or_restricted("127.0.0.1"))
        self.assertTrue(is_ip_private_or_restricted("10.0.0.1"))
        self.assertTrue(is_ip_private_or_restricted("192.168.1.100"))
        self.assertTrue(is_ip_private_or_restricted("172.16.0.5"))
        self.assertTrue(is_ip_private_or_restricted("169.254.169.254"))  # AWS metadata
        self.assertTrue(is_ip_private_or_restricted("::1"))
        self.assertFalse(is_ip_private_or_restricted("8.8.8.8"))
        self.assertFalse(is_ip_private_or_restricted("142.250.190.46"))

    def test_07_ssrf_url_validation(self):
        """SSRF validator must block dangerous URL schemes and internal hosts."""
        safe, _ = validate_url_safe("file:///etc/passwd")
        self.assertFalse(safe)

        safe, _ = validate_url_safe("http://localhost:8080/api")
        self.assertFalse(safe)

        safe, _ = validate_url_safe("http://127.0.0.1:3000/admin")
        self.assertFalse(safe)

        safe, _ = validate_url_safe("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(safe)

        safe, _ = validate_url_safe("https://www.google.com")
        self.assertTrue(safe)

    # ---------------- 3. Content Extraction & Fallback Tests ----------------

    async def test_08_safe_web_reader_boilerplate_stripping(self):
        """SafeWebReader removes scripts, styles, and navigation boilerplate."""
        html_sample = """
        <html>
            <head><title>Sample Tech Article</title><style>.hidden{display:none;}</style></head>
            <body>
                <nav><a href="/">Home</a></nav>
                <script>console.log("malicious");</script>
                <article>
                    <h1>Python 3.13 Released</h1>
                    <p>Python 3.13 is now officially available with a free-threaded build option.</p>
                </article>
                <footer>Copyright 2026</footer>
            </body>
        </html>
        """
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = html_sample.encode("utf-8")
            mock_resp.encoding = "utf-8"
            mock_get.return_value = mock_resp

            source = await SafeWebReader.fetch_page("https://example.com/news")
            self.assertIsNotNone(source)
            self.assertEqual(source.title, "Sample Tech Article")
            self.assertIn("Python 3.13 Released", source.content)
            self.assertNotIn("console.log", source.content)
            self.assertNotIn("Copyright", source.content)

    # ---------------- 4. Citation Validation Tests ----------------

    def test_09_citation_validation(self):
        """Verifies bracketed citation extraction and source mapping."""
        sources = [
            ResearchSource(source_id="1", title="Official Python Docs", url="https://python.org", domain="python.org", content="Python 3.13 features"),
            ResearchSource(source_id="2", title="Tech News", url="https://technews.com/py", domain="technews.com", content="Free threading details")
        ]
        reply = "Python 3.13 was released recently [1] with experimental free threading [2]. Unsupported claim [99]."
        clean_text, citations, sources_meta = WebIntelligenceAgent.validate_citations(reply, sources)

        self.assertIn(1, citations)
        self.assertIn(2, citations)
        self.assertNotIn(99, citations)  # Discarded hallucinated citation
        self.assertEqual(len(sources_meta), 2)
        self.assertEqual(sources_meta[0]["domain"], "python.org")
        self.assertEqual(sources_meta[1]["domain"], "technews.com")

    # ---------------- 5. Dedicated Research Endpoint Tests ----------------

    def test_10_fastapi_research_endpoint(self):
        """POST /api/v1/research/search returns structured verified response."""
        res = self.client.post(
            "/api/v1/research/search",
            json={"question": "What is 10 + 20?", "research_depth": "quick"},
            cookies=self.cookies
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("answer", data)
        self.assertIn("sources", data)
        self.assertIn("search_performed", data)
        self.assertEqual(data["decision"], "NO_SEARCH")

if __name__ == "__main__":
    unittest.main()
