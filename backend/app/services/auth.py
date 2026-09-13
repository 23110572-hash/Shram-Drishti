"""Authentication: login, refresh rotation, logout.

Two defences worth calling out.

**Uniform failure.** Wrong email and wrong password return the same error, and
the password hash is verified even when the user does not exist. Skipping the
hash for unknown emails makes those requests measurably faster, which turns
login into an account-enumeration oracle.

**Refresh rotation with theft detection.** Each refresh issues a new token and
marks the old one replaced. Presenting an already-replaced token means two
parties hold it, so the entire chain is revoked rather than silently reissued.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.base import utcnow
from app.models.enums import AuditAction
from app.models.user import RefreshToken, User
from app.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from app.services import audit

logger = logging.getLogger(__name__)

# Hashed once at import. Verifying against this for unknown emails keeps the
# timing of a bad-email attempt indistinguishable from a bad-password attempt.
_DUMMY_HASH = hash_password("timing-equalisation-placeholder")


class AuthError(Exception):
    """Authentication failed. Message is deliberately vague for the client."""


class AccountLocked(AuthError):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def _issue_pair(
    session: Session,
    user: User,
    *,
    user_agent: str | None,
    ip_address: str | None,
    replaces: RefreshToken | None = None,
) -> TokenPair:
    settings = get_settings()

    access, _ = create_access_token(
        subject=user.id,
        role=str(user.role),
        organisation_id=user.organisation_id,
        jurisdictions=list(user.jurisdictions or []),
    )

    plain_refresh, refresh_hash = generate_refresh_token()
    record = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(user_agent or "")[:255] or None,
        ip_address=(ip_address or "")[:64] or None,
    )
    session.add(record)
    session.flush()

    if replaces is not None:
        replaces.replaced_by_id = record.id
        replaces.revoked_at = utcnow()

    return TokenPair(access_token=access, refresh_token=plain_refresh)


def login(
    session: Session,
    *,
    email: str,
    password: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenPair:
    settings = get_settings()
    now = utcnow()

    user = session.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalar_one_or_none()

    if user is None:
        verify_password(password, _DUMMY_HASH)  # equalise timing
        audit.record(
            session,
            action=AuditAction.USER_LOGIN_FAILED,
            subject_type="user",
            subject_id="unknown",
            actor_ip=ip_address,
            detail={"reason": "no_such_user"},
        )
        raise AuthError("invalid credentials")

    if user.locked_until and user.locked_until > now:
        audit.record(
            session,
            action=AuditAction.USER_LOGIN_FAILED,
            subject_type="user",
            subject_id=user.id,
            actor_ip=ip_address,
            detail={"reason": "locked"},
        )
        raise AccountLocked("account temporarily locked")

    if not user.is_active:
        audit.record(
            session,
            action=AuditAction.USER_LOGIN_FAILED,
            subject_type="user",
            subject_id=user.id,
            actor_ip=ip_address,
            detail={"reason": "inactive"},
        )
        raise AuthError("invalid credentials")

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.account_lock_minutes)
            user.failed_login_count = 0
        audit.record(
            session,
            action=AuditAction.USER_LOGIN_FAILED,
            subject_type="user",
            subject_id=user.id,
            actor_ip=ip_address,
            detail={"reason": "bad_password", "locked": user.locked_until is not None},
        )
        raise AuthError("invalid credentials")

    # Success. Upgrade the stored hash if cost parameters have since increased.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    pair = _issue_pair(session, user, user_agent=user_agent, ip_address=ip_address)

    audit.record(
        session,
        action=AuditAction.USER_LOGIN,
        subject_type="user",
        subject_id=user.id,
        actor_id=user.id,
        actor_role=str(user.role),
        actor_ip=ip_address,
    )
    return pair


def refresh(
    session: Session,
    *,
    refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenPair:
    now = utcnow()
    token_hash = hash_refresh_token(refresh_token)

    record = session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if record is None:
        raise AuthError("invalid refresh token")

    if record.replaced_by_id is not None or record.revoked_at is not None:
        # Reuse of a spent token: two holders. Revoke everything for this user
        # rather than guess which holder is legitimate.
        _revoke_all_for_user(session, record.user_id, now)
        logger.warning(
            "refresh token reuse detected; all sessions revoked",
            extra={"user_id": record.user_id},
        )
        raise AuthError("invalid refresh token")

    if record.expires_at <= now:
        raise AuthError("refresh token expired")

    user = session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AuthError("invalid refresh token")

    return _issue_pair(
        session,
        user,
        user_agent=user_agent,
        ip_address=ip_address,
        replaces=record,
    )


def logout(session: Session, *, refresh_token: str) -> None:
    """Revoke one session. Unknown tokens succeed silently.

    Logout must not reveal whether a token was valid, and a client retrying
    logout should not receive an error.
    """
    record = session.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(refresh_token)
        )
    ).scalar_one_or_none()

    if record is not None and record.revoked_at is None:
        record.revoked_at = utcnow()


def _revoke_all_for_user(session: Session, user_id: str, when) -> None:
    tokens = (
        session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    for token in tokens:
        token.revoked_at = when
