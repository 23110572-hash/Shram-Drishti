"""Hash-chained append-only audit log.

Why a hash chain rather than a plain table: an audit log is only worth having if
tampering is detectable. Each entry stores the hash of the previous entry, so
altering or deleting any historical row breaks every hash after it. Verification
walks the chain and reports the first break.

This is what makes a finding defensible. If an employer disputes a finding, the
chain shows exactly who created it, when, from which rule pack version, and
whether anyone has touched it since.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import EnumColumn, IdMixin, JSONColumn, utcnow
from app.models.enums import AuditAction

# Chain anchor. The first entry's prev_hash, so the chain has a defined start.
GENESIS_HASH = "0" * 64


class AuditEntry(IdMixin, Base):
    """One immutable audit record.

    Deliberately has no ``updated_at`` and no ORM update path. Entries are
    written once. Any change is a tamper event, not a legitimate edit.
    """

    __tablename__ = "audit_entry"
    __id_prefix__ = "aud"
    __table_args__ = (
        # Chain verification walks strictly in sequence order.
        Index("ix_audit_entry_sequence", "sequence", unique=True),
        # The common query is "everything that happened to this establishment".
        Index("ix_audit_entry_subject", "subject_type", "subject_id", "recorded_at"),
    )

    # Monotonic position in the chain. Assigned by the writer under a lock so
    # concurrent writes cannot produce two entries claiming the same position.
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    action: Mapped[AuditAction] = mapped_column(
        EnumColumn(AuditAction, 48), nullable=False, index=True
    )

    # Who acted. Null for system-initiated actions such as scheduled scoring.
    actor_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # What was acted upon, e.g. ("finding", "fnd_01JQ...").
    subject_type: Mapped[str] = mapped_column(String(48), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(40), nullable=False)

    # Establishment this action concerns, for jurisdiction-scoped audit reads.
    establishment_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True, index=True
    )

    # DPDP purpose limitation: reads of worker data must state why.
    purpose: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Action detail. Must never contain worker PII; store identifiers and
    # before/after values of non-personal fields only.
    detail: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict, nullable=False)

    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    def compute_hash(self) -> str:
        """Recompute this entry's hash from its content.

        Field order is fixed and explicit. A dict iteration order change would
        otherwise silently invalidate every historical hash.
        """
        payload = {
            "sequence": self.sequence,
            "recorded_at": self.recorded_at.isoformat(),
            "action": str(self.action),
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "establishment_id": self.establishment_id,
            "purpose": self.purpose,
            "detail": self.detail,
            "prev_hash": self.prev_hash,
        }
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
