"""CYBER WORKSPACE — token + pairing code security primitives."""
from __future__ import annotations

import hmac
import hashlib
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)


def new_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
