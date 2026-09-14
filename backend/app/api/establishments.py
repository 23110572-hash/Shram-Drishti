"""Establishments, scorecards and the inspection worklist."""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from app.deps import Access, CurrentUser, DbSession, require_roles
from app.models.document import Document
from app.models.enums import (
    DocumentStatus,
    DocumentType,
    FindingKind,
    FindingStatus,
    LabourCode,
    RiskBand,
    Role,
    Severity,
    SkillCategory,
)
from app.models.establishment import Contractor, Establishment, MinimumWageRate, Registration
from app.models.finding import Finding, Scorecard
from app.services import jobs as job_service
from app.services.wage_rates import lookup_rate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/establishments", tags=["establishments"])


# ------------------------------------------------------------------- schemas
class EstablishmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    state_code: str = Field(min_length=2, max_length=8)
    lin: str | None = Field(default=None, max_length=32)
    district: str | None = Field(default=None, max_length=128)
    wage_zone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=512)
    nic_code: str | None = Field(default=None, max_length=16)
    sector: str | None = Field(default=None, max_length=128)

    worker_count: int = Field(default=0, ge=0)
    worker_count_peak_12m: int = Field(default=0, ge=0)
    women_worker_count: int = Field(default=0, ge=0)
    contract_worker_count: int = Field(default=0, ge=0)
    interstate_migrant_count: int = Field(default=0, ge=0)

    is_factory: bool = False
    is_mine: bool = False
    is_plantation: bool = False
    is_construction: bool = False
    has_hazardous_process: bool = False
    engages_contract_labour: bool = False
    has_night_shift: bool = False

    commenced_on: date | None = None


class RegistrationOut(BaseModel):
    id: str
    kind: str
    number: str
    issuing_authority: str | None
    valid_from: date | None
    valid_to: date | None
    is_current: bool


class ContractorOut(BaseModel):
    id: str
    name: str
    licence_number: str | None
    licence_valid_to: date | None
    licensed_worker_count: int | None
    deployed_worker_count: int
    is_over_deployed: bool


class ScorecardOut(BaseModel):
    id: str
    computed_at: str
    period_start: date | None
    period_end: date | None
    overall_score: float
    risk_band: RiskBand
    code_scores: dict[str, float]
    data_completeness: float
    documents_expected: int
    documents_received: int
    expected_document_types: list[DocumentType] | None
    present_document_types: list[DocumentType] | None
    missing_document_types: list[DocumentType] | None
    findings_by_severity: dict[str, int]
    open_finding_count: int
    anomaly_count: int
    recommended_inspection_priority: int | None
    recommended_inspection_months: int | None
    #: True when the score rests on enough evidence to mean anything. A clean
    #: score on thin evidence is not compliance and must not be presented as such.
    evidence_sufficient: bool
    #: Set when part of the score reflects Codes that could not be assessed rather
    #: than anything found. Without this an employer cannot tell a low score earned
    #: by breaches from one caused by documents they never sent.
    evidence_note: str | None
    #: The model's reading of the records, from the review that ran before scoring.
    #: Never part of the calculation.
    review_summary: str | None
    records_quality: str | None
    computation: dict[str, Any] | None = None


class EstablishmentSummary(BaseModel):
    id: str
    name: str
    lin: str | None
    state_code: str
    district: str | None
    sector: str | None
    worker_count: int
    worker_count_peak_12m: int
    is_active: bool
    latest_score: float | None
    risk_band: RiskBand | None
    data_completeness: float | None
    open_finding_count: int
    critical_finding_count: int
    inspection_priority: int | None
    last_evaluated_at: str | None


class EstablishmentDetail(EstablishmentSummary):
    address: str | None
    wage_zone: str | None
    nic_code: str | None
    women_worker_count: int
    contract_worker_count: int
    interstate_migrant_count: int
    is_factory: bool
    is_mine: bool
    is_plantation: bool
    is_construction: bool
    has_hazardous_process: bool
    engages_contract_labour: bool
    has_night_shift: bool
    commenced_on: date | None
    jurisdiction_code: str
    registrations: list[RegistrationOut]
    contractors: list[ContractorOut]
    latest_scorecard: ScorecardOut | None
    document_counts: dict[str, int]
    applicable_thresholds: dict[str, Any]
    minimum_wage: dict[str, Any]


class WorklistItem(BaseModel):
    establishment: EstablishmentSummary
    reason: str
    priority: int


class EvaluateRequest(BaseModel):
    period_start: date
    period_end: date


# ---------------------------------------------------------------------- list
@router.get("", response_model=list[EstablishmentSummary])
def list_establishments(
    session: DbSession,
    user: CurrentUser,
    band: Annotated[RiskBand | None, Query()] = None,
    state_code: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EstablishmentSummary]:
    query = _scoped(select(Establishment), user).order_by(Establishment.name)

    if state_code:
        query = query.where(Establishment.state_code == state_code.upper())
    if search:
        query = query.where(Establishment.name.ilike(f"%{search}%"))

    establishments = list(
        session.execute(query.limit(limit).offset(offset)).scalars().all()
    )
    summaries = _summaries(session, establishments)

    if band:
        summaries = [s for s in summaries if s.risk_band is band]

    return summaries


@router.get("/worklist", response_model=list[WorklistItem])
def worklist(
    session: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[WorklistItem]:
    """Establishments ranked for inspection.

    The output the whole system exists to produce. Ranked by recommended priority
    rather than by score, because priority already folds in evidence
    completeness — an establishment that submitted nothing rises up the list
    instead of sitting at the top of the rankings with an untested clean score.
    """
    if user.role not in {Role.INSPECTOR, Role.ADMIN, Role.ANALYST}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="the worklist is for inspectors and administrators",
        )

    establishments = list(
        session.execute(_scoped(select(Establishment), user).where(
            Establishment.is_active.is_(True)
        )).scalars().all()
    )
    if not establishments:
        return []

    summaries = _summaries(session, establishments)
    items: list[WorklistItem] = []

    for summary in summaries:
        priority = summary.inspection_priority
        if priority is None:
            # Never evaluated. That is not a clean record, it is an unknown one,
            # and an unknown establishment is a legitimate inspection target.
            items.append(
                WorklistItem(
                    establishment=summary,
                    reason="never assessed — no documents have been submitted",
                    priority=90,
                )
            )
            continue

        reasons = []
        if summary.critical_finding_count:
            reasons.append(f"{summary.critical_finding_count} critical finding(s)")
        if summary.data_completeness is not None and summary.data_completeness < 60:
            reasons.append(
                f"only {summary.data_completeness:.0f}% of expected evidence assessable"
            )
        if summary.open_finding_count:
            reasons.append(f"{summary.open_finding_count} open finding(s)")
        if summary.risk_band in {RiskBand.HIGH, RiskBand.CRITICAL}:
            reasons.append(f"{summary.risk_band.value.lower()} risk band")

        items.append(
            WorklistItem(
                establishment=summary,
                reason="; ".join(reasons) or "routine cycle",
                priority=priority,
            )
        )

    items.sort(key=lambda item: item.priority, reverse=True)
    return items[:limit]


@router.get("/{establishment_id}", response_model=EstablishmentDetail)
def get_establishment(
    establishment_id: str,
    session: DbSession,
    access: Access,
) -> EstablishmentDetail:
    establishment = session.get(Establishment, establishment_id)
    if establishment is None:
        raise HTTPException(status_code=404, detail="establishment not found")
    access.assert_can_access(establishment)

    summary = _summaries(session, [establishment])[0]
    scorecard = _latest_scorecard(session, establishment.id)
    today = date.today()

    document_counts: dict[str, int] = {}
    for doc_type, count in session.execute(
        select(Document.doc_type, func.count())
        .where(
            Document.establishment_id == establishment.id,
            Document.status != DocumentStatus.REJECTED,
        )
        .group_by(Document.doc_type)
    ).all():
        document_counts[str(doc_type)] = int(count)

    return EstablishmentDetail(
        **summary.model_dump(),
        address=establishment.address,
        wage_zone=establishment.wage_zone,
        nic_code=establishment.nic_code,
        women_worker_count=establishment.women_worker_count,
        contract_worker_count=establishment.contract_worker_count,
        interstate_migrant_count=establishment.interstate_migrant_count,
        is_factory=establishment.is_factory,
        is_mine=establishment.is_mine,
        is_plantation=establishment.is_plantation,
        is_construction=establishment.is_construction,
        has_hazardous_process=establishment.has_hazardous_process,
        engages_contract_labour=establishment.engages_contract_labour,
        has_night_shift=establishment.has_night_shift,
        commenced_on=establishment.commenced_on,
        jurisdiction_code=establishment.jurisdiction_code,
        registrations=[
            RegistrationOut(
                id=r.id,
                kind=r.kind,
                number=r.number,
                issuing_authority=r.issuing_authority,
                valid_from=r.valid_from,
                valid_to=r.valid_to,
                is_current=r.is_valid_on(today),
            )
            for r in establishment.registrations or []
        ],
        contractors=[
            ContractorOut(
                id=c.id,
                name=c.name,
                licence_number=c.licence_number,
                licence_valid_to=c.licence_valid_to,
                licensed_worker_count=c.licensed_worker_count,
                deployed_worker_count=c.deployed_worker_count,
                is_over_deployed=bool(
                    c.licensed_worker_count is not None
                    and c.deployed_worker_count > c.licensed_worker_count
                ),
            )
            for c in establishment.contractors or []
        ],
        latest_scorecard=_scorecard_out(
            scorecard, session=session, include_computation=True
        )
        if scorecard
        else None,
        document_counts=document_counts,
        applicable_thresholds=_thresholds(establishment),
        minimum_wage=_minimum_wage(session, establishment, today),
    )


@router.get("/{establishment_id}/scorecards", response_model=list[ScorecardOut])
def list_scorecards(
    establishment_id: str,
    session: DbSession,
    access: Access,
    limit: Annotated[int, Query(ge=1, le=60)] = 12,
) -> list[ScorecardOut]:
    """Score history.

    Scorecards are immutable, so this is a genuine trajectory rather than a
    current value with a timestamp. Whether an establishment is improving matters
    more for targeting than where it stands today.
    """
    establishment = session.get(Establishment, establishment_id)
    if establishment is None:
        raise HTTPException(status_code=404, detail="establishment not found")
    access.assert_can_access(establishment)

    rows = (
        session.execute(
            select(Scorecard)
            .where(Scorecard.establishment_id == establishment_id)
            .order_by(desc(Scorecard.computed_at))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [_scorecard_out(row) for row in rows]


# -------------------------------------------------------------------- writes
@router.post(
    "",
    response_model=EstablishmentDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(Role.EMPLOYER, Role.ADMIN))],
)
def create_establishment(
    payload: EstablishmentIn,
    session: DbSession,
    user: CurrentUser,
    access: Access,
) -> EstablishmentDetail:
    establishment = Establishment(
        organisation_id=user.organisation_id,
        **payload.model_dump(exclude={"state_code"}),
        state_code=payload.state_code.upper(),
    )
    # The twelve-month peak governs several thresholds and can never be below the
    # current headcount, whatever was submitted.
    establishment.worker_count_peak_12m = max(
        establishment.worker_count_peak_12m, establishment.worker_count
    )
    session.add(establishment)
    session.commit()

    return get_establishment(establishment.id, session, access)


@router.patch(
    "/{establishment_id}",
    response_model=EstablishmentDetail,
    dependencies=[Depends(require_roles(Role.EMPLOYER, Role.ADMIN))],
)
def update_establishment(
    establishment_id: str,
    payload: EstablishmentIn,
    session: DbSession,
    access: Access,
) -> EstablishmentDetail:
    establishment = session.get(Establishment, establishment_id)
    if establishment is None:
        raise HTTPException(status_code=404, detail="establishment not found")
    access.assert_can_access(establishment)

    for field_name, value in payload.model_dump().items():
        setattr(
            establishment,
            field_name,
            value.upper() if field_name == "state_code" and value else value,
        )
    establishment.worker_count_peak_12m = max(
        establishment.worker_count_peak_12m, establishment.worker_count
    )
    session.commit()

    return get_establishment(establishment_id, session, access)


@router.post(
    "/{establishment_id}/evaluate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(Role.EMPLOYER, Role.INSPECTOR, Role.ADMIN))],
)
def evaluate(
    establishment_id: str,
    payload: EvaluateRequest,
    session: DbSession,
    user: CurrentUser,
    access: Access,
) -> dict[str, str]:
    """Re-run rules, scoring and alerts for one period."""
    establishment = session.get(Establishment, establishment_id)
    if establishment is None:
        raise HTTPException(status_code=404, detail="establishment not found")
    access.assert_can_access(establishment)

    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=422, detail="the period ends before it begins")

    job = job_service.enqueue_evaluation(
        session,
        establishment_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        actor_id=user.id,
    )
    session.commit()
    return {
        "establishment_id": establishment_id,
        "job_id": job.id,
        "status": "queued",
    }


# -------------------------------------------------------------------- helpers
def _scoped(query, user: CurrentUser):
    if user.role is Role.EMPLOYER:
        return query.where(Establishment.organisation_id == user.organisation_id)
    if user.role is Role.ADMIN:
        return query

    jurisdictions = set(user.jurisdictions or [])
    if not jurisdictions:
        # Fail closed: an empty jurisdiction list is no access, not all access.
        return query.where(Establishment.id.is_(None))

    states = [j.split("/", 1)[1] for j in jurisdictions if "/" in j]
    if not states:
        return query.where(Establishment.id.is_(None))
    return query.where(Establishment.state_code.in_(states))


def _latest_scorecard(session: DbSession, establishment_id: str) -> Scorecard | None:
    return session.execute(
        select(Scorecard)
        .where(Scorecard.establishment_id == establishment_id)
        .order_by(desc(Scorecard.computed_at))
        .limit(1)
    ).scalar_one_or_none()


def _summaries(
    session: DbSession, establishments: list[Establishment]
) -> list[EstablishmentSummary]:
    if not establishments:
        return []

    ids = [e.id for e in establishments]

    # One query per aggregate rather than per establishment: a worklist over a few
    # hundred establishments would otherwise issue a few hundred round trips.
    latest_ids = (
        select(func.max(Scorecard.id))
        .where(Scorecard.establishment_id.in_(ids))
        .group_by(Scorecard.establishment_id)
        .scalar_subquery()
    )
    scorecards = {
        row.establishment_id: row
        for row in session.execute(
            select(Scorecard).where(Scorecard.id.in_(latest_ids))
        ).scalars()
    }

    open_counts: dict[str, int] = {}
    critical_counts: dict[str, int] = {}

    for establishment_id, severity, count in session.execute(
        select(Finding.establishment_id, Finding.severity, func.count())
        .where(
            Finding.establishment_id.in_(ids),
            Finding.kind != FindingKind.ANOMALY,
            Finding.rule_id != "MODEL.OBSERVATION",
            Finding.status.in_(
                [
                    FindingStatus.OPEN,
                    FindingStatus.ACKNOWLEDGED,
                    FindingStatus.DISPUTED,
                ]
            ),
        )
        .group_by(Finding.establishment_id, Finding.severity)
    ).all():
        open_counts[establishment_id] = open_counts.get(establishment_id, 0) + int(count)
        if severity == Severity.CRITICAL:
            critical_counts[establishment_id] = critical_counts.get(
                establishment_id, 0
            ) + int(count)

    summaries: list[EstablishmentSummary] = []
    for establishment in establishments:
        scorecard = scorecards.get(establishment.id)
        summaries.append(
            EstablishmentSummary(
                id=establishment.id,
                name=establishment.name,
                lin=establishment.lin,
                state_code=establishment.state_code,
                district=establishment.district,
                sector=establishment.sector,
                worker_count=establishment.worker_count,
                worker_count_peak_12m=establishment.worker_count_peak_12m,
                is_active=establishment.is_active,
                latest_score=scorecard.overall_score if scorecard else None,
                risk_band=scorecard.risk_band if scorecard else None,
                data_completeness=scorecard.data_completeness if scorecard else None,
                open_finding_count=open_counts.get(establishment.id, 0),
                critical_finding_count=critical_counts.get(establishment.id, 0),
                inspection_priority=(
                    scorecard.recommended_inspection_priority if scorecard else None
                ),
                last_evaluated_at=(
                    scorecard.computed_at.isoformat() if scorecard else None
                ),
            )
        )

    return summaries


def _document_types_from_computation(
    completeness: dict[str, Any] | None, key: str
) -> list[DocumentType] | None:
    if not completeness or not isinstance(completeness.get(key), list):
        return None
    values: list[DocumentType] = []
    for value in completeness[key]:
        try:
            values.append(DocumentType(str(value)))
        except ValueError:
            continue
    return values


def _present_document_types(
    session: DbSession, scorecard: Scorecard
) -> list[DocumentType]:
    """Document types actually assessed in this immutable scorecard period.

    Older scorecards predate the persisted list, so the detail API reconstructs
    it with the same status and inclusive-period rules used by score computation.
    """
    query = select(Document.doc_type).where(
        Document.establishment_id == scorecard.establishment_id,
        Document.status.in_(
            [
                DocumentStatus.EXTRACTED,
                DocumentStatus.NEEDS_REVIEW,
                DocumentStatus.VERIFIED,
                DocumentStatus.EVALUATED,
            ]
        ),
    )
    if scorecard.period_end is not None:
        query = query.where(Document.period_start <= scorecard.period_end)
    if scorecard.period_start is not None:
        query = query.where(Document.period_end >= scorecard.period_start)

    values = set(session.execute(query).scalars().all())
    return sorted(values, key=lambda item: item.value)


def _scorecard_out(
    scorecard: Scorecard,
    *,
    session: DbSession | None = None,
    include_computation: bool = False,
) -> ScorecardOut:
    completeness = scorecard.computation.get("completeness") if scorecard.computation else None
    sufficient = bool(completeness.get("is_sufficient")) if completeness else False
    present_document_types = _document_types_from_computation(
        completeness, "present_document_types"
    )
    if present_document_types is None and session is not None:
        present_document_types = _present_document_types(session, scorecard)

    return ScorecardOut(
        id=scorecard.id,
        computed_at=scorecard.computed_at.isoformat(),
        period_start=scorecard.period_start,
        period_end=scorecard.period_end,
        overall_score=scorecard.overall_score,
        risk_band=scorecard.risk_band,
        code_scores=dict(scorecard.code_scores or {}),
        data_completeness=scorecard.data_completeness,
        documents_expected=scorecard.documents_expected,
        documents_received=scorecard.documents_received,
        expected_document_types=_document_types_from_computation(
            completeness, "expected_document_types"
        ),
        present_document_types=present_document_types,
        missing_document_types=_document_types_from_computation(
            completeness, "missing_document_types"
        ),
        findings_by_severity=dict(scorecard.findings_by_severity or {}),
        open_finding_count=scorecard.open_finding_count,
        anomaly_count=scorecard.anomaly_count,
        recommended_inspection_priority=scorecard.recommended_inspection_priority,
        recommended_inspection_months=scorecard.recommended_inspection_months,
        evidence_sufficient=sufficient,
        evidence_note=scorecard.evidence_note,
        review_summary=scorecard.review_summary,
        records_quality=scorecard.records_quality,
        # The full computation is large. Returned only on the detail view, where
        # somebody is actually inspecting how a score was produced.
        computation=dict(scorecard.computation or {}) if include_computation else None,
    )


def _thresholds(establishment: Establishment) -> dict[str, Any]:
    """Which headcount thresholds this establishment crosses.

    Shown so an employer can see why a rule applies to them, and so an inspector
    can sanity-check applicability without reading the rule pack. Each entry
    carries the section it comes from.
    """
    peak = max(establishment.worker_count_peak_12m, establishment.worker_count)

    return {
        "works_committee": {
            "applies": peak >= 100,
            "threshold": 100,
            "basis": "workers on any day in the preceding twelve months",
            "citation": "Industrial Relations Code, 2020 — s.3(1)",
        },
        "grievance_committee": {
            "applies": establishment.worker_count >= 20,
            "threshold": 20,
            "basis": "workers currently employed",
            "citation": "Industrial Relations Code, 2020 — s.4(1)",
        },
        "standing_orders": {
            "applies": peak >= 300,
            "threshold": 300,
            "basis": "workers on any day in the preceding twelve months",
            "citation": "Industrial Relations Code, 2020 — s.28(1)",
        },
        "retrenchment_permission": {
            "applies": peak >= 300
            and (
                establishment.is_factory
                or establishment.is_mine
                or establishment.is_plantation
            ),
            "threshold": 300,
            "basis": "factories, mines and plantations only",
            "citation": "Industrial Relations Code, 2020 — Chapter X",
        },
        "contractor_licensing": {
            "applies": establishment.engages_contract_labour,
            "basis": "engaging contract labour",
            "citation": "OSH & Working Conditions Code, 2020 — Chapter XI",
        },
        "health_examinations": {
            "applies": establishment.has_hazardous_process,
            "basis": "hazardous processes carried on",
            "citation": "OSH & Working Conditions Code, 2020 — s.18",
        },
    }


def _minimum_wage(
    session: DbSession, establishment: Establishment, on: date
) -> dict[str, Any]:
    """The wage floor on file for this state, with its provenance.

    Provenance is returned alongside the rate because it is legally material: a
    figure from a secondary reference table must not be presented with the
    authority of an official state notification.
    """
    rates: dict[str, Any] = {}
    source: str | None = None
    note: str | None = None

    for category in SkillCategory:
        rate = lookup_rate(
            session,
            state_code=establishment.state_code,
            skill_category=category,
            on=on,
        )
        if rate is None:
            continue
        rates[category.value] = {
            "daily_paise": rate.daily_rate_paise,
            "daily_rupees": rate.daily_rate_rupees,
            "monthly_paise": rate.monthly_rate_paise,
            "monthly_working_days": rate.monthly_working_days,
            "effective_from": rate.effective_from.isoformat(),
        }
        source = rate.source.value
        note = rate.source_note

    return {
        "state_code": establishment.state_code,
        "effective_on": on.isoformat(),
        "rates": rates,
        "source": source,
        "source_note": note,
        "available": bool(rates),
        "caveat": (
            None
            if rates
            else "No minimum wage rate is on file for this state, so wage floor "
            "checks cannot run. They are skipped rather than guessed."
        ),
    }
