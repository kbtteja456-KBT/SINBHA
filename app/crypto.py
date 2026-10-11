"""
Field-Level Encryption at Rest (Step 11, Requirement 8)
Encrypts sensitive text (chat message contents, memory facts) before writing
to the database using Fernet (AES-128-CBC with HMAC-SHA256 authentication).
"""

import os
import base64
import hashlib
from dotenv import load_dotenv

load_dotenv()

from cryptography.fernet import Fernet, InvalidToken

_fernet_instance = None

def get_encryption_key() -> bytes:
    """
    Retrieves or generates a valid Fernet key.
    Reads DATA_ENCRYPTION_KEY from environment.
    If missing in development, derives a stable deterministic fallback key.
    In production (ENV=production), raises an error if not explicitly configured.
    """
    raw_key = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    is_production = os.getenv("ENV", "development").lower() == "production"

    if raw_key:
        # If it's already a 44-byte base64 string, validate it
        try:
            # Fernet keys are 32 url-safe base64-encoded bytes (44 chars)
            decoded = base64.urlsafe_b64decode(raw_key.encode("utf-8"))
            if len(decoded) == 32:
                return raw_key.encode("utf-8")
        except Exception:
            pass
        # If user passed a passphrase, derive a 32-byte key via SHA-256
        derived = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest())
        return derived

    if is_production:
        raise RuntimeError(
            "CRITICAL SECURITY ERROR: DATA_ENCRYPTION_KEY environment variable is missing in production! "
            "SINBHA refuses to start without encryption key configured."
        )

    # Development fallback key derived from local marker so dev data persists predictably
    dev_seed = "sinbha_local_dev_secret_key_seed_2026"
    return base64.urlsafe_b64encode(hashlib.sha256(dev_seed.encode("utf-8")).digest())

def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        key = get_encryption_key()
        _fernet_instance = Fernet(key)
    return _fernet_instance

def set_encryption_key_for_testing(key_bytes: bytes):
    """Allows test suites to test key changes and error handling."""
    global _fernet_instance
    _fernet_instance = Fernet(key_bytes)

def encrypt_text(plain_text: str) -> str:
    """
    Encrypts a plaintext string into a Fernet ciphertext token.
    Returns ciphertext string prefixed with 'enc::' for easy detection.
    """
    if not plain_text:
        return ""
    f = get_fernet()
    token = f.encrypt(plain_text.encode("utf-8")).decode("utf-8")
    return f"enc::{token}"

def decrypt_text(cipher_text: str) -> str:
    """
    Decrypts a ciphertext string.
    If text was not encrypted (legacy plain text), returns as-is safely.
    """
    if not cipher_text:
        return ""
    if not cipher_text.startswith("enc::"):
        # Backwards compatibility for unencrypted legacy rows
        return cipher_text

    token = cipher_text[5:]
    f = get_fernet()
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return "[Decryption error: encryption key does not match or data is corrupted]"
    except Exception as e:
        return f"[Decryption error: {e}]"
