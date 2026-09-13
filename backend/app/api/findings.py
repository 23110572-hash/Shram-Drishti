"""Findings: listing, evidence, and status changes."""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from app.deps import Access, CurrentUser, DbSession, client_ip, require_roles
from app.models.base import utcnow
from app.models.document import Document
from app.models.enums import (
    AuditAction,
    FindingKind,
    FindingStatus,
    LabourCode,
    Role,
    Severity,
    WageRateSource,
)
from app.models.establishment import Establishment
from app.models.finding import Finding
from app.services import audit as audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/findings", tags=["findings"])

#: Status transitions an employer may make. An employer can accept or contest a
#: finding but never close one: only an inspector decides that a breach has been
#: remedied or should be set aside.
EMPLOYER_TRANSITIONS = frozenset({FindingStatus.ACKNOWLEDGED, FindingStatus.DISPUTED})

#: Statuses whose effect is to remove a finding from the score. Each needs a
#: recorded reason, because these are the decisions an audit will question.
REASON_REQUIRED = frozenset(
    {FindingStatus.WAIVED, FindingStatus.FALSE_POSITIVE, FindingStatus.RESOLVED}
)


# ------------------------------------------------------------------- schemas
class EvidenceOut(BaseModel):
    document_id: str | None
    document_filename: str | None
    page_number: int | None
    bbox: list[float] | None
    field_name: str | None
    value_shown: str | None
    row_reference: str | None
    note: str | None
    is_cell_level: bool


class FindingSummary(BaseModel):
    id: str
    establishment_id: str
    establishment_name: str | None
    kind: FindingKind
    code: LabourCode | None
    severity: Severity
    status: FindingStatus
    title: str
    citation: str
    rule_id: str
    rule_verified: bool
    period_start: date | None
    period_end: date | None
    affected_worker_count: int | None
    exposure_paise: int | None
    possible_false_positive: bool
    due_on: date | None
    is_scored: bool
    created_at: str


class FindingDetail(FindingSummary):
    message: str
    remediation: str | None
    explanation: str | None
    false_positive_reason: str | None
    observed: dict[str, Any]
    expected: dict[str, Any]
    rule_pack_version: str
    jurisdiction: str | None
    wage_rate_source: WageRateSource | None
    extraction_confidence: float | None
    status_reason: str | None
    status_changed_at: str | None
    evidence: list[EvidenceOut]


class StatusChangeRequest(BaseModel):
    status: FindingStatus
    reason: str | None = Field(default=None, max_length=2000)


class FindingCounts(BaseModel):
    by_severity: dict[str, int]
    by_kind: dict[str, int]
    by_status: dict[str, int]
    by_code: dict[str, int]
    total: int
    scored_total: int
    advisory_total: int
    unverified_rule_total: int
    total_exposure_paise: int


# ---------------------------------------------------------------------- list
@router.get("", response_model=list[FindingSummary])
def list_findings(
    session: DbSession,
    user: CurrentUser,
    access: Access,
    establishment_id: Annotated[str | None, Query()] = None,
    code: Annotated[LabourCode | None, Query()] = None,
    severity: Annotated[Severity | None, Query()] = None,
    kind: Annotated[FindingKind | None, Query()] = None,
    status_filter: Annotated[FindingStatus | None, Query(alias="status")] = None,
    open_only: Annotated[bool, Query()] = False,
    scored_only: Annotated[bool, Query()] = False,
    period_start: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FindingSummary]:
    query = _scoped_query(session, user)

    if establishment_id:
        establishment = session.get(Establishment, establishment_id)
        if establishment is None:
            raise HTTPException(status_code=404, detail="establishment not found")
        access.assert_can_access(establishment)
        query = query.where(Finding.establishment_id == establishment_id)

    if code:
        query = query.where(Finding.code == code)
    if severity:
        query = query.where(Finding.severity == severity)
    if kind:
        query = query.where(Finding.kind == kind)
    if status_filter:
        query = query.where(Finding.status == status_filter)
    if period_start:
        query = query.where(Finding.period_start == period_start)
    if open_only:
        query = query.where(
            Finding.status.in_(
                [
                    FindingStatus.OPEN,
                    FindingStatus.ACKNOWLEDGED,
                    FindingStatus.DISPUTED,
                ]
            )
        )
    if scored_only:
        # Excludes advisory signals. An employer reviewing what actually affects
        # their score should not have to sift statistical observations out of it.
        query = query.where(Finding.kind != FindingKind.ANOMALY)

    # Ordered by the severity that matters, then by how many workers it touches.
    # Alphabetical or chronological ordering would bury a critical finding
    # affecting two hundred workers under a missing canteen record.
    query = query.order_by(
        _severity_order(),
        desc(func.coalesce(Finding.affected_worker_count, 0)),
        desc(Finding.created_at),
    )

    findings = list(session.execute(query.limit(limit).offset(offset)).scalars().all())
    names = _establishment_names(session, findings)
    return [_summary(f, names) for f in findings]


@router.get("/counts", response_model=FindingCounts)
def count_findings(
    session: DbSession,
    user: CurrentUser,
    access: Access,
    establishment_id: Annotated[str | None, Query()] = None,
    open_only: Annotated[bool, Query()] = True,
) -> FindingCounts:
    """Aggregate counts for dashboards.

    Scored and advisory totals are reported separately and never summed into one
    headline. A count that mixed them would let a run of statistical observations
    look like a compliance problem.
    """
    query = _scoped_query(session, user)

    if establishment_id:
        establishment = session.get(Establishment, establishment_id)
        if establishment is None:
            raise HTTPException(status_code=404, detail="establishment not found")
        access.assert_can_access(establishment)
        query = query.where(Finding.establishment_id == establishment_id)

    if open_only:
        query = query.where(
            Finding.status.in_(
                [
                    FindingStatus.OPEN,
                    FindingStatus.ACKNOWLEDGED,
                    FindingStatus.DISPUTED,
                ]
            )
        )

    findings = list(session.execute(query).scalars().all())

    by_severity: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_code: dict[str, int] = {}
    exposure = 0

    for finding in findings:
        by_severity[finding.severity.value] = by_severity.get(finding.severity.value, 0) + 1
        by_kind[finding.kind.value] = by_kind.get(finding.kind.value, 0) + 1
        by_status[finding.status.value] = by_status.get(finding.status.value, 0) + 1
        key = finding.code.value if finding.code else "UNSPECIFIED"
        by_code[key] = by_code.get(key, 0) + 1
        exposure += finding.exposure_paise or 0

    advisory = sum(1 for f in findings if f.kind is FindingKind.ANOMALY)

    return FindingCounts(
        by_severity=by_severity,
        by_kind=by_kind,
        by_status=by_status,
        by_code=by_code,
        total=len(findings),
        scored_total=sum(1 for f in findings if f.is_scored),
        advisory_total=advisory,
        unverified_rule_total=sum(1 for f in findings if not f.rule_verified),
        total_exposure_paise=exposure,
    )


@router.get("/{finding_id}", response_model=FindingDetail)
def get_finding(
    finding_id: str,
    session: DbSession,
    user: CurrentUser,
    access: Access,
    ip: Annotated[str | None, Depends(client_ip)],
) -> FindingDetail:
    finding = _load(session, finding_id, user, access)

    filenames = dict(
        session.execute(
            select(Document.id, Document.original_filename).where(
                Document.id.in_(
                    [e.document_id for e in finding.evidence if e.document_id]
                )
            )
        ).all()
    )

    # Evidence points at named workers' pay records, so opening a finding is a
    # worker-record read and is logged with its purpose.
    audit_service.record(
        session,
        action=AuditAction.WORKER_RECORD_READ,
        subject_type="finding",
        subject_id=finding.id,
        actor_id=user.id,
        actor_role=str(user.role),
        actor_ip=ip,
        establishment_id=finding.establishment_id,
        purpose="reviewing a compliance finding and its supporting evidence",
    )
    session.commit()

    names = _establishment_names(session, [finding])
    summary = _summary(finding, names)

    return FindingDetail(
        **summary.model_dump(),
        message=finding.message,
        remediation=finding.remediation,
        explanation=finding.explanation,
        false_positive_reason=finding.false_positive_reason,
        observed=dict(finding.observed or {}),
        expected=dict(finding.expected or {}),
        rule_pack_version=finding.rule_pack_version,
        jurisdiction=finding.jurisdiction,
        wage_rate_source=finding.wage_rate_source,
        extraction_confidence=finding.extraction_confidence,
        status_reason=finding.status_reason,
        status_changed_at=(
            finding.status_changed_at.isoformat() if finding.status_changed_at else None
        ),
        evidence=[
            EvidenceOut(
                document_id=e.document_id,
                document_filename=filenames.get(e.document_id) if e.document_id else None,
                page_number=e.page_number,
                bbox=e.bbox,
                field_name=e.field_name,
                value_shown=e.value_shown,
                row_reference=e.row_reference,
                note=e.note,
                is_cell_level=e.is_cell_level,
            )
            for e in finding.evidence
        ],
    )


# -------------------------------------------------------------------- status
@router.post("/{finding_id}/status", response_model=FindingDetail)
def change_status(
    finding_id: str,
    payload: StatusChangeRequest,
    session: DbSession,
    user: CurrentUser,
    access: Access,
    ip: Annotated[str | None, Depends(client_ip)],
) -> FindingDetail:
    """Change a finding's status.

    Who may do what is enforced here rather than in the UI. An employer can
    acknowledge or dispute; only an inspector or administrator can resolve, waive
    or dismiss, because those remove the finding from the score and that decision
    has to sit with the regulator.
    """
    finding = _load(session, finding_id, user, access)

    if user.role is Role.EMPLOYER and payload.status not in EMPLOYER_TRANSITIONS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "an employer may acknowledge or dispute a finding; resolving, "
                "waiving or dismissing it is for the Inspector-cum-Facilitator"
            ),
        )

    if user.role is Role.ANALYST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="analyst accounts are read-only",
        )

    reason = (payload.reason or "").strip()
    if payload.status in REASON_REQUIRED and len(reason) < 10:
        # A waiver with no stated reason is indefensible on review, and this is
        # the point at which the reason is cheapest to capture.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"a reason of at least 10 characters is required to set status "
                f"{payload.status.value}"
            ),
        )

    previous = finding.status
    if previous == payload.status:
        names = _establishment_names(session, [finding])
        return _detail_unchanged(session, finding, names)

    finding.status = payload.status
    finding.status_reason = reason or None
    finding.status_changed_at = utcnow()
    finding.status_changed_by_id = user.id

    action = (
        AuditAction.FINDING_OVERRIDDEN
        if payload.status
        in {FindingStatus.WAIVED, FindingStatus.FALSE_POSITIVE}
        else AuditAction.FINDING_STATUS_CHANGED
    )

    audit_service.record(
        session,
        action=action,
        subject_type="finding",
        subject_id=finding.id,
        actor_id=user.id,
        actor_role=str(user.role),
        actor_ip=ip,
        establishment_id=finding.establishment_id,
        detail={
            "from": previous.value,
            "to": payload.status.value,
            "reason": reason or None,
            "rule_id": finding.rule_id,
            "severity": finding.severity.value,
            "removes_from_score": payload.status not in {
                FindingStatus.OPEN,
                FindingStatus.ACKNOWLEDGED,
                FindingStatus.DISPUTED,
            },
        },
    )
    session.commit()

    names = _establishment_names(session, [finding])
    return _detail_unchanged(session, finding, names)


@router.post(
    "/{finding_id}/escalate",
    response_model=FindingDetail,
    dependencies=[Depends(require_roles(Role.INSPECTOR, Role.ADMIN))],
)
def escalate(
    finding_id: str,
    session: DbSession,
    user: CurrentUser,
    access: Access,
    ip: Annotated[str | None, Depends(client_ip)],
) -> FindingDetail:
    """Mark a finding as escalated past its cure period."""
    finding = _load(session, finding_id, user, access)

    if not finding.is_open:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only an open finding can be escalated",
        )

    finding.escalated_at = utcnow()

    audit_service.record(
        session,
        action=AuditAction.FINDING_STATUS_CHANGED,
        subject_type="finding",
        subject_id=finding.id,
        actor_id=user.id,
        actor_role=str(user.role),
        actor_ip=ip,
        establishment_id=finding.establishment_id,
        detail={
            "action": "escalated",
            "rule_id": finding.rule_id,
            "due_on": finding.due_on.isoformat() if finding.due_on else None,
        },
    )
    session.commit()

    names = _establishment_names(session, [finding])
    return _detail_unchanged(session, finding, names)


# -------------------------------------------------------------------- helpers
def _scoped_query(session: DbSession, user: CurrentUser):
    query = select(Finding)

    if user.role is Role.EMPLOYER:
        owned = (
            select(Establishment.id)
            .where(Establishment.organisation_id == user.organisation_id)
            .scalar_subquery()
        )
        return query.where(Finding.establishment_id.in_(owned))

    if user.role is Role.ADMIN:
        return query

    jurisdictions = set(user.jurisdictions or [])
    if not jurisdictions:
        # Fail closed. An empty scope is no scope.
        return query.where(Finding.id.is_(None))

    return query.where(Finding.jurisdiction.in_(jurisdictions))


def _load(
    session: DbSession, finding_id: str, user: CurrentUser, access: Access
) -> Finding:
    finding = session.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")

    establishment = session.get(Establishment, finding.establishment_id)
    if establishment is None:
        raise HTTPException(status_code=404, detail="finding not found")

    # 404 rather than 403: a 403 would confirm the finding exists, which leaks
    # the existence of establishments outside the caller's scope.
    access.assert_can_access(establishment)
    return finding


def _severity_order():
    from sqlalchemy import case

    return case(
        {
            Severity.CRITICAL.value: 0,
            Severity.HIGH.value: 1,
            Severity.MEDIUM.value: 2,
            Severity.LOW.value: 3,
            Severity.INFO.value: 4,
        },
        value=Finding.severity,
        else_=5,
    )


def _establishment_names(
    session: DbSession, findings: list[Finding]
) -> dict[str, str]:
    ids = {f.establishment_id for f in findings if f.establishment_id}
    if not ids:
        return {}
    return dict(
        session.execute(
            select(Establishment.id, Establishment.name).where(
                Establishment.id.in_(ids)
            )
        ).all()
    )


def _summary(finding: Finding, names: dict[str, str]) -> FindingSummary:
    return FindingSummary(
        id=finding.id,
        establishment_id=finding.establishment_id,
        establishment_name=names.get(finding.establishment_id),
        kind=finding.kind,
        code=finding.code,
        severity=finding.severity,
        status=finding.status,
        title=finding.title,
        citation=finding.citation,
        rule_id=finding.rule_id,
        rule_verified=finding.rule_verified,
        period_start=finding.period_start,
        period_end=finding.period_end,
        affected_worker_count=finding.affected_worker_count,
        exposure_paise=finding.exposure_paise,
        possible_false_positive=finding.possible_false_positive,
        due_on=finding.due_on,
        is_scored=finding.is_scored,
        created_at=finding.created_at.isoformat() if finding.created_at else "",
    )


def _detail_unchanged(
    session: DbSession, finding: Finding, names: dict[str, str]
) -> FindingDetail:
    filenames = dict(
        session.execute(
            select(Document.id, Document.original_filename).where(
                Document.id.in_(
                    [e.document_id for e in finding.evidence if e.document_id]
                )
            )
        ).all()
    )
    summary = _summary(finding, names)
    return FindingDetail(
        **summary.model_dump(),
        message=finding.message,
        remediation=finding.remediation,
        explanation=finding.explanation,
        false_positive_reason=finding.false_positive_reason,
        observed=dict(finding.observed or {}),
        expected=dict(finding.expected or {}),
        rule_pack_version=finding.rule_pack_version,
        jurisdiction=finding.jurisdiction,
        wage_rate_source=finding.wage_rate_source,
        extraction_confidence=finding.extraction_confidence,
        status_reason=finding.status_reason,
        status_changed_at=(
            finding.status_changed_at.isoformat() if finding.status_changed_at else None
        ),
        evidence=[
            EvidenceOut(
                document_id=e.document_id,
                document_filename=filenames.get(e.document_id) if e.document_id else None,
                page_number=e.page_number,
                bbox=e.bbox,
                field_name=e.field_name,
                value_shown=e.value_shown,
                row_reference=e.row_reference,
                note=e.note,
                is_cell_level=e.is_cell_level,
            )
            for e in finding.evidence
        ],
    )
