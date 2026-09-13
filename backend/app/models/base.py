"""Shared model primitives.

Identifiers are prefixed, time-ordered strings rather than integers or bare
UUIDs. A value like ``fnd_01JQX8...`` is self-describing in logs, API responses
and support conversations, which matters when an inspector quotes a finding id
back to you.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

logger = logging.getLogger(__name__)

# Crockford base32: no I, L, O or U, so ids cannot be misread aloud or mistyped.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def new_id(prefix: str) -> str:
    """Time-ordered, collision-resistant identifier.

    The millisecond timestamp comes first so ids sort chronologically. That keeps
    B-tree index inserts sequential instead of scattered, and makes reading a
    list of ids genuinely informative.
    """
    ms = int(time.time() * 1000)
    return f"{prefix}_{_encode(ms, 10)}{_encode(secrets.randbits(80), 16)}"


def utcnow() -> datetime:
    """Timezone-aware current time. Never use naive datetimes in this codebase."""
    return datetime.now(UTC)


class JSONColumn(TypeDecorator):
    """JSONB on Postgres, plain JSON elsewhere.

    Keeps models portable without giving up JSONB's indexing and containment
    operators, which the findings and evidence tables rely on.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class EnumColumn(TypeDecorator):
    """A ``StrEnum`` stored as a readable string and returned as the enum.

    Stored as text, not an integer or a native Postgres enum type, because a row
    that reads ``severity='HIGH'`` is auditable by a labour officer querying raw
    SQL and ``severity=3`` is not. Native enum types were also avoided: altering
    one requires a migration for every added member.

    The coercion on load is the important part. Declaring these columns as plain
    ``String`` returns a ``str`` from the database, and although ``StrEnum``
    compares equal to its value, an identity check does not:

        loaded_role is Role.ADMIN      # False — it is a plain str
        loaded_role == Role.ADMIN      # True

    That difference is silent and dangerous. It would make an administrator's
    scope check fall through to "no access", and — far worse — it would make
    ``finding.kind is FindingKind.ANOMALY`` false for every stored finding, so
    advisory statistical signals would be counted into an employer's compliance
    score. Returning real enum members makes both styles of comparison correct.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[StrEnum], length: int = 48, **kwargs: Any) -> None:
        super().__init__(length=length, **kwargs)
        self._enum_class = enum_class

    @property
    def python_type(self) -> type:
        return self._enum_class

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, StrEnum):
            return str(value.value)
        # A bare string is accepted but validated, so a typo fails on write
        # rather than becoming an unreadable value nobody can query for.
        return str(self._enum_class(value).value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        try:
            return self._enum_class(value)
        except ValueError:
            # A value written before the member existed, or by hand. Returned as
            # the raw string rather than raising, so one bad row cannot make an
            # entire table unreadable.
            logger.warning(
                "unrecognised value %r for %s; returning the raw string",
                value,
                self._enum_class.__name__,
            )
            return value


class TimestampMixin:
    """Server-side created and updated timestamps.

    Defaults are computed by the database rather than Python so rows written by
    migrations, seeds or manual SQL are stamped consistently.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class IdMixin:
    """Prefixed string primary key.

    Subclasses declare ``__id_prefix__``. ``declared_attr`` builds the column
    per-subclass, so each model gets a default factory bound to its own prefix.
    """

    __id_prefix__: str = "row"

    @declared_attr
    @classmethod
    def id(cls) -> Mapped[str]:
        prefix = cls.__id_prefix__
        return mapped_column(
            String(40),
            primary_key=True,
            default=lambda: new_id(prefix),
            nullable=False,
        )
