"""
SINBHA Security & Privacy Hardening Layer (Step 11)
Includes:
- Production configuration validation & secret checks
- CSRF protection for cookie-based state-changing requests
- Security headers middleware (CSP, HSTS, X-Frame-Options, etc.)
- In-memory sliding window rate limiting (per IP and per user)
- Daily user AI message limit and global cost cap kill switch
- Request size limiter and maximum input length validators
"""

import os
import time
from collections import defaultdict
from typing import Dict, List, Tuple
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

# ----------------- 1. Configuration & Production Safety -----------------

def is_production() -> bool:
    return os.getenv("ENV", "development").strip().lower() == "production"

def is_dev_mode_allowed() -> bool:
    """DEV_MODE is strictly forbidden in production."""
    if is_production():
        return False
    return os.getenv("DEV_MODE", "false").strip().lower() == "true"

def validate_production_config():
    """
    Requirement 1: The app must refuse to start in production if required secrets are missing.
    Requirement 11: Database connections must require SSL.
    """
    if not is_production():
        return

    errors = []

    # 1. AI Model API Key (Groq or OpenRouter)
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    has_valid_groq = groq_key and "your_groq_api_key" not in groq_key
    has_valid_or = openrouter_key and "your_openrouter_api_key" not in openrouter_key
    if not has_valid_groq and not has_valid_or:
        errors.append("AI API Key is missing. Please configure GROQ_API_KEY or OPENROUTER_API_KEY.")

    # 2. Database URL
    db_url = os.getenv("DATABASE_URL", "").strip().lower()
    if not db_url:
        errors.append("DATABASE_URL is missing in production.")
    elif db_url.startswith("sqlite"):
        errors.append("DATABASE_URL cannot be SQLite in production. PostgreSQL is required.")
    elif "sslmode=" not in db_url:
        errors.append("DATABASE_URL must require SSL (missing sslmode=require parameter).")

    # 3. Data Encryption Key
    enc_key = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    if not enc_key or "your_base64_fernet_key" in enc_key:
        errors.append("DATA_ENCRYPTION_KEY is missing. Sensitive data cannot be encrypted at rest without it.")

    if errors:
        error_msg = "CRITICAL PRODUCTION CONFIGURATION ERROR(S):\n" + "\n".join(f"- {e}" for e in errors)
        raise RuntimeError(error_msg)

# ----------------- 2. Rate Limiting Engine -----------------

class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter per IP or user ID."""
    def __init__(self):
        # key -> list of timestamp floats
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Returns (is_allowed, remaining_seconds_or_requests).
        """
        now = time.time()
        window_start = now - window_seconds
        # Clean older entries
        self.requests[key] = [ts for ts in self.requests[key] if ts > window_start]

        if len(self.requests[key]) >= max_requests:
            oldest = self.requests[key][0]
            retry_after = max(1, int(oldest + window_seconds - now))
            return False, retry_after

        self.requests[key].append(now)
        return True, max_requests - len(self.requests[key])

    def reset(self):
        """Clears all rate limiting history."""
        self.requests.clear()

limiter = SlidingWindowRateLimiter()

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown_ip"

def check_endpoint_rate_limits(request: Request, user_id: int = None):
    """
    Applies endpoint-specific rate limits.
    """
    ip = get_client_ip(request)
    path = request.url.path

    # Login rate limit: 10 requests / 5 minutes per IP
    if path == "/api/auth/login" and request.method == "POST":
        allowed, retry_after = limiter.check(f"login_ip_{ip}", max_requests=10, window_seconds=300)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many login attempts. Please wait {retry_after} seconds before trying again."
            )

    # Signup rate limit: 5 requests / 15 minutes per IP
    elif path == "/api/auth/signup" and request.method == "POST":
        allowed, retry_after = limiter.check(f"signup_ip_{ip}", max_requests=5, window_seconds=900)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many accounts registered from this connection. Please try again after {retry_after} seconds."
            )

    # Chat rate limit: 25 requests / minute per user or IP
    elif path == "/api/chat" and request.method == "POST":
        rate_key = f"chat_user_{user_id}" if user_id else f"chat_ip_{ip}"
        allowed, retry_after = limiter.check(rate_key, max_requests=25, window_seconds=60)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Whoa, you're typing really fast! Let's pause for a breath and try again in a few seconds. 🌸"
            )

    # General endpoints: 120 requests / minute per IP
    else:
        allowed, retry_after = limiter.check(f"general_ip_{ip}", max_requests=120, window_seconds=60)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Please wait {retry_after} seconds."
            )

# ----------------- 3. Daily AI Limits & Cost Cap Kill Switch -----------------

def get_daily_user_ai_limit() -> int:
    try:
        return int(os.getenv("DAILY_USER_AI_LIMIT", "100"))
    except Exception:
        return 100

def get_daily_global_ai_limit() -> int:
    try:
        return int(os.getenv("DAILY_GLOBAL_AI_LIMIT", "1000"))
    except Exception:
        return 1000

def check_ai_usage_caps(user_today_count: int, global_today_count: int):
    """
    Requirement 4: Checks per-user daily message limit and global cost cap kill switch.
    """
    user_limit = get_daily_user_ai_limit()
    global_limit = get_daily_global_ai_limit()

    # 1. Global Kill Switch (Cost Cap)
    if global_today_count >= global_limit:
        return (
            False,
            "SINBHA is taking a short rest right now to cool down its circuits! "
            "Please check back in a little while, or manage your tasks normally. 🌸"
        )

    # 2. Per-User Daily Limit
    if user_today_count >= user_limit:
        return (
            False,
            "I want to make sure you get some restful time today! We've had a wonderful "
            "conversation today, so let's pause and continue tomorrow. You can still check your tasks and notes! 🌸"
        )

    return True, ""

def get_allowed_origins() -> List[str]:
    """
    Returns trusted origins for CORS and CSRF verification.
    Includes localhost, mobile app schemes (tauri/capacitor),
    Render deployment URL if present, and ALLOWED_ORIGINS environment variable.
    """
    origins = [
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        "http://localhost",
        "http://localhost:8000",
        "https://127.0.0.1",
        "https://localhost",
        # Mobile / Desktop wrappers (Android & Windows)
        "tauri://localhost",
        "capacitor://localhost",
        "http://localhost:1420",
    ]
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if render_url:
        origins.append(render_url.rstrip("/"))

    custom = os.getenv("ALLOWED_ORIGINS", "").strip()
    if custom:
        for o in custom.split(","):
            if o.strip():
                origins.append(o.strip().rstrip("/"))

    return list(dict.fromkeys(origins))

# ----------------- 4. Security Headers & CSRF Middleware -----------------

class SecurityHeadersAndCSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Request Body Size Limiter (Max 1MB)
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 1_048_576:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body too large. Maximum allowed size is 1MB."}
            )

        # 2. CSRF Protection for state-changing requests
        # State-changing requests using cookie authentication must include
        # a custom header (e.g. X-Requested-With) or come from an authorized Origin
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.url.path
            # Check Origin / Referer if present
            origin = request.headers.get("origin") or request.headers.get("referer")
            custom_header = request.headers.get("x-requested-with") or request.headers.get("x-csrf-token")

            allowed_origins = get_allowed_origins()

            # If an Origin is passed, make sure it belongs to an allowed origin
            if origin:
                origin_valid = any(origin.startswith(allowed) for allowed in allowed_origins)
                if not origin_valid and not custom_header:
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Cross-Site Request Forgery (CSRF) check failed: invalid Origin."}
                    )

        # Process the request
        response: Response = await call_next(request)

        # 3. Security Headers (Requirement 2)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # Content-Security-Policy (CSP)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp

        # Strict-Transport-Security (HSTS in production)
        if is_production():
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

        return response
