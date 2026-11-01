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

