"""Password hashing — stdlib PBKDF2-HMAC-SHA256, no third-party dependency.

A stored password is ``{salt, hash, iterations}`` (all hex/int). We never store the plaintext.
``verify`` recomputes with the stored salt+iterations and compares in constant time. Iteration count
is stored per-hash so it can be raised later without invalidating old accounts. (This is a parody app
with no password reset — pbkdf2 is plenty; swapping in argon2/bcrypt later is a localized change.)
"""

import hashlib
import hmac
import secrets
from typing import Dict

_ITERATIONS = 200_000
_ALGORITHM = "sha256"


def hash_password(plaintext: str) -> Dict[str, object]:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(_ALGORITHM, plaintext.encode("utf-8"),
                                 bytes.fromhex(salt), _ITERATIONS)
    return {"salt": salt, "hash": digest.hex(), "iterations": _ITERATIONS}


def verify_password(plaintext: str, stored: Dict[str, object]) -> bool:
    if not isinstance(stored, dict) or "salt" not in stored or "hash" not in stored:
        return False
    try:
        iterations = int(stored.get("iterations", _ITERATIONS))
        digest = hashlib.pbkdf2_hmac(_ALGORITHM, plaintext.encode("utf-8"),
                                     bytes.fromhex(str(stored["salt"])), iterations)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), str(stored["hash"]))
