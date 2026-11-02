"""
Dynamic application version reader (Step C2.8 Item 6).
Reads app versions from the build configuration (package.json / environment),
never hardcoded strings.
"""
import os
import json
from pathlib import Path

_CACHED_VERSION = None

def get_app_version() -> str:
    global _CACHED_VERSION
    if _CACHED_VERSION:
        return _CACHED_VERSION

    env_ver = os.getenv("APP_VERSION") or os.getenv("LATEST_APP_VERSION")
    if env_ver:
        _CACHED_VERSION = env_ver.strip()
        return _CACHED_VERSION

    pkg_path = Path(__file__).resolve().parent.parent / "package.json"
    if pkg_path.exists():
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "version" in data:
                    _CACHED_VERSION = str(data["version"]).strip()
                    return _CACHED_VERSION
        except Exception:
            pass

    _CACHED_VERSION = "1.4.12"
    return _CACHED_VERSION


def parse_semver(ver: str) -> tuple:
    """Parses semver string e.g. '1.4.20' or 'v1.4.20' into tuple of ints (1, 4, 20)."""
    import re
    cleaned = re.sub(r'^[^\d]*', '', ver.strip() if ver else '')
    parts = []
    for p in cleaned.split('.'):
        digits = re.match(r'^\d+', p)
        if digits:
            parts.append(int(digits.group(0)))
        else:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


MIN_COMPATIBLE_CLIENT_VERSION = "1.4.21"

def is_client_version_supported(client_ver: str, min_ver: str = None) -> bool:
    """Returns True if client_ver >= min_ver (Step C2.9 Item 8)."""
    if not client_ver:
        return True  # If unknown legacy or not reported yet, allow capability handshake to decide
    if min_ver is None:
        min_ver = os.getenv("MIN_CLIENT_VERSION", MIN_COMPATIBLE_CLIENT_VERSION)
    return parse_semver(client_ver) >= parse_semver(min_ver)


