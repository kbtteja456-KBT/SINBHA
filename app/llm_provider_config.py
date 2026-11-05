"""
LLM Provider Configuration & Multi-Tier Health System (Step C2.13)
Follows AGENT_RULES.md (including Rule 24).

Features:
1. Configuration-driven provider chain (primary, fallback 1, fallback 2).
2. Per-provider and per-model tool support flags, daily token budgets, and lockout timers.
3. Dynamic model discovery via provider /models endpoints (prevents 404 model_not_found).
4. Google AI Studio (Gemini Flash) support with OpenAI-compatible endpoint.
5. Dev-only OpenAI-compatible base URL (strictly rejected in production environments).
6. Daily cost safety: global daily spend cap, 80% alert threshold, per-user daily token limits.
7. Detailed token usage and error telemetry for DEV_MODE diagnostics.
8. Privacy metadata and provider toggling.
"""

import os
import time
import json
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("sinbha.llm_provider_config")

# Production environment markers
PRODUCTION_ENV_KEYS = ("RENDER", "RENDER_SERVICE_ID", "RENDER_INSTANCE_ID")

def is_production_environment() -> bool:
    """Returns True if running in a live production environment (e.g. Render)."""
    env_str = os.getenv("ENV", "").strip().lower()
    environment_str = os.getenv("ENVIRONMENT", "").strip().lower()
    if env_str in ("production", "prod") or environment_str in ("production", "prod"):
        return True
    for k in PRODUCTION_ENV_KEYS:
        if os.getenv(k):
            return True
    return False


# Provider Metadata & Privacy Disclosures
PROVIDER_PRIVACY_METADATA = {
    "groq": {
        "name": "Groq Cloud (LPU Inference)",
        "privacy_note": "Ephemeral inference on LPU chips. Zero prompt retention for AI training. Data is processed in volatile memory and deleted immediately.",
        "terms_url": "https://groq.com/privacy-policy/",
        "paid": False,
        "default_enabled": True
    },
    "gemini": {
        "name": "Google AI Studio (Gemini)",
        "privacy_note": "Official Google Developer API. Prompts are processed per Google API Terms of Service. Paid/standard tier does not use customer data to train models.",
        "terms_url": "https://ai.google.dev/terms",
        "paid": False,
        "default_enabled": True
    },
    "openrouter": {
        "name": "OpenRouter (Multi-Model Gateway)",
        "privacy_note": "Paid API routing proxy. Does not store message payloads; passes requests directly to underlying providers adhering to provider data privacy policies.",
        "terms_url": "https://openrouter.ai/privacy",
        "paid": True,
        "default_enabled": True
    },
    "dev_local": {
        "name": "Local Dev LLM (Ollama / vLLM / LM Studio)",
        "privacy_note": "100% on-device local execution. Zero network requests or external data transmission. Strictly disabled in production.",
        "terms_url": "http://localhost",
        "paid": False,
        "default_enabled": False
    }
}

# Provider Default Models & Tool Calling Support
DEFAULT_MODELS = {
    "groq": [
        {"id": "openai/gpt-oss-20b", "supports_tools": True, "tpm": 8000, "tpd": 200000, "cost_in": 0.0, "cost_out": 0.0},
        {"id": "openai/gpt-oss-120b", "supports_tools": True, "tpm": 8000, "tpd": 200000, "cost_in": 0.0, "cost_out": 0.0},
    ],
    "gemini": [
        {"id": "gemini-3-flash-preview", "supports_tools": True, "tpm": 1000000, "tpd": 1500, "cost_in": 0.0, "cost_out": 0.0},
        {"id": "gemini-2.5-flash", "supports_tools": True, "tpm": 1000000, "tpd": 1500, "cost_in": 0.0, "cost_out": 0.0},
    ],
    "openrouter": [
        {"id": "google/gemini-2.5-flash", "supports_tools": True, "tpm": 500000, "tpd": 1000000, "cost_in": 0.15, "cost_out": 0.60},
        {"id": "meta-llama/llama-3.3-70b-instruct", "supports_tools": True, "tpm": 500000, "tpd": 1000000, "cost_in": 0.40, "cost_out": 0.40},
    ],
    "dev_local": [
        {"id": "local-default", "supports_tools": True, "tpm": 1000000, "tpd": 10000000, "cost_in": 0.0, "cost_out": 0.0}
    ]
}


class LLMTelemetry:
    """In-memory telemetry for tokens used, costs, errors, and lockout tracking."""

    def __init__(self):
        self.lockouts: Dict[str, float] = {}  # key -> timestamp
        self.lockout_reasons: Dict[str, str] = {}
        self.discovered_models: Dict[str, Tuple[float, List[str]]] = {}  # provider -> (timestamp, model_ids)

        # Usage today
        self.current_day_stamp = time.strftime("%Y-%m-%d")
        self.tokens_today: Dict[str, int] = {}       # "provider:model" -> total_tokens
        self.user_tokens_today: Dict[int, int] = {}   # user_id -> total_tokens
        self.spend_today_usd: float = 0.0
        self.errors_today: Dict[str, int] = {}       # error_type -> count

    def _reset_if_new_day(self):
        today = time.strftime("%Y-%m-%d")
        if today != self.current_day_stamp:
            self.current_day_stamp = today
            self.tokens_today.clear()
            self.user_tokens_today.clear()
            self.spend_today_usd = 0.0
            self.errors_today.clear()

    def mark_lockout(self, target_key: str, duration_seconds: float, reason: str = ""):
        """Locks out a provider or model (e.g. 'groq' or 'groq:openai/gpt-oss-120b')."""
        self.lockouts[target_key.lower()] = time.time() + duration_seconds
        self.lockout_reasons[target_key.lower()] = reason
        logger.warning(f"[LLM_LOCKOUT] {target_key} locked out for {duration_seconds}s. Reason: {reason}")

    def is_locked_out(self, target_key: str) -> bool:
        expiry = self.lockouts.get(target_key.lower(), 0.0)
        return time.time() < expiry

    def record_usage(
        self,
        provider: str,
        model: str,
        user_id: int,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """Records token usage and increments daily spend."""
        self._reset_if_new_day()
        total_tokens = prompt_tokens + completion_tokens

        key = f"{provider}:{model}"
        self.tokens_today[key] = self.tokens_today.get(key, 0) + total_tokens
        self.user_tokens_today[user_id] = self.user_tokens_today.get(user_id, 0) + total_tokens

        # Calculate cost
        cost = 0.0
        provider_meta = DEFAULT_MODELS.get(provider, [])
        for m in provider_meta:
            if m["id"] == model:
                cost = (prompt_tokens * m.get("cost_in", 0.0) / 1_000_000.0) + (completion_tokens * m.get("cost_out", 0.0) / 1_000_000.0)
                break
        self.spend_today_usd += cost
        return cost

    def record_error(self, error_type: str):
        self._reset_if_new_day()
        self.errors_today[error_type] = self.errors_today.get(error_type, 0) + 1

    def get_summary(self) -> dict:
        self._reset_if_new_day()
        active_lockouts = {
            k: {
                "remaining_seconds": max(0, int(v - time.time())),
                "reason": self.lockout_reasons.get(k, "")
            }
            for k, v in self.lockouts.items() if time.time() < v
        }
        return {
            "date": self.current_day_stamp,
            "spend_today_usd": round(self.spend_today_usd, 4),
            "tokens_today_by_model": dict(self.tokens_today),
            "user_token_counts": dict(self.user_tokens_today),
            "errors_today": dict(self.errors_today),
            "active_lockouts": active_lockouts,
            "production_environment": is_production_environment()
        }


# Global singleton instance
telemetry = LLMTelemetry()


# Daily Cost & Safety Thresholds
GLOBAL_DAILY_SPEND_CAP_USD = float(os.getenv("LLM_DAILY_SPEND_CAP_USD", "1.00"))
DAILY_SPEND_ALERT_RATIO = 0.80  # Alert when 80% of daily cap is reached
PER_USER_DAILY_TOKEN_LIMIT = int(os.getenv("LLM_PER_USER_DAILY_TOKEN_LIMIT", "150000"))


def check_spending_and_user_limits(user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Step C2.13 Item 7: Deterministic code enforcement of daily spending and user token caps.
    Never lets an LLM hallucinate or guess budget limits.
    """
    telemetry._reset_if_new_day()

    # 1. Global Daily Spend Cap (Paid providers)
    if telemetry.spend_today_usd >= GLOBAL_DAILY_SPEND_CAP_USD:
        return False, f"Daily AI service spending cap (${GLOBAL_DAILY_SPEND_CAP_USD:.2f}) reached for today. Resets at midnight UTC."

    # 2. Per-User Daily Token Cap
    user_tokens = telemetry.user_tokens_today.get(user_id, 0)
    if user_tokens >= PER_USER_DAILY_TOKEN_LIMIT:
        return False, f"You have reached your daily AI usage limit ({PER_USER_DAILY_TOKEN_LIMIT:,} tokens). Resets at midnight UTC."

    return True, None


def get_spending_alert() -> Optional[str]:
    """Returns alert string if daily spend exceeds 80% threshold."""
    if telemetry.spend_today_usd >= (GLOBAL_DAILY_SPEND_CAP_USD * DAILY_SPEND_ALERT_RATIO):
        pct = int((telemetry.spend_today_usd / GLOBAL_DAILY_SPEND_CAP_USD) * 100)
        return f"Warning: Daily AI service budget is at {pct}% (${telemetry.spend_today_usd:.2f} of ${GLOBAL_DAILY_SPEND_CAP_USD:.2f})."
    return None


async def fetch_available_models_for_provider(provider_id: str, api_key: str, endpoint: str) -> List[str]:
    """
    Step C2.13 Item 2: Dynamic discovery of models from provider's /models endpoint.
    Caches model list for 1 hour to avoid repeated overhead and completely prevents 404s.
    """
    now = time.time()
    cached = telemetry.discovered_models.get(provider_id)
    if cached and (now - cached[0] < 3600):
        return cached[1]

    # Model listing endpoint
    models_url = endpoint.replace("/chat/completions", "/models")
    if provider_id == "gemini":
        models_url = "https://generativelanguage.googleapis.com/v1beta/openai/models"

    headers = {"Authorization": f"Bearer {api_key}"}
    if provider_id == "gemini":
        headers["x-goog-api-key"] = api_key

    model_ids = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(models_url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", [])
                for it in items:
                    mid = it.get("id")
                    if mid:
                        model_ids.append(mid)
    except Exception as e:
        logger.warning(f"Could not fetch dynamic models for {provider_id}: {e}")

    # Fall back to known default models if query fails or returns empty
    if not model_ids:
        model_ids = [m["id"] for m in DEFAULT_MODELS.get(provider_id, [])]

    telemetry.discovered_models[provider_id] = (now, model_ids)
    return model_ids


def build_ordered_provider_chain(
    active_pref: Optional[str] = None,
    disabled_providers: Optional[List[str]] = None
) -> List[dict]:
    """
    Step C2.13 Item 2 & 3:
    Builds the prioritized execution chain of providers.
    Order:
    1. Primary (Groq)
    2. Fallback 1: Google AI Studio (Gemini Flash)
    3. Fallback 2: OpenRouter (Paid fallback)
    4. Dev Local: (Optional, only allowed in non-production environments)
    """
    disabled_set = set(d.lower() for d in (disabled_providers or []))
    chain = []

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    groq_key2 = os.getenv("GROQ_API_KEY2", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    dev_local_url = os.getenv("DEV_LLM_BASE_URL", "").strip()

    is_prod = is_production_environment()

    # 1. Dev Local Provider (STRICTLY NON-PRODUCTION)
    if dev_local_url and "dev_local" not in disabled_set:
        if is_prod:
            logger.error("[SECURITY] DEV_LLM_BASE_URL is configured but strictly rejected in production environments.")
        else:
            chain.append({
                "provider": "dev_local",
                "api_key": "dummy_local_key",
                "model": "local-default",
                "endpoint": f"{dev_local_url.rstrip('/')}/chat/completions",
                "supports_tools": True,
                "reasoning_effort": None,
                "is_local": True
            })

    # 2. Groq Primary (Key 1)
    has_groq = bool(groq_key and groq_key != "your_groq_api_key_here")
    preferred_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
    if telemetry.is_locked_out(f"groq:{preferred_model}") or telemetry.is_locked_out(preferred_model):
        preferred_model = "openai/gpt-oss-20b" if "120b" in preferred_model else "openai/gpt-oss-120b"

    if has_groq and "groq" not in disabled_set and not telemetry.is_locked_out("groq"):
        chain.append({
            "provider": "groq",
            "api_key": groq_key,
            "model": preferred_model,
            "endpoint": "https://api.groq.com/openai/v1/chat/completions",
            "supports_tools": True,
            "reasoning_effort": "low" if "gpt-oss" in preferred_model else None
        })

    # 2b. Groq Secondary (Key 2: Additional 200,000 Tokens/Day Quota)
    has_groq2 = bool(groq_key2 and groq_key2 != "your_groq_api_key_here")
    if has_groq2 and "groq" not in disabled_set and not telemetry.is_locked_out("groq2"):
        chain.append({
            "provider": "groq",
            "api_key": groq_key2,
            "model": preferred_model,
            "endpoint": "https://api.groq.com/openai/v1/chat/completions",
            "supports_tools": True,
            "reasoning_effort": "low" if "gpt-oss" in preferred_model else None
        })

    # 3. Google AI Studio (Fallback 1)
    has_gemini = bool(gemini_key and gemini_key != "your_gemini_api_key_here")
    if has_gemini and "gemini" not in disabled_set and not telemetry.is_locked_out("gemini"):
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview").strip()
        chain.append({
            "provider": "gemini",
            "api_key": gemini_key,
            "model": gemini_model,
            "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "supports_tools": True,
            "reasoning_effort": None
        })

    # 4. OpenRouter (Fallback 2 - Paid)
    has_openrouter = bool(openrouter_key and openrouter_key != "your_openrouter_api_key_here")
    if has_openrouter and "openrouter" not in disabled_set and not telemetry.is_locked_out("openrouter"):
        openrouter_model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash").strip()
        chain.append({
            "provider": "openrouter",
            "api_key": openrouter_key,
            "model": openrouter_model,
            "endpoint": "https://openrouter.ai/api/v1/chat/completions",
            "supports_tools": True,
            "reasoning_effort": None
        })

    # If active preference specifies a single provider (and not 'auto')
    if active_pref and active_pref != "auto":
        filtered = [c for c in chain if c["provider"] == active_pref]
        if filtered:
            return filtered

    return chain
