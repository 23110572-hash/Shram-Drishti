"""Findings, evidence and compliance scorecards.

A finding is an accusation against a real employer, so every one records enough
to defend itself: which rule fired, which version of which rule pack, the exact
statutory citation, the observed and expected values, and the cell on the page
that proves it.

Statistical anomalies and model-only observations live in the same table but are
structurally prevented from affecting a score. They remain advisory because they
are leads from data analysis, not deterministic statutory verdicts.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
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
from app.models.enums import (
    FindingKind,
    FindingStatus,
    LabourCode,
    RiskBand,
    RuleBasis,
    Severity,
    WageRateSource,
)


class Finding(IdMixin, TimestampMixin, Base):
    __tablename__ = "finding"
    __id_prefix__ = "fnd"
    __table_args__ = (
        Index("ix_finding_estab_status", "establishment_id", "status"),
        Index("ix_finding_code_severity", "code", "severity"),
        Index("ix_finding_rule", "rule_id"),
        Index("ix_finding_period", "establishment_id", "period_start"),
    )

    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False
    )

    # ------------------------------------------------------------ what fired
    kind: Mapped[FindingKind] = mapped_column(
        EnumColumn(FindingKind, 24), nullable=False, index=True
    )
    code: Mapped[LabourCode | None] = mapped_column(
        EnumColumn(LabourCode, 32), nullable=True
    )
    severity: Mapped[Severity] = mapped_column(
        EnumColumn(Severity, 16), nullable=False
    )

    rule_id: Mapped[str] = mapped_column(String(96), nullable=False)
    # Pinned so a rule pack upgrade cannot silently rewrite the basis of a
    # historical finding, e.g. "wages@2026.01".
    rule_pack_version: Mapped[str] = mapped_column(String(48), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(16), nullable=True)

    citation: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # What the rule's operative number rests on, copied from the rule at
    # evaluation time so a later pack revision cannot change the footing of a
    # historical finding. Only RULES_PENDING is a caveat; see RuleBasis.
    rule_basis: Mapped[RuleBasis] = mapped_column(
        EnumColumn(RuleBasis, 24), nullable=False
    )

    # --------------------------------------------------------- what was found
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------- contextual severity
    # The rule declares a baseline severity. It cannot see magnitude, spread or
    # repetition: a deduction at 51% and one at 90% are the same rule. These
    # columns hold the assessed severity and the reason for it, written once at
    # evaluation time and read by scoring thereafter — so the score stays
    # reproducible without freezing judgement into a constant.
    baseline_severity: Mapped[Severity | None] = mapped_column(
        EnumColumn(Severity, 16), nullable=True
    )
    severity_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity_assessed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    observed: Mapped[dict] = mapped_column(JSONColumn, default=dict, nullable=False)
    expected: Mapped[dict] = mapped_column(JSONColumn, default=dict, nullable=False)

    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    affected_worker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Money at stake, when computable. Drives triage more effectively than
    # severity alone: a HIGH affecting one worker matters less than a MEDIUM
    # affecting two hundred.
    exposure_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # When a wage-floor rule fired, whether the rate came from an official
    # notification or a secondary reference table. Legally material.
    wage_rate_source: Mapped[WageRateSource | None] = mapped_column(
        EnumColumn(WageRateSource, 16), nullable=True
    )

    # ------------------------------------------------------------ confidence
    # Lowest extraction confidence among the values this finding depends on. A
    # finding built on a barely-read figure must not look as solid as one built
    # on a clean digital PDF.
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Model-suggested false positive. Advisory: it annotates, never deletes.
    possible_false_positive: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    false_positive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Plain-language narrative. Explicitly non-authoritative; the statutory
    # citation and the observed/expected pair are what carry weight.
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---------------------------------------------------------------- status
    status: Mapped[FindingStatus] = mapped_column(
        EnumColumn(FindingStatus, 24), default=FindingStatus.OPEN, nullable=False
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_changed_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    # Mandatory when an inspector waives or dismisses a finding.
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cure period given to the employer before escalation.
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Stable hash of (rule, establishment, period, subject) used to recognise the
    # same issue across runs, so re-evaluating does not duplicate findings and
    # repeat offences can be counted.
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    evidence: Mapped[list[FindingEvidence]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )

    @property
    def is_scored(self) -> bool:
        """Only current deterministic rule findings contribute to a score."""
        if self.kind is FindingKind.ANOMALY or self.rule_id == "MODEL.OBSERVATION":
            return False
        return self.status in {
            FindingStatus.OPEN,
            FindingStatus.ACKNOWLEDGED,
            FindingStatus.DISPUTED,
        }

    @property
    def is_open(self) -> bool:
        return self.status in {
            FindingStatus.OPEN,
            FindingStatus.ACKNOWLEDGED,
            FindingStatus.DISPUTED,
        }


class FindingEvidence(IdMixin, Base):
    """A pointer to the exact place on a page that supports a finding.

    Without this a finding is an assertion. With it, an inspector clicks and sees
    the cell. This is the single most important thing for making the output
    trustworthy.
    """

    __tablename__ = "finding_evidence"
    __id_prefix__ = "evd"

    finding_id: Mapped[str] = mapped_column(
        ForeignKey("finding.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("document.id", ondelete="SET NULL"), nullable=True
    )

    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # [left, top, width, height] normalised 0-1. Null on Mode C pages, where
    # evidence degrades to the whole page.
    bbox: Mapped[list[float] | None] = mapped_column(JSONColumn, nullable=True)

    field_name: Mapped[str | None] = mapped_column(String(96), nullable=True)
    value_shown: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)

    note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    finding: Mapped[Finding] = relationship(back_populates="evidence")

    @property
    def is_cell_level(self) -> bool:
        return self.bbox is not None


class Scorecard(IdMixin, TimestampMixin, Base):
    """An immutable snapshot of an establishment's compliance position.

    Never updated in place. Each evaluation writes a new row, storing the inputs
    and weights that produced it, so any historical score can be recomputed
    exactly and a rule pack change cannot retroactively alter the past.
    """

    __tablename__ = "scorecard"
    __id_prefix__ = "scr"
    __table_args__ = (
        Index("ix_scorecard_estab_computed", "establishment_id", "computed_at"),
        Index("ix_scorecard_band", "risk_band"),
    )

    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_band: Mapped[RiskBand] = mapped_column(
        EnumColumn(RiskBand, 16), nullable=False
    )

    # Per-Code sub-scores: {"WAGES": 72.5, "OSH": 91.0, ...}
    code_scores: Mapped[dict] = mapped_column(JSONColumn, default=dict, nullable=False)

    # Reported separately and never folded into the score. An establishment that
    # submitted nothing must read as high-risk-low-confidence, not as clean.
    data_completeness: Mapped[float] = mapped_column(Float, nullable=False)
    documents_expected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    findings_by_severity: Mapped[dict] = mapped_column(
        JSONColumn, default=dict, nullable=False
    )
    open_finding_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Advisory signals, counted but not scored.
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Everything needed to reproduce this number: rule pack versions, weights,
    # multipliers, and the finding ids that contributed.
    computation: Mapped[dict] = mapped_column(JSONColumn, default=dict, nullable=False)

    recommended_inspection_priority: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    recommended_inspection_months: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ------------------------------------------------------ reading the number
    # A score on its own invites the wrong reading. 58 because eleven workers were
    # underpaid and 58 because two Codes had no document to test are the same
    # number and completely different situations, and an employer who cannot tell
    # them apart does not know what to fix.
    #
    # `evidence_note` states which Codes were held down by missing evidence rather
    # than by a finding. It is computed, not written by a model, because it is a
    # fact about the arithmetic and there is nothing to judge.
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The model's own reading of the records, carried over from the review that
    # ran before scoring. Explicitly not part of the calculation — it is here so
    # an inspector sees the qualitative picture next to the number instead of
    # having to go digging in the audit trail for it.
    review_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    records_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
