"""Canonical records extracted from documents.

These are the facts the rule engine reasons over. Three principles shape them.

**Money is integer paise, never float.** These numbers decide whether an employer
underpaid a worker. ``0.1 + 0.2 != 0.3`` in binary floating point, and a finding
that hinges on a rounding artefact is indefensible.

**Every value carries provenance.** ``source_page``, ``source_bbox`` and
``agreement`` travel with the field so an inspector can click a finding and see
the exact cell on the scan, and so a value the model corrected against OCR is
visibly flagged rather than silently trusted.

**Worker identity is a link, not a name.** ``WorkerIdentity`` groups the same
person across documents. Names in Indian registers vary wildly between filings,
so matching is an explicit, reviewable, confidence-scored artefact.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import EnumColumn, IdMixin, JSONColumn, TimestampMixin
from app.models.enums import SkillCategory


class ExtractedField(IdMixin, TimestampMixin, Base):
    """A single header-level key-value read off a document.

    Header fields (establishment name, wage period, totals) are stored as rows
    rather than columns because the set differs per document type, and a sparse
    wide table would need altering every time a new document type is supported.
    """

    __tablename__ = "extracted_field"
    __id_prefix__ = "efd"
    __table_args__ = (Index("ix_extracted_field_doc_name", "document_id", "name"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(96), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ------------------------------------------------------------- provenance
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # [left, top, width, height] normalised 0-1, or null on a Mode C page.
    source_bbox: Mapped[list[float] | None] = mapped_column(JSONColumn, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Did OCR and the page image agree on this value?
    #   "agreed"     both sources matched
    #   "corrected"  model overrode OCR, with a stated reason
    #   "ocr_only"   no image was sent (Mode A)
    #   "model_only" no OCR available (Mode C)
    agreement: Mapped[str | None] = mapped_column(String(16), nullable=True)
    correction_note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    corrected_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )


class WorkerIdentity(IdMixin, TimestampMixin, Base):
    """One person, linked across documents.

    The same worker appears as "RAJESH KUMAR S/O RAM LAL", "Rajesh Kumar",
    "R. Kumar" and "RAJESH KUMAR RAMLAL" across four filings. String equality
    fails and edit distance does poorly on Indian names with initials and
    patronymics, so the link is produced by a model, stored with its reasoning,
    and left overridable.
    """

    __tablename__ = "worker_identity"
    __id_prefix__ = "wid"
    __table_args__ = (Index("ix_worker_identity_estab", "establishment_id"),)

    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False
    )

    # Canonical display name, chosen from the observed variants.
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Every spelling seen, for audit and for explaining a match to an inspector.
    name_variants: Mapped[list[str]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )

    # Strong identifiers, when present. A shared UAN is proof of identity and
    # short-circuits the whole matching problem.
    uan: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    esic_number: Mapped[str | None] = mapped_column(String(24), nullable=True)
    father_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    skill_category: Mapped[SkillCategory | None] = mapped_column(
        EnumColumn(SkillCategory, 24), nullable=True
    )
    designation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_of_joining: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_of_exit: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_contract_worker: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # How the link was made.
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    match_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    wage_lines: Mapped[list[WageLine]] = relationship(back_populates="worker")


class WageLine(IdMixin, TimestampMixin, Base):
    """One worker's pay for one wage period.

    All amounts in paise. Column names mirror the Code on Wages vocabulary so a
    rule expression reads close to the statute.
    """

    __tablename__ = "wage_line"
    __id_prefix__ = "wgl"
    __table_args__ = (
        Index("ix_wage_line_estab_period", "establishment_id", "period_start"),
        Index("ix_wage_line_worker", "worker_identity_id"),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False
    )
    worker_identity_id: Mapped[str | None] = mapped_column(
        ForeignKey("worker_identity.id", ondelete="SET NULL"), nullable=True
    )

    # As printed on this document, before identity resolution.
    worker_name_as_printed: Mapped[str] = mapped_column(String(255), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ---------------------------------------------------------- days and hours
    days_paid: Mapped[float | None] = mapped_column(Float, nullable=True)
    days_present: Mapped[float | None] = mapped_column(Float, nullable=True)
    overtime_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    normal_hours_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ----------------------------------------------------- amounts, all paise
    basic_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    da_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Allowances excluded from "wages" under the s.2(y) definition. The 50% cap
    # test compares this against total remuneration.
    other_allowances_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)

    overtime_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overtime_rate_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)

    deductions_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pf_deduction_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    esi_deduction_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    advance_recovery_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)

    net_paid_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    skill_category: Mapped[SkillCategory | None] = mapped_column(
        EnumColumn(SkillCategory, 24), nullable=True
    )

    # Per-field provenance for this row, keyed by column name:
    #   {"gross_paise": {"page": 3, "bbox": [...], "agreement": "agreed"}}
    provenance: Mapped[dict] = mapped_column(JSONColumn, default=dict, nullable=False)

    # True when this row failed a verification check during reading — an untraceable
    # figure, or arithmetic that does not hold.
    #
    # Such a row is excluded from compliance evaluation rather than merely flagged.
    # A swapped pair of columns is as likely to hide a breach as to invent one: read
    # deductions and net the wrong way round and a 55% deduction reads as 45%, which
    # is under the statutory cap. Judging an establishment compliant on a row we know
    # we misread is worse than declining to judge it.
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_reasons: Mapped[list[str]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )

    worker: Mapped[WorkerIdentity | None] = relationship(back_populates="wage_lines")

    # ------------------------------------------------------------- derivations
    @property
    def total_remuneration_paise(self) -> int | None:
        """Everything paid, used as the denominator in the s.2(y) 50% test."""
        parts = [self.basic_paise, self.da_paise, self.other_allowances_paise]
        if all(p is None for p in parts):
            return self.gross_paise
        return sum(p or 0 for p in parts)

    @property
    def statutory_wages_paise(self) -> int | None:
        """Basic plus DA: the "wages" base for contributions and overtime."""
        if self.basic_paise is None and self.da_paise is None:
            return None
        return (self.basic_paise or 0) + (self.da_paise or 0)

    @property
    def ordinary_hourly_rate_paise(self) -> int | None:
        """Hourly rate used as the overtime baseline under s.14."""
        wages = self.statutory_wages_paise
        if not wages or not self.days_paid or not self.normal_hours_per_day:
            return None
        hours = self.days_paid * self.normal_hours_per_day
        return int(wages / hours) if hours > 0 else None


class ContributionLine(IdMixin, TimestampMixin, Base):
    """One worker's EPF or ESIC contribution for one month.

    EPF ECR files are structured text, so these rows are parsed exactly with no
    OCR and no model involvement. That makes this table the most reliable data in
    the system and the natural anchor for reconciliation.
    """

    __tablename__ = "contribution_line"
    __id_prefix__ = "cnl"
    __table_args__ = (
        Index("ix_contribution_estab_period", "establishment_id", "period_start"),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False
    )
    worker_identity_id: Mapped[str | None] = mapped_column(
        ForeignKey("worker_identity.id", ondelete="SET NULL"), nullable=True
    )

    scheme: Mapped[str] = mapped_column(String(16), nullable=False)  # EPF | ESIC
    worker_name_as_printed: Mapped[str] = mapped_column(String(255), nullable=False)
    uan: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    member_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    wage_base_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_share_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employer_share_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Non-contributory period: days the worker was absent without pay.
    ncp_days: Mapped[float | None] = mapped_column(Float, nullable=True)

    deposited_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    challan_number: Mapped[str | None] = mapped_column(String(48), nullable=True)

    provenance: Mapped[dict] = mapped_column(JSONColumn, default=dict, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_reasons: Mapped[list[str]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )


class AttendanceRecord(IdMixin, TimestampMixin, Base):
    """One worker's attendance summary for one period, from the muster roll.

    Summary rather than per-day rows: the compliance questions are about totals
    and maxima, and per-day storage would multiply row count by thirty for no
    analytical gain.
    """

    __tablename__ = "attendance_record"
    __id_prefix__ = "att"
    __table_args__ = (
        Index("ix_attendance_estab_period", "establishment_id", "period_start"),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False
    )
    worker_identity_id: Mapped[str | None] = mapped_column(
        ForeignKey("worker_identity.id", ondelete="SET NULL"), nullable=True
    )

    worker_name_as_printed: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    days_present: Mapped[float | None] = mapped_column(Float, nullable=True)
    days_absent: Mapped[float | None] = mapped_column(Float, nullable=True)
    weekly_offs_given: Mapped[int | None] = mapped_column(Integer, nullable=True)

    total_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    overtime_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Peak single-day hours, for the daily working-hours cap.
    max_daily_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_weekly_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Longest run of consecutive worked days, for the rest-day requirement.
    longest_consecutive_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    provenance: Mapped[dict] = mapped_column(JSONColumn, default=dict, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_reasons: Mapped[list[str]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )


class IncidentRecord(IdMixin, TimestampMixin, Base):
    """A workplace accident or dangerous occurrence, and whether it was notified."""

    __tablename__ = "incident_record"
    __id_prefix__ = "inc"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False, index=True
    )

    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    workers_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)

    notified_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notification_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)

    provenance: Mapped[dict] = mapped_column(JSONColumn, default=dict, nullable=False)


class ProseAssertion(IdMixin, TimestampMixin, Base):
    """A fact read out of a prose document by the model.

    Appointment letters, standing orders and safety policies are paragraphs, not
    tables. There is no cell to extract, so the model answers specific questions
    ("does this state the notice period") and each answer is stored with the
    supporting quotation so an inspector can check it against the document.
    """

    __tablename__ = "prose_assertion"
    __id_prefix__ = "prz"
    __table_args__ = (Index("ix_prose_assertion_doc_key", "document_id", "key"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False
    )

    # e.g. "states_wage_rate", "states_notice_period", "is_certified"
    key: Mapped[str] = mapped_column(String(96), nullable=False)
    present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Verbatim supporting text, so the assertion is checkable rather than a
    # bare claim from a model.
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
