"""Users, organisations and jurisdiction scoping.

The access model is two-layered:

* **Role** decides what kind of action a user may take.
* **Scope** decides which establishments those actions may touch.

Both are enforced. An inspector with the right role but the wrong jurisdiction
must not see an establishment, and a query that forgets the scope filter is a
data breach, so scoping is applied in a single shared helper rather than
repeated per endpoint.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import EnumColumn, IdMixin, JSONColumn, TimestampMixin
from app.models.enums import Role


class Organisation(IdMixin, TimestampMixin, Base):
    """An employer company, or a government department for official users."""

    __tablename__ = "organisation"
    __id_prefix__ = "org"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_government: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="organisation")


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "app_user"
    __id_prefix__ = "usr"

    organisation_id: Mapped[str] = mapped_column(
        ForeignKey("organisation.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        EnumColumn(Role, 32), nullable=False, index=True
    )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Jurisdiction codes this user may act within, e.g. ["IN/MH", "IN/GJ"].
    # Empty means no jurisdiction scope, which for an inspector means no access
    # at all rather than access to everything. Fail closed.
    jurisdictions: Mapped[list[str]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_login_count: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organisation: Mapped[Organisation] = relationship(back_populates="users")

    @property
    def is_official(self) -> bool:
        return self.role in {Role.INSPECTOR, Role.ADMIN, Role.ANALYST}


class RefreshToken(IdMixin, TimestampMixin, Base):
    """Rotating refresh tokens.

    Only a hash is stored, so a database leak does not hand over live sessions.
    ``replaced_by_id`` builds a rotation chain: if a token that has already been
    used is presented again, the whole chain is revoked, which is how token
    theft is detected.
    """

    __tablename__ = "refresh_token"
    __id_prefix__ = "rft"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_refresh_token_hash"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_id: Mapped[str | None] = mapped_column(String(40), nullable=True)

    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
