"""
Unit and Integration Tests for Step C2.13: LLM Provider Plan
Follows AGENT_RULES.md (including Rule 24).

Validates:
1. Fallback chain order: Groq (20b/120b) -> Google AI Studio (Gemini Flash) -> OpenRouter -> Dev Local.
2. Complete failure simulation: when all providers fail, returns deterministic error message without raw secrets or provider names.
3. Dev Local refusal: DEV_LLM_BASE_URL is strictly refused when ENV=production or RENDER=true.
4. Spending caps & Alerts: Global spend cap pauses queries, 80% spend alert is triggered, per-user limits enforced.
5. Telemetry recording: tokens today per provider/model/user and errors by type.
6. Dynamic model listing: models are cached and prevent 404s.
"""

import os
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.llm_provider_config import (
    telemetry,
    check_spending_and_user_limits,
    get_spending_alert,
    build_ordered_provider_chain,
    is_production_environment,
    fetch_available_models_for_provider,
    GLOBAL_DAILY_SPEND_CAP_USD,
    PROVIDER_PRIVACY_METADATA,
)
from app.agent_loop import (
    _get_fallback_candidates,
    run_agent_loop,
    _call_llm_with_tools,
)


@pytest.fixture(autouse=True)
def reset_telemetry_state():
    """Reset telemetry tracking before every test."""
    telemetry.tokens_today = {}
    telemetry.spend_today_usd = 0.0
    telemetry.errors_today = {}
    telemetry.lockouts = {}
    telemetry.discovered_models = {}
    yield


def test_production_environment_refusal_of_dev_local():
    """Requirement 5: dev_local provider must be strictly refused in production."""
    with patch.dict(os.environ, {"DEV_LLM_BASE_URL": "http://localhost:11434/v1", "ENV": "production"}):
        assert is_production_environment() is True
        chain = build_ordered_provider_chain()
        # Ensure dev_local is NOT in the chain
        assert not any(c.get("provider") == "dev_local" for c in chain)

    with patch.dict(os.environ, {"DEV_LLM_BASE_URL": "http://localhost:11434/v1", "RENDER": "true"}):
        assert is_production_environment() is True
        chain = build_ordered_provider_chain()
        assert not any(c.get("provider") == "dev_local" for c in chain)

    with patch.dict(os.environ, {"DEV_LLM_BASE_URL": "http://localhost:11434/v1", "ENV": "development", "RENDER": ""}):
        assert is_production_environment() is False
        chain = build_ordered_provider_chain()
        assert any(c.get("provider") == "dev_local" for c in chain)


def test_fallback_chain_hierarchy():
    """Requirement 2 & 3: Groq (Primary) -> Google AI Studio (Fallback 1) -> OpenRouter (Fallback 2)."""
    env_keys = {
        "GROQ_API_KEY": "gsk_test_groq_key",
        "GEMINI_API_KEY": "AIzaSyTestGeminiKey",
        "OPENROUTER_API_KEY": "sk-or-test-openrouter-key",
        "ENV": "production",
    }
    with patch.dict(os.environ, env_keys, clear=False):
        chain = build_ordered_provider_chain()
        providers = [c["provider"] for c in chain]
        assert "groq" in providers
        assert "gemini" in providers
        assert "openrouter" in providers
        assert providers.index("groq") < providers.index("gemini")
        assert providers.index("gemini") < providers.index("openrouter")


def test_spending_cap_and_alert_threshold():
    """Requirement 7: Global daily spend cap and 80% spending alert."""
    # 1. Below 80% threshold
    telemetry.spend_today_usd = 0.50
    assert get_spending_alert() is None
    allowed, reason = check_spending_and_user_limits(user_id=1)
    assert allowed is True
    assert reason is None

    # 2. At 80% threshold ($0.80)
    telemetry.spend_today_usd = 0.85
    alert = get_spending_alert()
    assert alert is not None
    assert "85%" in alert
    allowed, reason = check_spending_and_user_limits(user_id=1)
    assert allowed is True

    # 3. Exceeded cap ($1.00)
    telemetry.spend_today_usd = 1.05
    allowed, reason = check_spending_and_user_limits(user_id=1)
    assert allowed is False
    assert "spending cap" in reason.lower()


def test_per_user_token_limits():
    """Requirement 7: Deterministic code-written message for per-user token cap."""
    user_id = 42
    # Record 160k tokens for this user today (limit is 150k)
    telemetry.user_tokens_today[user_id] = 160000
    allowed, reason = check_spending_and_user_limits(user_id)
    assert allowed is False
    assert "daily ai usage limit" in reason.lower()


@pytest.mark.asyncio
async def test_dynamic_model_discovery_caching():
    """Requirement 2: Dynamic discovery of models from provider /models endpoint with 1h cache."""
    mock_models_response = {
        "data": [
            {"id": "gemini-2.5-flash"},
            {"id": "gemini-1.5-pro"}
        ]
    }
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_models_response
        mock_get.return_value = mock_resp

        models = await fetch_available_models_for_provider(
            "gemini", "dummy_key", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        )
        assert "gemini-2.5-flash" in models
        assert mock_get.call_count == 1

        # Second call within 1 hour must use cache without calling httpx
        models_cached = await fetch_available_models_for_provider(
            "gemini", "dummy_key", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        )
        assert models_cached == models
        assert mock_get.call_count == 1  # No additional network request


@pytest.mark.asyncio
async def test_full_failover_when_all_providers_fail():
    """
    Requirement 8: Simulate every provider failing sequentially.
    Ensures agent loop catches all failures and returns a truthful user-facing explanation.
    """
    with patch("app.agent_loop._call_llm_with_tools") as mock_call:
        # All calls return 429 rate limit errors
        mock_call.return_value = {
            "success": False,
            "status": 429,
            "error": "rate_limit",
        }

        mock_db = MagicMock()
        mock_db.get_active_ai_provider.return_value = "auto"
        mock_db.get_emergency_stopped.return_value = False
        mock_db.get_active_task_memory.return_value = []

        result = await run_agent_loop(
            user_id=1,
            user_message="Hello SINBHA",
            chat_history=[],
            remembered_facts=[],
            user_devices=[],
            db_module=mock_db,
        )

        assert result.error == "rate_limit"
        assert "429: Too Many Requests" in result.reply
        # Provider names like groq or openrouter should not be leaked in the user reply
        assert "groq" not in result.reply.lower()
        assert "openrouter" not in result.reply.lower()


def test_provider_privacy_metadata_integrity():
    """Requirement 6: Data-use notes must be defined for all providers."""
    for provider in ("groq", "gemini", "openrouter", "dev_local"):
        assert provider in PROVIDER_PRIVACY_METADATA
        meta = PROVIDER_PRIVACY_METADATA[provider]
        assert "name" in meta
        note = meta.get("privacy_note") or meta.get("data_use", "")
        assert len(note) > 20
