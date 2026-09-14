"""Alerts to employers and Inspector-cum-Facilitators.

PS5 asks for a system that "alerts employers and Inspector-cum-Facilitators", and
the facilitation framing matters: under the Codes an inspector is meant to help an
employer comply, not only to prosecute. So an employer alert leads with what to
do, gives a cure period, and states the statutory basis so the employer can check
it. It is a notice, not an accusation.

Alerts are persisted, not fired and forgotten. The audit trail has to answer "was
this employer told, and when", because a cure period cannot start from a message
nobody can prove was sent.

Delivery is a queue on the database. There is no SMTP or SMS integration here
because the credentials for those belong to the Ministry, not to this codebase;
``dispatch_pending`` is where a real transport plugs in, and until then the queue
is the record and the API serves it to the UI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.enums import AuditAction, FindingKind, FindingStatus, RiskBand, Severity
from app.models.establishment import Establishment
from app.models.finding import Finding
from app.models.user import User
from app.services import audit as audit_service
from app.services.scorecard import ScoreResult

logger = logging.getLogger(__name__)

#: Days an employer gets to fix an issue before it escalates, by severity.
#: Critical is short because the harm is ongoing — unpaid wages every week, an
#: unguarded machine every shift.
CURE_PERIOD_DAYS: dict[Severity, int] = {
    Severity.CRITICAL: 7,
    Severity.HIGH: 15,
    Severity.MEDIUM: 30,
    Severity.LOW: 45,
    Severity.INFO: 60,
}

#: Bands that put an establishment in front of an inspector without waiting for
#: the routine cycle.
ESCALATION_BANDS = frozenset({RiskBand.HIGH, RiskBand.CRITICAL})


@dataclass
class Alert:
    """One message queued for one recipient."""

    audience: str
    """``employer`` or ``inspector``."""

    channel: str
    """``in_app``, ``email`` or ``sms``. Only ``in_app`` is delivered today."""

    subject: str
    body_en: str
    body_hi: str | None = None
    establishment_id: str | None = None
    recipient_user_id: str | None = None
    severity: Severity = Severity.MEDIUM
    finding_ids: list[str] = field(default_factory=list)
    due_on: date | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def build_alerts(
    session: Session,
    *,
    establishment: Establishment,
    findings: list[Finding],
    score: ScoreResult,
) -> list[Alert]:
    """Compose the alerts arising from one evaluation.

    One digest per audience rather than one message per finding. An employer with
    nineteen findings who receives nineteen notices reads none of them, and an
    inspector needs the establishment ranked against others, not a stream of
    individual items.
    """
    alerts: list[Alert] = []

    # Statistical and model-only observations remain available to inspectors as
    # advisory context, but are never legal compliance notices to employers.
    actionable = [
        finding
        for finding in findings
        if finding.is_scored and finding.status is FindingStatus.OPEN
    ]

    if actionable:
        alerts.append(_employer_notice(establishment, actionable, score))

    if actionable or score.risk_band in ESCALATION_BANDS:
        alerts.extend(_inspector_notices(session, establishment, findings, score))

    if not score.completeness.is_sufficient:
        alerts.append(_completeness_notice(establishment, score))

    return alerts


def record_alerts(
    session: Session,
    alerts: list[Alert],
    *,
    actor_id: str | None = None,
) -> None:
    """Write alerts to the audit log and set cure dates on the findings.

    Auditing rather than a dedicated table: the audit log is already hash-chained
    and append-only, which is exactly what a notice record needs. The dispatch
    date must not be quietly editable, because a cure period runs from it.
    """
    for alert in alerts:
        entry = audit_service.record(
            session,
            action=AuditAction.ALERT_DISPATCHED,
            subject_type="establishment",
            subject_id=alert.establishment_id or "-",
            actor_id=actor_id,
            establishment_id=alert.establishment_id,
            detail={
                "audience": alert.audience,
                "channel": alert.channel,
                "subject": alert.subject,
                "severity": str(alert.severity),
                "finding_ids": alert.finding_ids[:50],
                "recipient_user_id": alert.recipient_user_id,
                "due_on": alert.due_on.isoformat() if alert.due_on else None,
                **alert.detail,
            },
        )
        logger.info(
            "alert queued",
            extra={
                "audit_sequence": entry.sequence,
                "audience": alert.audience,
                "establishment_id": alert.establishment_id,
                "findings": len(alert.finding_ids),
            },
        )

    _apply_cure_periods(session, alerts)


def _apply_cure_periods(session: Session, alerts: list[Alert]) -> None:
    """Set ``due_on`` on findings covered by an employer notice.

    Only set once. Re-running an evaluation must not silently extend a deadline
    the employer has already been given, or a cure period could be renewed
    indefinitely by re-uploading a document.
    """
    finding_ids = {
        finding_id
        for alert in alerts
        if alert.audience == "employer"
        for finding_id in alert.finding_ids
    }
    if not finding_ids:
        return

    findings = (
        session.execute(select(Finding).where(Finding.id.in_(finding_ids)))
        .scalars()
        .all()
    )
    today = date.today()

    for finding in findings:
        if finding.due_on is None:
            finding.due_on = today + timedelta(
                days=CURE_PERIOD_DAYS.get(finding.severity, 30)
            )


def dispatch_pending() -> int:
    """Hook for a real transport.

    Deliberately a no-op. Email and SMS credentials for a government
    notification channel belong to the Ministry's infrastructure, and inventing a
    transport here would produce a component that has to be thrown away. The
    queue is the record; the UI reads it from the audit log.
    """
    return 0


# --------------------------------------------------------------- composition
def _employer_notice(
    establishment: Establishment, findings: list[Finding], score: ScoreResult
) -> Alert:
    ordered = sorted(findings, key=lambda f: _severity_rank(f.severity))
    worst = ordered[0].severity
    cure_days = CURE_PERIOD_DAYS.get(worst, 30)
    due = date.today() + timedelta(days=cure_days)

    counts = _counts(findings)
    lines_en: list[str] = [
        f"Compliance review of {establishment.name}",
        "",
        f"A review of the documents submitted for {establishment.name} has "
        f"identified {len(findings)} matter(s) requiring your attention.",
        "",
        _summary_line(counts),
        "",
        "What needs to be done:",
    ]

    # Remediation before the accusation. The Codes put facilitation before
    # prosecution, and an employer who can see the fix is far more likely to make
    # it than one who receives a list of alleged breaches.
    for finding in ordered[:10]:
        lines_en.append("")
        lines_en.append(f"• {finding.title}")
        lines_en.append(f"  Statutory basis: {finding.citation}")
        if finding.remediation:
            lines_en.append(f"  Action: {finding.remediation}")
        if finding.affected_worker_count:
            lines_en.append(f"  Workers affected: {finding.affected_worker_count}")
        if finding.exposure_paise:
            lines_en.append(
                f"  Amount involved: ₹{finding.exposure_paise / 100:,.2f}"
            )
        if finding.rule_basis.needs_notified_rules:
            # Said plainly. An employer must not be pressed on a number the Act
            # left to a notification that nobody has produced.
            lines_en.append(
                "  Note: the Act leaves the figure applied here to be notified by "
                "the appropriate Government, and that notification has not been "
                "obtained. The figure used is drawn from a secondary source. "
                "Raise this if you believe it does not apply."
            )

    if len(ordered) > 10:
        lines_en.append("")
        lines_en.append(
            f"…and {len(ordered) - 10} further matter(s) listed in the portal."
        )

    lines_en.extend(
        [
            "",
            f"Please respond or correct these by {due.isoformat()}.",
            "",
            "If you believe any of this is based on a misreading of your "
            "documents, mark it as disputed in the portal with an explanation. "
            "Every item links to the exact page and cell it was read from, so a "
            "misreading is straightforward to demonstrate.",
        ]
    )

    body_hi = (
        f"{establishment.name} के लिए प्रस्तुत दस्तावेजों की समीक्षा में "
        f"{len(findings)} विषय पाए गए हैं जिन पर आपका ध्यान आवश्यक है। "
        f"कृपया {due.isoformat()} तक उत्तर दें अथवा सुधार करें। "
        "यदि आपको लगता है कि कोई विषय आपके दस्तावेजों के गलत पठन पर आधारित है, "
        "तो पोर्टल में उसे विवादित चिह्नित करें। प्रत्येक विषय उस पृष्ठ और खाने "
        "से जुड़ा है जहाँ से वह पढ़ा गया है।"
    )

    return Alert(
        audience="employer",
        channel="in_app",
        subject=f"Action required: {len(findings)} compliance matter(s)",
        body_en="\n".join(lines_en),
        body_hi=body_hi,
        establishment_id=establishment.id,
        severity=worst,
        finding_ids=[f.id for f in findings],
        due_on=due,
        detail={
            "risk_band": str(score.risk_band),
            "overall_score": score.overall_score,
            "cure_period_days": cure_days,
        },
    )


def _inspector_notices(
    session: Session,
    establishment: Establishment,
    findings: list[Finding],
    score: ScoreResult,
) -> list[Alert]:
    """One notice per inspector whose jurisdiction covers this establishment."""
    inspectors = _inspectors_for(session, establishment.jurisdiction_code)
    if not inspectors:
        logger.warning(
            "no inspector is assigned to this jurisdiction, so no inspector "
            "alert could be addressed",
            extra={
                "establishment_id": establishment.id,
                "jurisdiction": establishment.jurisdiction_code,
            },
        )
        return []

    scored = [finding for finding in findings if finding.is_scored]
    anomalies = [
        finding
        for finding in findings
        if finding.is_open
        and (
            finding.kind is FindingKind.ANOMALY
            or finding.rule_id == "MODEL.OBSERVATION"
        )
    ]
    counts = _counts(scored)

    lines = [
        f"{establishment.name} — {score.headline}",
        "",
        f"State: {establishment.state_code}"
        + (f", district {establishment.district}" if establishment.district else ""),
        f"Workers on record: {establishment.worker_count}"
        + (
            f" (peak {establishment.worker_count_peak_12m} in the last 12 months)"
            if establishment.worker_count_peak_12m > establishment.worker_count
            else ""
        ),
        f"Recommended inspection priority: {score.inspection_priority}/100",
        f"Suggested inspection interval: {score.inspection_interval_months} months",
        "",
        _summary_line(counts),
        "",
        f"Evidence assessable: {score.completeness.overall:.0f}% "
        f"({score.completeness.documents_received} of "
        f"{score.completeness.documents_expected} expected documents, "
        f"{score.completeness.rule_coverage:.0%} of applicable rules assessable)",
    ]

    if not score.completeness.is_sufficient:
        lines.extend(
            [
                "",
                "Caution: this score rests on incomplete evidence. A low finding "
                "count here does not indicate compliance — most rules could not "
                "be assessed at all.",
            ]
        )

    exposure = sum(f.exposure_paise or 0 for f in scored)
    if exposure:
        lines.extend(["", f"Quantified amount at stake: ₹{exposure / 100:,.2f}"])

    pending = [f for f in scored if f.rule_basis.needs_notified_rules]
    if pending:
        lines.extend(
            [
                "",
                f"{len(pending)} of these findings rest on a figure the Act leaves "
                "to the appropriate Government to notify, where that notification "
                "has not been obtained. They are shown for information and should "
                "not be enforced without checking the notified Rules.",
            ]
        )

    if anomalies:
        lines.extend(
            [
                "",
                f"{len(anomalies)} advisory signal(s) were also raised. These are "
                "statistical or pattern observations, not breaches of law, and do "
                "not affect the score:",
            ]
        )
        for anomaly in anomalies[:5]:
            lines.append(f"• {anomaly.title}")

    top = sorted(scored, key=lambda f: _severity_rank(f.severity))[:8]
    if top:
        lines.extend(["", "Most serious findings:"])
        for finding in top:
            affected = (
                f", {finding.affected_worker_count} worker(s)"
                if finding.affected_worker_count
                else ""
            )
            lines.append(
                f"• [{finding.severity.value}] {finding.title} — "
                f"{finding.citation}{affected}"
            )

    body = "\n".join(lines)

    return [
        Alert(
            audience="inspector",
            channel="in_app",
            subject=(
                f"{establishment.name}: {score.risk_band.value.lower()} risk, "
                f"{len(scored)} finding(s)"
            ),
            body_en=body,
            establishment_id=establishment.id,
            recipient_user_id=inspector.id,
            severity=_worst_severity(scored),
            finding_ids=[f.id for f in scored],
            detail={
                "risk_band": str(score.risk_band),
                "overall_score": score.overall_score,
                "inspection_priority": score.inspection_priority,
                "data_completeness": score.completeness.overall,
                "anomaly_count": len(anomalies),
            },
        )
        for inspector in inspectors
    ]


def _completeness_notice(
    establishment: Establishment, score: ScoreResult
) -> Alert:
    """Tell the employer what is missing.

    Sent separately from the findings notice and always sent when evidence is
    thin, because an establishment that submits nothing must be chased rather
    than quietly recorded as having no findings.
    """
    missing = (
        score.completeness.documents_expected - score.completeness.documents_received
    )

    body = "\n".join(
        [
            f"Documents outstanding for {establishment.name}",
            "",
            f"{missing} of {score.completeness.documents_expected} expected "
            "document types have not been submitted for this period, and "
            f"{score.completeness.rule_coverage:.0%} of the applicable checks "
            "could be run.",
            "",
            "Until these are provided, compliance cannot be assessed. An "
            "incomplete submission is recorded as unverified, not as compliant, "
            "and raises the priority for a physical inspection.",
            "",
            "The portal lists exactly which document types are outstanding.",
        ]
    )

    body_hi = (
        f"{establishment.name} के लिए इस अवधि के "
        f"{score.completeness.documents_expected} अपेक्षित दस्तावेज प्रकारों में से "
        f"{missing} प्रस्तुत नहीं किए गए हैं। जब तक ये उपलब्ध नहीं होते, अनुपालन का "
        "मूल्यांकन संभव नहीं है। अपूर्ण प्रस्तुति को अनुपालित नहीं, अपुष्ट दर्ज किया "
        "जाता है।"
    )

    return Alert(
        audience="employer",
        channel="in_app",
        subject=f"{missing} document type(s) outstanding",
        body_en=body,
        body_hi=body_hi,
        establishment_id=establishment.id,
        severity=Severity.MEDIUM,
        detail={
            "documents_expected": score.completeness.documents_expected,
            "documents_received": score.completeness.documents_received,
            "rule_coverage": score.completeness.rule_coverage,
        },
    )


# -------------------------------------------------------------------- helpers
def _inspectors_for(session: Session, jurisdiction: str) -> list[User]:
    from app.models.enums import Role

    users = (
        session.execute(
            select(User).where(
                User.role == Role.INSPECTOR, User.is_active.is_(True)
            )
        )
        .scalars()
        .all()
    )
    # Jurisdictions are a JSON array, so filtering happens in Python. Fine at this
    # scale, and an empty list means no scope rather than all scope — the same
    # fail-closed rule the access layer applies.
    return [
        user for user in users if jurisdiction in set(user.jurisdictions or [])
    ]


def _severity_rank(severity: Severity) -> int:
    return {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFO: 4,
    }[severity]


def _worst_severity(findings: list[Finding]) -> Severity:
    if not findings:
        return Severity.INFO
    return min((f.severity for f in findings), key=_severity_rank)


def _counts(findings: list[Finding]) -> dict[Severity, int]:
    counts: dict[Severity, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def _summary_line(counts: dict[Severity, int]) -> str:
    if not counts:
        return "No findings were raised."
    parts = [
        f"{counts[severity]} {severity.value.lower()}"
        for severity in Severity
        if counts.get(severity)
    ]
    return "Summary: " + ", ".join(parts) + "."
