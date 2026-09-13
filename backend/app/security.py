"""Password hashing and token issuance.

Argon2id is used rather than bcrypt: it is the current password-hashing
competition winner, resists GPU cracking through memory hardness, and has no
72-byte input truncation surprise.

Access tokens are short-lived and stateless. Refresh tokens are long-lived,
stored only as hashes, and single-use — reuse of a spent refresh token is
treated as theft and revokes the whole chain.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import get_settings

logger = logging.getLogger(__name__)

# Tuned for interactive login on modest hardware. Raising memory_cost is the
# most effective lever against offline cracking.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or of the wrong type."""


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    role: str
    organisation_id: str
    jurisdictions: tuple[str, ...]
    token_type: TokenType
    expires_at: datetime
    jti: str


# ------------------------------------------------------------------ passwords
def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time-ish verification that never raises on bad input.

    A malformed stored hash must read as "wrong password", not a 500. Otherwise
    a corrupted row becomes an availability bug and an information leak.
    """
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when a stored hash predates the current cost parameters."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return False


# --------------------------------------------------------------------- tokens
def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    *,
    subject: str,
    role: str,
    organisation_id: str,
    jurisdictions: list[str],
) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = _now() + timedelta(minutes=settings.access_token_ttl_minutes)

    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "org": organisation_id,
        "jur": jurisdictions,
        "typ": "access",
        "iat": int(_now().timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(16),
        "iss": settings.jwt_issuer,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> TokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "typ", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc

    if payload.get("typ") != "access":
        # A refresh token presented as a bearer credential would otherwise grant
        # long-lived API access, defeating short access-token lifetimes.
        raise TokenError("wrong token type")

    return TokenClaims(
        subject=payload["sub"],
        role=payload.get("role", ""),
        organisation_id=payload.get("org", ""),
        jurisdictions=tuple(payload.get("jur") or ()),
        token_type="access",
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        jti=payload.get("jti", ""),
    )


def generate_refresh_token() -> tuple[str, str]:
    """Return ``(plaintext, hash)``.

    The plaintext goes to the client once and is never stored. Hashing uses
    SHA-256 rather than Argon2 because the token is already 256 bits of
    entropy — there is nothing to brute force, and lookup must be fast.
    """
    plain = secrets.token_urlsafe(48)
    return plain, hash_refresh_token(plain)


def hash_refresh_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def refresh_tokens_match(plain: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_refresh_token(plain), stored_hash)
