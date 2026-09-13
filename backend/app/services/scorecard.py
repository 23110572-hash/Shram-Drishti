"""Risk-based compliance scoring.

The scorecard exists so an inspectorate with a few hundred officers and millions
of establishments can decide where to go first. That makes it a resource
allocation tool, and it has to be honest about its own limits.

Four design decisions carry most of the weight.

**Completeness is never folded into the score.** An establishment that submitted
nothing would otherwise score perfectly, having broken no rule that could be
tested. That is the single most dangerous failure available to a compliance
system, because it rewards non-submission. So completeness is a separate number,
reported beside the score, and an establishment with high completeness and a
clean score is a genuinely different thing from one with no data at all.

**Anomalies never score.** They are advisory signals for an inspector. A
statistical outlier is not a breach of law and cannot be defended as one.

**Exposure counts, not just severity.** A medium finding affecting two hundred
workers matters more than a high one affecting a single worker, and severity alone
cannot express that. Affected headcount scales a finding's contribution.

**The computation is stored.** Every scorecard keeps its weights, inputs and the
finding ids that produced it, so any historical score can be recomputed exactly
and a rule pack change cannot silently rewrite the past.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.enums import (
    AuditAction,
    DocumentType,
    FindingKind,
    LabourCode,
    RiskBand,
    Severity,
)
from app.models.establishment import Establishment
from app.models.finding import Finding, Scorecard
from app.services import audit as audit_service
from app.services.rule_engine import EvaluationReport, is_scored, severity_weight

logger = logging.getLogger(__name__)

SCORING_VERSION = "1.0"

#: Relative importance of each Code in the overall score. Wages and social
#: security are weighted highest because their breaches take money directly out
#: of a worker's hands and are the hardest for that worker to recover alone.
CODE_WEIGHTS: dict[LabourCode, float] = {
    LabourCode.WAGES: 0.35,
    LabourCode.SOCIAL_SECURITY: 0.30,
    LabourCode.OSH: 0.25,
    LabourCode.INDUSTRIAL_RELATIONS: 0.10,
}

#: Score boundaries. A single critical finding should not leave an establishment
#: in the low-risk band, so the bands are set where the severity weights put a
#: critical breach beyond MEDIUM on its own.
BAND_THRESHOLDS: tuple[tuple[float, RiskBand], ...] = (
    (85.0, RiskBand.LOW),
    (70.0, RiskBand.MEDIUM),
    (50.0, RiskBand.HIGH),
    (0.0, RiskBand.CRITICAL),
)

#: Months between routine inspections, by band. The point of the whole exercise:
#: a compliant employer is left alone and the officer's time goes where the risk is.
INSPECTION_INTERVAL_MONTHS: dict[RiskBand, int] = {
    RiskBand.LOW: 36,
    RiskBand.MEDIUM: 24,
    RiskBand.HIGH: 12,
    RiskBand.CRITICAL: 3,
}

#: Documents expected from every establishment for a wage period. Used only for
#: the completeness figure, never to raise a finding — the missing-document rules
#: do that, with citations.
CORE_EXPECTED_DOCUMENTS: tuple[DocumentType, ...] = (
    DocumentType.EMPLOYEE_REGISTER,
    DocumentType.WAGE_REGISTER,
    DocumentType.MUSTER_ROLL,
    DocumentType.WAGE_SLIP,
    DocumentType.EPF_ECR,
    DocumentType.ESIC_CHALLAN,
)

#: How much a finding's affected headcount can amplify it. Logarithmic, so scale
#: registers without one large establishment's arithmetic swamping everything: two
#: hundred affected workers weigh roughly three times one.
MAX_SCALE_MULTIPLIER = 3.0


@dataclass
class CodeScore:
    code: LabourCode
    score: float
    penalty: float
    finding_count: int
    critical_count: int = 0
    weight: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "penalty": round(self.penalty, 2),
            "findings": self.finding_count,
            "critical": self.critical_count,
            "weight": self.weight,
        }


@dataclass
class Completeness:
    """How much of the expected evidence actually arrived.

    ``rule_coverage`` is the more honest of the two numbers: an establishment can
    submit every document and still be unassessable if the documents are illegible.
    """

    documents_expected: int
    documents_received: int
    rule_coverage: float
    unassessable_rules: int = 0
    documents_needing_review: int = 0

    @property
    def document_share(self) -> float:
        if self.documents_expected <= 0:
            return 0.0
        return min(1.0, self.documents_received / self.documents_expected)

    @property
    def overall(self) -> float:
        """Weighted towards rule coverage, which is what actually limits judgement."""
        return round(100 * (0.4 * self.document_share + 0.6 * self.rule_coverage), 1)

    @property
    def is_sufficient(self) -> bool:
        """Whether a clean score means anything at all."""
        return self.document_share >= 0.6 and self.rule_coverage >= 0.6


@dataclass
class ScoreResult:
    overall_score: float
    risk_band: RiskBand
    code_scores: dict[LabourCode, CodeScore]
    completeness: Completeness
    findings_by_severity: dict[Severity, int]
    open_finding_count: int
    anomaly_count: int
    computation: dict[str, Any] = field(default_factory=dict)
    inspection_priority: int = 0
    inspection_interval_months: int = 24

    @property
    def headline(self) -> str:
        """One line for a list view, honest about confidence."""
        if not self.completeness.is_sufficient:
            return (
                f"{self.overall_score:.0f} / 100 — {self.risk_band.value.lower()} "
                f"risk, but only {self.completeness.overall:.0f}% of the expected "
                "evidence was assessable"
            )
        return f"{self.overall_score:.0f} / 100 — {self.risk_band.value.lower()} risk"


def compute_score(
    session: Session,
    *,
    establishment: Establishment,
    period_start: date | None,
    period_end: date | None,
    report: EvaluationReport | None = None,
) -> ScoreResult:
    """Score one establishment for one period from its current findings."""
    findings = _findings(session, establishment.id, period_start, period_end)

    scored = [f for f in findings if is_scored(f)]
    anomalies = [f for f in findings if f.kind is FindingKind.ANOMALY]

    code_scores: dict[LabourCode, CodeScore] = {}
    contributing: dict[str, list[str]] = {}

    for code in LabourCode:
        relevant = [f for f in scored if f.code is code]
        penalty = 0.0
        critical = 0

        for finding in relevant:
            weight = severity_weight(finding.severity)
            if weight == 0:
                continue

            scale = _scale_multiplier(finding.affected_worker_count)

            # A finding built on a marginal scan should not carry the same weight
            # as one read off a clean digital PDF. Confidence is a discount, never
            # a bonus: an unknown confidence is treated as full weight so a
            # missing measurement cannot help an employer.
            confidence = finding.extraction_confidence
            discount = 1.0 if confidence is None else 0.6 + 0.4 * confidence

            # A rule whose threshold is not yet confirmed against primary
            # statutory text is shown to inspectors but weighed lightly, because
            # enforcing on an unverified number is not defensible.
            verification = 1.0 if finding.rule_verified else 0.4

            penalty += weight * scale * discount * verification
            if finding.severity is Severity.CRITICAL:
                critical += 1

        # Diminishing returns. Twenty findings is not twice as bad as ten: both
        # are an establishment in serious trouble, and a linear scale would make
        # the worst cases indistinguishable from each other.
        score = 100.0 * math.exp(-penalty / 120.0)

        code_scores[code] = CodeScore(
            code=code,
            score=round(max(0.0, min(100.0, score)), 1),
            penalty=round(penalty, 2),
            finding_count=len(relevant),
            critical_count=critical,
            weight=CODE_WEIGHTS[code],
        )
        contributing[code.value] = [f.id for f in relevant]

    overall = sum(
        code_scores[code].score * CODE_WEIGHTS[code] for code in LabourCode
    )

    # A critical breach anywhere caps the overall score. Without this, a large
    # establishment compliant across three Codes could average away an unnotified
    # fatality or systematic underpayment, and the number would be a lie.
    critical_total = sum(cs.critical_count for cs in code_scores.values())
    if critical_total:
        overall = min(overall, 45.0)

    completeness = _completeness(session, establishment, period_start, period_end, report)

    band = _band(overall)
    priority = _priority(overall, critical_total, completeness)

    result = ScoreResult(
        overall_score=round(max(0.0, min(100.0, overall)), 1),
        risk_band=band,
        code_scores=code_scores,
        completeness=completeness,
        findings_by_severity=_by_severity(scored),
        open_finding_count=len([f for f in findings if f.is_open]),
        anomaly_count=len(anomalies),
        inspection_priority=priority,
        inspection_interval_months=INSPECTION_INTERVAL_MONTHS[band],
    )

    result.computation = {
        "scoring_version": SCORING_VERSION,
        "code_weights": {code.value: weight for code, weight in CODE_WEIGHTS.items()},
        "severity_weights": {
            severity.value: severity_weight(severity) for severity in Severity
        },
        "decay_constant": 120.0,
        "max_scale_multiplier": MAX_SCALE_MULTIPLIER,
        "critical_score_cap": 45.0 if critical_total else None,
        "per_code": {
            code.value: score.as_dict() for code, score in code_scores.items()
        },
        "contributing_findings": contributing,
        "excluded_anomalies": [f.id for f in anomalies],
        "rule_pack_versions": sorted(
            {f.rule_pack_version for f in findings if f.rule_pack_version}
        ),
        "completeness": {
            "documents_expected": completeness.documents_expected,
            "documents_received": completeness.documents_received,
            "document_share": round(completeness.document_share, 3),
            "rule_coverage": completeness.rule_coverage,
            "unassessable_rules": completeness.unassessable_rules,
            "documents_needing_review": completeness.documents_needing_review,
            "is_sufficient": completeness.is_sufficient,
        },
        "period": {
            "start": period_start.isoformat() if period_start else None,
            "end": period_end.isoformat() if period_end else None,
        },
    }

    return result


def persist_score(
    session: Session,
    *,
    establishment: Establishment,
    period_start: date | None,
    period_end: date | None,
    result: ScoreResult,
    actor_id: str | None = None,
) -> Scorecard:
    """Write a new scorecard row.

    Always an insert. Scorecards are never updated in place, so an establishment's
    trajectory over time is preserved and a past score cannot be quietly restated.
    """
    scorecard = Scorecard(
        establishment_id=establishment.id,
        computed_at=utcnow(),
        period_start=period_start,
        period_end=period_end,
        overall_score=result.overall_score,
        risk_band=result.risk_band,
        code_scores={
            code.value: score.score for code, score in result.code_scores.items()
        },
        data_completeness=result.completeness.overall,
        documents_expected=result.completeness.documents_expected,
        documents_received=result.completeness.documents_received,
        findings_by_severity={
            severity.value: count
            for severity, count in result.findings_by_severity.items()
        },
        open_finding_count=result.open_finding_count,
        anomaly_count=result.anomaly_count,
        computation=result.computation,
        recommended_inspection_priority=result.inspection_priority,
        recommended_inspection_months=result.inspection_interval_months,
    )
    session.add(scorecard)
    session.flush()

    audit_service.record(
        session,
        action=AuditAction.SCORE_COMPUTED,
        subject_type="scorecard",
        subject_id=scorecard.id,
        actor_id=actor_id,
        establishment_id=establishment.id,
        detail={
            "overall_score": result.overall_score,
            "risk_band": str(result.risk_band),
            "data_completeness": result.completeness.overall,
            "open_findings": result.open_finding_count,
            "scoring_version": SCORING_VERSION,
        },
    )

    logger.info(
        "scorecard computed",
        extra={
            "establishment_id": establishment.id,
            "score": result.overall_score,
            "band": str(result.risk_band),
            "completeness": result.completeness.overall,
        },
    )
    return scorecard


def latest_scorecard(session: Session, establishment_id: str) -> Scorecard | None:
    return session.execute(
        select(Scorecard)
        .where(Scorecard.establishment_id == establishment_id)
        .order_by(Scorecard.computed_at.desc())
        .limit(1)
    ).scalar_one_or_none()


# -------------------------------------------------------------------- helpers
def _findings(
    session: Session,
    establishment_id: str,
    period_start: date | None,
    period_end: date | None,
) -> list[Finding]:
    query = select(Finding).where(Finding.establishment_id == establishment_id)
    if period_start is not None:
        query = query.where(Finding.period_start == period_start)
    if period_end is not None:
        query = query.where(Finding.period_end == period_end)
    return list(session.execute(query).scalars().all())


def _scale_multiplier(affected: int | None) -> float:
    """How much affected headcount amplifies a finding.

    Logarithmic and capped. One affected worker is 1.0, ten is about 1.8, two
    hundred is capped at 3.0. Linear scaling would let a single large employer's
    arithmetic dominate a national ranking; no scaling at all would treat
    systematic underpayment of two hundred workers as one incident.
    """
    if not affected or affected <= 1:
        return 1.0
    return min(MAX_SCALE_MULTIPLIER, 1.0 + math.log10(affected))


def _band(score: float) -> RiskBand:
    for threshold, band in BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return RiskBand.CRITICAL


def _priority(score: float, critical_count: int, completeness: Completeness) -> int:
    """Inspection priority, 0-100. Higher means visit sooner.

    Low completeness raises priority rather than lowering it. An establishment
    that submits nothing must not be able to hide behind an untestable clean
    score — non-submission is itself a reason to visit.
    """
    priority = 100.0 - score
    priority += 15 * min(critical_count, 3)

    if not completeness.is_sufficient:
        priority += 20 * (1 - completeness.overall / 100)

    if completeness.documents_received == 0:
        priority = max(priority, 85.0)

    return int(max(0, min(100, round(priority))))


def _by_severity(findings: list[Finding]) -> dict[Severity, int]:
    counts = dict.fromkeys(Severity, 0)
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def _completeness(
    session: Session,
    establishment: Establishment,
    period_start: date | None,
    period_end: date | None,
    report: EvaluationReport | None,
) -> Completeness:
    from app.models.document import Document
    from app.models.enums import DocumentStatus

    expected = list(CORE_EXPECTED_DOCUMENTS)

    # Conditional expectations, so an establishment is not marked incomplete for
    # failing to submit a document it has no obligation to hold.
    if establishment.worker_count_peak_12m >= 300:
        expected.append(DocumentType.STANDING_ORDERS)
    if establishment.worker_count >= 20:
        expected.append(DocumentType.GRIEVANCE_COMMITTEE_RECORD)
    if establishment.engages_contract_labour:
        expected.append(DocumentType.CONTRACTOR_LICENCE)
    if establishment.has_hazardous_process:
        expected.append(DocumentType.HEALTH_CHECKUP_RECORD)
    if establishment.is_factory or establishment.is_construction:
        expected.append(DocumentType.ACCIDENT_REGISTER)

    query = select(Document).where(
        Document.establishment_id == establishment.id,
        Document.status.in_(
            [
                DocumentStatus.EXTRACTED,
                DocumentStatus.NEEDS_REVIEW,
                DocumentStatus.VERIFIED,
                DocumentStatus.EVALUATED,
            ]
        ),
    )
    if period_end is not None:
        query = query.where(Document.period_start <= period_end)
    if period_start is not None:
        query = query.where(Document.period_end >= period_start)

    documents = list(session.execute(query).scalars().all())
    present_types = {d.doc_type for d in documents}

    received = sum(1 for doc_type in expected if doc_type in present_types)

    return Completeness(
        documents_expected=len(expected),
        documents_received=received,
        rule_coverage=report.coverage if report is not None else 0.0,
        unassessable_rules=report.rules_unassessable if report is not None else 0,
        documents_needing_review=sum(
            1 for d in documents if d.status is DocumentStatus.NEEDS_REVIEW
        ),
    )
