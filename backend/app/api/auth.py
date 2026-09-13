"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.deps import CurrentUser, DbSession, client_ip
from app.models.enums import Role
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
    organisation_id: str
    jurisdictions: list[str]


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: DbSession,
    ip: Annotated[str | None, Depends(client_ip)],
) -> TokenResponse:
    try:
        pair = auth_service.login(
            session,
            email=payload.email,
            password=payload.password,
            user_agent=request.headers.get("User-Agent"),
            ip_address=ip,
        )
    except auth_service.AccountLocked as exc:
        # Committed so the failed-attempt audit entry and lock state persist.
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except auth_service.AuthError as exc:
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    session.commit()
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    request: Request,
    session: DbSession,
    ip: Annotated[str | None, Depends(client_ip)],
) -> TokenResponse:
    try:
        pair = auth_service.refresh(
            session,
            refresh_token=payload.refresh_token,
            user_agent=request.headers.get("User-Agent"),
            ip_address=ip,
        )
    except auth_service.AuthError as exc:
        # Commit so a detected-reuse revocation is not rolled back.
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    session.commit()
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, session: DbSession) -> None:
    auth_service.logout(session, refresh_token=payload.refresh_token)
    session.commit()


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organisation_id=user.organisation_id,
        jurisdictions=list(user.jurisdictions or []),
    )
