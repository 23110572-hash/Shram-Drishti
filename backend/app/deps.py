"""FastAPI dependencies for authentication and authorisation.

Authorisation is deliberately two-stage and both stages are mandatory:

1. ``require_roles`` — does this kind of user perform this kind of action.
2. ``AccessContext.assert_can_access`` — may this particular user touch this
   particular establishment.

Passing stage one alone is not enough. An inspector authenticated for Gujarat
must not read a Maharashtra establishment, so every endpoint that resolves an
establishment goes through stage two as well.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.enums import Role
from app.models.establishment import Establishment
from app.models.user import User
from app.security import TokenError, decode_access_token

logger = logging.getLogger(__name__)

# auto_error=False so a missing header produces our own 401 with a WWW-
# Authenticate hint rather than FastAPI's bare 403.
_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorised(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request,
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise _unauthorised("missing bearer token")

    try:
        claims = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise _unauthorised(str(exc)) from exc

    user = session.get(User, claims.subject)
    if user is None or not user.is_active:
        # Deactivating a user must take effect immediately, even though the
        # signed token is still cryptographically valid until it expires.
        raise _unauthorised("user no longer active")

    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: Role):
    """Dependency factory restricting an endpoint to specific roles."""

    def _check(user: CurrentUser) -> User:
        if user.role not in allowed:
            logger.warning(
                "role check failed",
                extra={
                    "user_id": user.id,
                    "user_role": str(user.role),
                    "required": [str(r) for r in allowed],
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient role",
            )
        return user

    return _check


@dataclass(frozen=True)
class AccessContext:
    """Answers "may this user touch this establishment", and fails closed."""

    user: User

    @property
    def is_admin(self) -> bool:
        return self.user.role is Role.ADMIN

    def can_access(self, establishment: Establishment) -> bool:
        role = self.user.role

        if role is Role.ADMIN:
            return True

        if role is Role.EMPLOYER:
            return establishment.organisation_id == self.user.organisation_id

        if role in {Role.INSPECTOR, Role.ANALYST}:
            # An empty jurisdiction list means no scope, therefore no access.
            # Treating empty as "all" would silently grant nationwide reach to a
            # half-provisioned account.
            return establishment.jurisdiction_code in set(self.user.jurisdictions or [])

        return False

    def assert_can_access(self, establishment: Establishment) -> None:
        """Raise 404 — not 403 — when access is denied.

        403 confirms the establishment exists, which leaks the existence of
        establishments outside the caller's scope. 404 reveals nothing.
        """
        if not self.can_access(establishment):
            logger.warning(
                "establishment access denied",
                extra={
                    "user_id": self.user.id,
                    "user_role": str(self.user.role),
                    "establishment_id": establishment.id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="establishment not found"
            )


def get_access_context(user: CurrentUser) -> AccessContext:
    return AccessContext(user=user)


Access = Annotated[AccessContext, Depends(get_access_context)]


def client_ip(request: Request) -> str | None:
    """Best-effort client IP.

    X-Forwarded-For is honoured only because this sits behind a reverse proxy in
    deployment. The header is client-controlled, so it is used for audit context
    and rate limiting, never for authorisation.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None
