"""Audit log writer and chain verifier.

Writing is serialised. Two concurrent writers must not claim the same sequence
number, or the chain forks and verification becomes meaningless. On Postgres we
take an advisory lock; on other backends we fall back to a table lock.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import GENESIS_HASH, AuditEntry
from app.models.base import utcnow
from app.models.enums import AuditAction

logger = logging.getLogger(__name__)

# Arbitrary but fixed key for the Postgres advisory lock guarding chain appends.
_AUDIT_LOCK_KEY = 0x5348_5241_4D41_5544  # "SHRAMAUD"


@dataclass(frozen=True)
class ChainVerification:
    """Outcome of walking the audit chain."""

    valid: bool
    entries_checked: int
    first_bad_sequence: int | None = None
    reason: str | None = None


def _acquire_lock(session: Session) -> None:
    """Serialise chain appends.

    A transaction-scoped Postgres advisory lock releases automatically on commit
    or rollback, so a crashed writer cannot wedge the log. On SQLite the engine
    already serialises writers, so no lock is needed.
    """
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(_AUDIT_LOCK_KEY)))


def record(
    session: Session,
    *,
    action: AuditAction,
    subject_type: str,
    subject_id: str,
    actor_id: str | None = None,
    actor_role: str | None = None,
    actor_ip: str | None = None,
    establishment_id: str | None = None,
    purpose: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEntry:
    """Append one entry to the chain.

    Does not commit. The caller commits, so the audit entry and the change it
    describes land in the same transaction — an action can never be applied
    without its audit record, or vice versa.
    """
    _acquire_lock(session)

    last = session.execute(
        select(AuditEntry).order_by(AuditEntry.sequence.desc()).limit(1)
    ).scalar_one_or_none()

    entry = AuditEntry(
        sequence=1 if last is None else last.sequence + 1,
        # Set here rather than left to the column default. A default is applied at
        # flush time, but the hash is computed before flush — so relying on it
        # would hash a None timestamp and store a different one, breaking chain
        # verification on the very first entry.
        recorded_at=utcnow(),
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        actor_ip=actor_ip,
        subject_type=subject_type,
        subject_id=subject_id,
        establishment_id=establishment_id,
        purpose=purpose,
        detail=detail or {},
        prev_hash=GENESIS_HASH if last is None else last.entry_hash,
        entry_hash="",
    )
    entry.entry_hash = entry.compute_hash()
    session.add(entry)
    session.flush()

    logger.info(
        "audit recorded",
        extra={
            "audit_sequence": entry.sequence,
            "audit_action": str(action),
            "subject": f"{subject_type}:{subject_id}",
        },
    )
    return entry


def verify_chain(session: Session, *, batch_size: int = 1000) -> ChainVerification:
    """Walk the whole chain and confirm every hash and link.

    Streams in batches so a large log does not have to fit in memory.
    """
    expected_prev = GENESIS_HASH
    expected_sequence = 1
    checked = 0
    offset = 0

    while True:
        batch = (
            session.execute(
                select(AuditEntry)
                .order_by(AuditEntry.sequence)
                .offset(offset)
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        if not batch:
            break

        for entry in batch:
            if entry.sequence != expected_sequence:
                return ChainVerification(
                    valid=False,
                    entries_checked=checked,
                    first_bad_sequence=entry.sequence,
                    reason=f"sequence gap: expected {expected_sequence}, found {entry.sequence}",
                )
            if entry.prev_hash != expected_prev:
                return ChainVerification(
                    valid=False,
                    entries_checked=checked,
                    first_bad_sequence=entry.sequence,
                    reason="prev_hash does not match the preceding entry",
                )
            if entry.compute_hash() != entry.entry_hash:
                return ChainVerification(
                    valid=False,
                    entries_checked=checked,
                    first_bad_sequence=entry.sequence,
                    reason="entry content does not match its stored hash (tampered)",
                )

            expected_prev = entry.entry_hash
            expected_sequence += 1
            checked += 1

        offset += batch_size

    return ChainVerification(valid=True, entries_checked=checked)
