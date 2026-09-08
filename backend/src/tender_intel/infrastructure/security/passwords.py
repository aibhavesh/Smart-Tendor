"""Password hashing for manual (email/password) sign-in.

PBKDF2-HMAC-SHA256, standard library only — no extra third-party dependency
for a single-purpose primitive, consistent with how the rest of ``security``
favours small, framework-free adapters. 600,000 iterations follows OWASP's
current minimum recommendation for PBKDF2-SHA256 (2023 guidance).

The stored string is self-describing —
``pbkdf2_sha256$<iterations>$<salt-hex>$<hash-hex>`` — so a future increase to
the iteration count does not invalidate hashes created under a lower one, and
verification never has to guess which parameters produced a given hash.

Never used for anything but the password column: refresh-token hashing has
its own function (:func:`tender_intel.infrastructure.security.tokens.hash_refresh_token`)
because it protects a different threat model (a stored lookup key, not a
low-entropy secret a person chose).
"""

from __future__ import annotations

import hashlib
import hmac
import os

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Hash ``password`` with a fresh random salt."""
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a hash from :func:`hash_password`.

    Returns ``False`` (never raises) for a malformed or unrecognised stored
    value, so a corrupt or legacy row fails closed rather than raising into
    caller code that expects a plain yes/no answer.
    """
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = stored.split("$")
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    if algorithm != _ALGORITHM:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)
