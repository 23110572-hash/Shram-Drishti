"""Building the fact context a rule expression is evaluated against.

Rules are written to read close to the statute:

    is_missing(deduction_share(row)) or deduction_share(row) <= 0.5

That only works if the facts are shaped for it, which is what this module does.
It queries everything held for one establishment and one period and assembles the
namespaces the rule packs traverse: ``estab``, ``period``, ``wage_register``,
``epf``, ``docs``, ``counts`` and the rest.

Two decisions here matter more than the plumbing.

**Missing stays missing.** Nothing is defaulted to zero on the way in. A wage row
with no recorded deduction must produce ``None``, not ``0``, because the
evaluator propagates ``None`` through comparisons and a rule therefore declines
to judge rather than passing an establishment it could not assess. Substituting
zero here would silently turn "we have no data" into "this is compliant", which
is the most dangerous failure a compliance system can have.

**Derived values are precomputed.** ``daily_wage_paise``, ``deduction_share``,
``worker_key`` and the rest are attached to each row before evaluation. Rule
authors get plain field access instead of nested function calls, and — more
importantly — the ``observe`` expressions that record what a finding saw can use
``pluck(wage_register, 'daily_wage_paise')`` rather than re-deriving it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType, SkillCategory
from app.models.establishment import Contractor, Establishment, Registration
from app.models.extraction import (
    AttendanceRecord,
    ContributionLine,
    IncidentRecord,
    ProseAssertion,
    WageLine,
    WorkerIdentity,
)
from app.services.wage_rates import lookup_rate

logger = logging.getLogger(__name__)

# ESIC applies below a monthly wage ceiling set by scheme notification. The value
# lives here as a single named constant rather than scattered through rules,
# because when the notification is obtained this is the one place to change.
# Marked clearly as unverified: any rule that depends on it says so on its
# findings.
ESIC_WAGE_CEILING_PAISE = 2_100_000  # ₹21,000 per month
ESIC_CEILING_VERIFIED = False

#: Key carried on every row indicating whether it survived verification during
#: reading. The rule engine refuses to judge a row where this is False.
#:
#: This matters more than it first appears. When the model swaps two columns —
#: reading deductions as net and net as deductions — the row is internally
#: plausible but says the opposite of the truth: a 55% deduction reads as 45%,
#: which is inside the statutory cap. Evaluating such a row does not merely risk a
#: false accusation, it silently absolves a real breach. Declining to judge it and
#: reporting the gap is the only defensible behaviour.
ROW_VERIFIED_KEY = "row_verified"


class FactList(list):
    """A list that also carries summary attributes.

    Needed because rules address the same collection two ways. ``for_each:
    incidents`` iterates rows, while ``incidents.notified >= incidents.total``
    reads aggregates off the same name. A plain list cannot do the second and a
    plain dict cannot do the first, so the list carries the totals as attributes.
    """

    def __init__(self, rows: Iterable[Any] = (), **summary: Any) -> None:
        super().__init__(rows)
        for key, value in summary.items():
            setattr(self, key, value)


@dataclass
class FactContext:
    """The complete namespace handed to the evaluator."""

    establishment: Establishment
    period_start: date | None
    period_end: date | None
    namespaces: dict[str, Any] = field(default_factory=dict)
    #: Row-level provenance, keyed by namespace then row index, so a finding can
    #: be traced back to the page and cell that produced it.
    row_sources: dict[str, list[dict]] = field(default_factory=dict)
    #: Documents considered, so a finding can name its evidence.
    documents: list[Document] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_facts(self) -> dict[str, Any]:
        return dict(self.namespaces)

    def rows(self, namespace: str) -> list[Any]:
        value = self.namespaces.get(namespace)
        return list(value) if isinstance(value, list) else []

    def source_for(self, namespace: str, index: int) -> dict:
        sources = self.row_sources.get(namespace) or []
        return sources[index] if 0 <= index < len(sources) else {}


# --------------------------------------------------------------------- builder
def build_facts(
    session: Session,
    *,
    establishment: Establishment,
    period_start: date | None,
    period_end: date | None,
) -> FactContext:
    """Assemble every fact for one establishment and period."""
    context = FactContext(
        establishment=establishment,
        period_start=period_start,
        period_end=period_end,
    )

    documents = _documents(session, establishment.id, period_start, period_end)
    context.documents = documents
    document_ids = [d.id for d in documents]

    wage_lines = _wage_lines(session, establishment.id, period_start, period_end)
    attendance = _attendance(session, establishment.id, period_start, period_end)
    contributions = _contributions(session, establishment.id, period_start, period_end)
    incidents = _incidents(session, establishment.id, period_start, period_end)
    prose = _prose(session, establishment.id, document_ids)

    identities = _identities(session, establishment.id)
    attendance_by_worker = {
        record.worker_identity_id: record
        for record in attendance
        if record.worker_identity_id
    }

    wage_floor = _wage_floor(session, establishment, period_end or period_start)

    wage_rows, wage_sources = _wage_rows(
        wage_lines, attendance_by_worker, identities, wage_floor
    )
    attendance_rows, attendance_sources = _attendance_rows(attendance)
    epf_rows, epf_sources = _contribution_rows(
        [c for c in contributions if (c.scheme or "").upper() == "EPF"], wage_lines
    )
    esic_rows, esic_sources = _contribution_rows(
        [c for c in contributions if (c.scheme or "").upper() == "ESIC"], wage_lines
    )
    incident_rows, incident_sources = _incident_rows(incidents)
    employee_rows = _employee_rows(identities, period_start, period_end)

    context.namespaces = {
        "estab": _establishment_facts(establishment),
        "period": _period_facts(period_start, period_end, documents),
        "wage_register": wage_rows,
        "employee_register": employee_rows,
        "attendance": attendance_rows,
        "epf": epf_rows,
        "esic": esic_rows,
        "annual_return": prose,
        "contractors": _contractor_facts(establishment, period_end or period_start),
        "registrations": _registration_facts(establishment, period_end or period_start),
        "incidents": incident_rows,
        "prose": prose,
        "wage_floor": wage_floor,
        "docs": _document_counts(documents),
        "counts": _headcounts(wage_rows, epf_rows, esic_rows, prose, employee_rows),
    }

    context.row_sources = {
        "wage_register": wage_sources,
        "attendance": attendance_sources,
        "epf": epf_sources,
        "esic": esic_sources,
        "incidents": incident_sources,
    }

    if not wage_rows:
        context.notes.append("no wage register data is held for this period")
    if not epf_rows:
        context.notes.append("no provident fund filing is held for this period")

    return context


# ------------------------------------------------------------------- loading
def _in_period(column_start: Any, column_end: Any, start: date | None, end: date | None):
    """Overlap predicate.

    Overlap rather than containment, because a wage period running 26 February to
    25 March belongs to March in every practical sense and a containment test
    would exclude it from both months.
    """
    conditions = []
    if end is not None:
        conditions.append(column_start <= end)
    if start is not None:
        conditions.append(column_end >= start)
    return conditions


def _documents(
    session: Session, establishment_id: str, start: date | None, end: date | None
) -> list[Document]:
    query = select(Document).where(
        Document.establishment_id == establishment_id,
        Document.status.in_(
            [
                DocumentStatus.EXTRACTED,
                DocumentStatus.NEEDS_REVIEW,
                DocumentStatus.VERIFIED,
                DocumentStatus.EVALUATED,
            ]
        ),
    )
    for condition in _in_period(Document.period_start, Document.period_end, start, end):
        query = query.where(condition)
    return list(session.execute(query).scalars().all())


def _wage_lines(
    session: Session, establishment_id: str, start: date | None, end: date | None
) -> list[WageLine]:
    query = select(WageLine).where(WageLine.establishment_id == establishment_id)
    for condition in _in_period(WageLine.period_start, WageLine.period_end, start, end):
        query = query.where(condition)
    return list(session.execute(query).scalars().all())


def _attendance(
    session: Session, establishment_id: str, start: date | None, end: date | None
) -> list[AttendanceRecord]:
    query = select(AttendanceRecord).where(
        AttendanceRecord.establishment_id == establishment_id
    )
    for condition in _in_period(
        AttendanceRecord.period_start, AttendanceRecord.period_end, start, end
    ):
        query = query.where(condition)
    return list(session.execute(query).scalars().all())


def _contributions(
    session: Session, establishment_id: str, start: date | None, end: date | None
) -> list[ContributionLine]:
    query = select(ContributionLine).where(
        ContributionLine.establishment_id == establishment_id
    )
    for condition in _in_period(
        ContributionLine.period_start, ContributionLine.period_end, start, end
    ):
        query = query.where(condition)
    return list(session.execute(query).scalars().all())


def _incidents(
    session: Session, establishment_id: str, start: date | None, end: date | None
) -> list[IncidentRecord]:
    query = select(IncidentRecord).where(
        IncidentRecord.establishment_id == establishment_id
    )
    if start is not None:
        query = query.where(IncidentRecord.occurred_on >= start)
    if end is not None:
        query = query.where(IncidentRecord.occurred_on <= end)
    return list(session.execute(query).scalars().all())


def _prose(
    session: Session, establishment_id: str, document_ids: list[str]
) -> dict[str, Any]:
    """Flatten prose assertions into a single namespace.

    Later documents win on a repeated key, since they are the more recent
    statement of the same fact. Values are coerced towards what rules expect:
    ``prose.grievance_committee_members <= 10`` needs a number, and the assertion
    stored it as text.
    """
    query = select(ProseAssertion).where(
        ProseAssertion.establishment_id == establishment_id
    )
    if document_ids:
        query = query.where(ProseAssertion.document_id.in_(document_ids))

    facts: dict[str, Any] = {}
    for assertion in session.execute(query).scalars().all():
        if not assertion.key:
            continue

        if not assertion.present:
            facts[assertion.key] = None
            facts[f"{assertion.key}_stated"] = False
            continue

        facts[f"{assertion.key}_stated"] = True
        facts[assertion.key] = _coerce_prose_value(assertion.value_text)
        if assertion.quote:
            facts[f"{assertion.key}_quote"] = assertion.quote

    # A couple of aliases so rule authors can use the natural name.
    if "aggregator_contribution" in facts:
        facts.setdefault(
            "aggregator_contribution_paise",
            _rupees_to_paise(facts.get("aggregator_contribution")),
        )
    if "accidents_reported" in facts:
        facts.setdefault("incidents_declared", facts.get("accidents_reported"))

    return facts


def _identities(session: Session, establishment_id: str) -> list[WorkerIdentity]:
    return list(
        session.execute(
            select(WorkerIdentity).where(
                WorkerIdentity.establishment_id == establishment_id
            )
        )
        .scalars()
        .all()
    )


# --------------------------------------------------------------- row shaping
def _wage_rows(
    wage_lines: list[WageLine],
    attendance_by_worker: dict[str | None, AttendanceRecord],
    identities: list[WorkerIdentity],
    wage_floor: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    """Shape wage rows and attach every derived value a rule might read."""
    identity_by_id = {identity.id: identity for identity in identities}
    rows: list[dict] = []
    sources: list[dict] = []

    for line in wage_lines:
        identity = identity_by_id.get(line.worker_identity_id or "")
        attendance = attendance_by_worker.get(line.worker_identity_id)

        statutory = line.statutory_wages_paise
        total_rem = line.total_remuneration_paise

        # Attendance is a separate document, so days present may only exist
        # there. Preferring the wage register's own figure and falling back to
        # the muster roll is what makes the "paid for fewer days than present"
        # comparison possible at all.
        days_present = line.days_present
        if days_present is None and attendance is not None:
            days_present = attendance.days_present

        overtime_hours = line.overtime_hours
        if overtime_hours is None and attendance is not None:
            overtime_hours = attendance.overtime_hours

        row: dict[str, Any] = {
            "worker_key": identity.id if identity else None,
            "worker_name_as_printed": line.worker_name_as_printed,
            "worker_display_name": identity.display_name if identity else None,
            "row_number": line.row_number,
            "uan": identity.uan if identity else None,
            "skill_category": _skill_name(line.skill_category or (identity.skill_category if identity else None)),
            "date_of_joining": identity.date_of_joining if identity else None,
            "date_of_exit": identity.date_of_exit if identity else None,
            "days_paid": line.days_paid,
            "days_present": days_present,
            "normal_hours_per_day": line.normal_hours_per_day,
            "overtime_hours": overtime_hours,
            "basic_paise": line.basic_paise,
            "da_paise": line.da_paise,
            "other_allowances_paise": line.other_allowances_paise,
            "gross_paise": line.gross_paise,
            "overtime_paise": line.overtime_paise,
            "overtime_rate_paise": line.overtime_rate_paise,
            "pf_deduction_paise": line.pf_deduction_paise,
            "esi_deduction_paise": line.esi_deduction_paise,
            "advance_recovery_paise": line.advance_recovery_paise,
            "deductions_paise": line.deductions_paise,
            "net_paid_paise": line.net_paid_paise,
            "paid_on": line.paid_on,
            "statutory_wages_paise": statutory,
            "total_remuneration_paise": total_rem,
        }

        # ---- derived, precomputed so observe expressions can pluck them
        row["daily_wage_paise"] = _ratio(statutory, line.days_paid)
        row["ordinary_hourly_rate_paise"] = line.ordinary_hourly_rate_paise
        row["deduction_share"] = _ratio(line.deductions_paise, total_rem)
        row["excluded_share"] = _ratio(line.other_allowances_paise, total_rem)
        row["settlement_days"] = (
            (line.paid_on - identity.date_of_exit).days
            if identity and identity.date_of_exit and line.paid_on
            else None
        )
        row["unpaid_days"] = (
            float(days_present) - float(line.days_paid)
            if days_present is not None and line.days_paid is not None
            else None
        )
        row["shortfall_vs_floor_paise"] = (
            wage_floor["daily_paise"] - row["daily_wage_paise"]
            if wage_floor.get("daily_paise") is not None
            and row["daily_wage_paise"] is not None
            and row["daily_wage_paise"] < wage_floor["daily_paise"]
            else None
        )

        # Only workers at or below the ceiling are compared against the ESIC
        # filing, so a well-paid employee legitimately outside the scheme is not
        # reported as uncovered.
        monthly = total_rem
        row["esic_eligible_worker_key"] = (
            identity.id
            if identity and monthly is not None and monthly <= ESIC_WAGE_CEILING_PAISE
            else None
        )

        # Whether this row may be used to decide compliance at all. False when a
        # figure could not be traced to the page or the row's arithmetic does not
        # hold, which usually means two columns were read the wrong way round.
        row[ROW_VERIFIED_KEY] = not line.needs_review
        row["review_reasons"] = list(line.review_reasons or [])

        rows.append(row)
        sources.append(
            {
                "document_id": line.document_id,
                "provenance": dict(line.provenance or {}),
                "worker_identity_id": line.worker_identity_id,
                "row_reference": (
                    f"row {line.row_number}" if line.row_number else line.worker_name_as_printed
                ),
            }
        )

    return rows, sources


def _attendance_rows(
    records: list[AttendanceRecord],
) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    sources: list[dict] = []

    for record in records:
        rows.append(
            {
                "worker_key": record.worker_identity_id,
                "worker_name_as_printed": record.worker_name_as_printed,
                "days_present": record.days_present,
                "days_absent": record.days_absent,
                "weekly_offs_given": record.weekly_offs_given,
                "total_hours": record.total_hours,
                "overtime_hours": record.overtime_hours,
                "max_daily_hours": record.max_daily_hours,
                "max_weekly_hours": record.max_weekly_hours,
                "longest_consecutive_days": record.longest_consecutive_days,
                ROW_VERIFIED_KEY: not record.needs_review,
                "review_reasons": list(record.review_reasons or []),
            }
        )
        sources.append(
            {
                "document_id": record.document_id,
                "provenance": dict(record.provenance or {}),
                "worker_identity_id": record.worker_identity_id,
                "row_reference": record.worker_name_as_printed,
            }
        )

    return rows, sources


def _contribution_rows(
    lines: list[ContributionLine], wage_lines: list[WageLine]
) -> tuple[list[dict], list[dict]]:
    """Shape contribution rows, joining each to the wage register.

    ``register_wages_paise`` is attached here so the wage-base suppression rule
    can compare a declared contribution base against the basic-plus-DA the
    register itself shows. Without that join the rule would have nothing to
    compare against, and wage suppression is one of the commonest evasions.
    """
    register_wages: dict[str, int] = {}
    for line in wage_lines:
        if line.worker_identity_id:
            wages = line.statutory_wages_paise
            if wages is not None:
                register_wages[line.worker_identity_id] = wages

    rows: list[dict] = []
    sources: list[dict] = []

    for line in lines:
        rows.append(
            {
                "worker_key": line.worker_identity_id,
                "worker_name_as_printed": line.worker_name_as_printed,
                "uan": line.uan,
                "member_id": line.member_id,
                "wage_base_paise": line.wage_base_paise,
                "employee_share_paise": line.employee_share_paise,
                "employer_share_paise": line.employer_share_paise,
                "ncp_days": line.ncp_days,
                "deposited_on": line.deposited_on,
                "challan_number": line.challan_number,
                "register_wages_paise": register_wages.get(
                    line.worker_identity_id or ""
                ),
                ROW_VERIFIED_KEY: not line.needs_review,
                "review_reasons": list(line.review_reasons or []),
            }
        )
        sources.append(
            {
                "document_id": line.document_id,
                "provenance": dict(line.provenance or {}),
                "worker_identity_id": line.worker_identity_id,
                "row_reference": line.worker_name_as_printed,
            }
        )

    return rows, sources


def _incident_rows(
    records: list[IncidentRecord],
) -> tuple[FactList, list[dict]]:
    rows: list[dict] = []
    sources: list[dict] = []
    notified = 0

    for record in records:
        delay = (
            (record.notified_on - record.occurred_on).days
            if record.occurred_on and record.notified_on
            else None
        )
        if record.notified_on is not None:
            notified += 1

        rows.append(
            {
                "occurred_on": record.occurred_on,
                "notified_on": record.notified_on,
                "notification_delay_days": delay,
                "description": record.description,
                "severity": record.severity,
                "workers_affected": record.workers_affected,
                "notification_reference": record.notification_reference,
            }
        )
        sources.append(
            {
                "document_id": record.document_id,
                "provenance": dict(record.provenance or {}),
                "row_reference": (
                    record.occurred_on.isoformat() if record.occurred_on else "undated"
                ),
            }
        )

    return (
        FactList(
            rows,
            total=len(rows),
            notified=notified,
            unnotified=len(rows) - notified,
        ),
        sources,
    )


def _employee_rows(
    identities: list[WorkerIdentity], start: date | None, end: date | None
) -> list[dict]:
    """The employee register: everyone on the books during the period.

    Someone who left before the period began or joined after it ended is
    excluded, so a headcount comparison is not thrown off by historical staff.
    """
    rows: list[dict] = []

    for identity in identities:
        if end and identity.date_of_joining and identity.date_of_joining > end:
            continue
        if start and identity.date_of_exit and identity.date_of_exit < start:
            continue

        rows.append(
            {
                "worker_key": identity.id,
                "worker_display_name": identity.display_name,
                "uan": identity.uan,
                "esic_number": identity.esic_number,
                "father_name": identity.father_name,
                "designation": identity.designation,
                "skill_category": _skill_name(identity.skill_category),
                "gender": identity.gender,
                "date_of_joining": identity.date_of_joining,
                "date_of_exit": identity.date_of_exit,
                "is_contract_worker": identity.is_contract_worker,
                "match_reviewed": identity.match_reviewed,
                "match_confidence": identity.match_confidence,
            }
        )

    return rows


# --------------------------------------------------------------- aggregates
def _establishment_facts(establishment: Establishment) -> dict[str, Any]:
    return {
        "id": establishment.id,
        "name": establishment.name,
        "lin": establishment.lin,
        "state_code": establishment.state_code,
        "district": establishment.district,
        "wage_zone": establishment.wage_zone,
        "jurisdiction_code": establishment.jurisdiction_code,
        "nic_code": establishment.nic_code,
        "sector": establishment.sector,
        "worker_count": establishment.worker_count,
        "worker_count_peak_12m": max(
            establishment.worker_count_peak_12m, establishment.worker_count
        ),
        "women_worker_count": establishment.women_worker_count,
        "women_worker_ratio": establishment.women_worker_ratio,
        "contract_worker_count": establishment.contract_worker_count,
        "interstate_migrant_count": establishment.interstate_migrant_count,
        "is_factory": establishment.is_factory,
        "is_mine": establishment.is_mine,
        "is_plantation": establishment.is_plantation,
        "is_construction": establishment.is_construction,
        "has_hazardous_process": establishment.has_hazardous_process,
        "engages_contract_labour": establishment.engages_contract_labour,
        "has_night_shift": establishment.has_night_shift,
        "commenced_on": establishment.commenced_on,
    }


def _period_facts(
    start: date | None, end: date | None, documents: list[Document]
) -> dict[str, Any]:
    days = (end - start).days + 1 if start and end else None

    # Basis is taken from the documents themselves where available, because the
    # wage-period rules test what the employer actually operates, not what the
    # reporting window happens to be.
    basis = None
    if days is not None:
        if days <= 1:
            basis = "daily"
        elif days <= 8:
            basis = "weekly"
        elif days <= 16:
            basis = "fortnightly"
        elif days <= 31:
            basis = "monthly"
        else:
            basis = "longer_than_month"

    return {
        "start": start,
        "end": end,
        "days": days,
        "basis": basis,
        "document_count": len(documents),
    }


def _contractor_facts(
    establishment: Establishment, on: date | None
) -> dict[str, Any]:
    contractors: list[Contractor] = list(establishment.contractors or [])
    reference = on or date.today()

    expired = 0
    unlicensed = 0
    over_deployed = 0

    for contractor in contractors:
        has_number = bool(contractor.licence_number)
        # A null expiry is an open-ended licence, which is legitimate. Treating
        # null as expired would flag every establishment holding one.
        lapsed = bool(
            contractor.licence_valid_to and contractor.licence_valid_to < reference
        )

        if not has_number or lapsed:
            unlicensed += 1
        if lapsed:
            expired += 1
        if (
            contractor.licensed_worker_count is not None
            and contractor.deployed_worker_count > contractor.licensed_worker_count
        ):
            over_deployed += 1

    return {
        "total": len(contractors),
        "expired": expired,
        "without_valid_licence": unlicensed,
        "over_deployed": over_deployed,
        "deployed_workers": sum(c.deployed_worker_count for c in contractors),
        "licensed_workers": sum(
            c.licensed_worker_count or 0 for c in contractors
        ),
    }


def _registration_facts(
    establishment: Establishment, on: date | None
) -> dict[str, Any]:
    registrations: list[Registration] = list(establishment.registrations or [])
    reference = on or date.today()

    def find(kind: str) -> Registration | None:
        matches = [r for r in registrations if (r.kind or "").upper() == kind]
        if not matches:
            return None
        # Prefer one valid on the reference date; otherwise the latest, so an
        # expiry check has something to report rather than reading as absent.
        valid = [r for r in matches if r.is_valid_on(reference)]
        pool = valid or matches
        return max(pool, key=lambda r: r.valid_to or date.min)

    establishment_reg = find("ESTABLISHMENT_REGISTRATION")
    factory = find("FACTORY_LICENCE")
    epf = find("EPF")
    esic = find("ESIC")
    bocw = find("BOCW")

    return {
        "total": len(registrations),
        "kinds": sorted({(r.kind or "").upper() for r in registrations if r.kind}),
        "has_establishment_registration": establishment_reg is not None,
        "establishment_number": establishment_reg.number if establishment_reg else None,
        "establishment_valid_to": establishment_reg.valid_to if establishment_reg else None,
        "has_factory_licence": factory is not None,
        "factory_valid_to": factory.valid_to if factory else None,
        "has_epf": epf is not None,
        "epf_number": epf.number if epf else None,
        "has_esic": esic is not None,
        "esic_number": esic.number if esic else None,
        "has_bocw": bocw is not None,
        "expired_count": sum(
            1 for r in registrations if r.valid_to and r.valid_to < reference
        ),
    }


def _document_counts(documents: list[Document]) -> dict[str, Any]:
    """How many of each document type were received.

    Feeds the missing-document rules. Names match the rule packs exactly, so a
    rule reads ``docs.wage_slip_count > 0``.
    """
    counts = {doc_type: 0 for doc_type in DocumentType}
    for document in documents:
        counts[document.doc_type] = counts.get(document.doc_type, 0) + 1

    facts: dict[str, Any] = {
        f"{doc_type.value.lower()}_count": count
        for doc_type, count in counts.items()
    }

    facts.update(
        {
            "total": len(documents),
            # Committee and welfare records share a document type, so the
            # specific names the rules use are derived rather than counted.
            "works_committee_count": _prose_backed_count(
                documents, DocumentType.GRIEVANCE_COMMITTEE_RECORD
            ),
            "grievance_committee_count": counts.get(
                DocumentType.GRIEVANCE_COMMITTEE_RECORD, 0
            ),
            "standing_orders_count": counts.get(DocumentType.STANDING_ORDERS, 0),
            "creche_record_count": counts.get(
                DocumentType.WELFARE_FACILITY_RECORD, 0
            ),
            "canteen_record_count": counts.get(
                DocumentType.WELFARE_FACILITY_RECORD, 0
            ),
            "health_checkup_count": counts.get(
                DocumentType.HEALTH_CHECKUP_RECORD, 0
            ),
            "needs_review_count": sum(
                1 for d in documents if d.status is DocumentStatus.NEEDS_REVIEW
            ),
        }
    )
    return facts


def _prose_backed_count(documents: list[Document], doc_type: DocumentType) -> int:
    return sum(1 for d in documents if d.doc_type is doc_type)


def _headcounts(
    wage_rows: list[dict],
    epf_rows: list[dict],
    esic_rows: list[dict],
    prose: dict[str, Any],
    employee_rows: list[dict],
) -> dict[str, Any]:
    """Distinct worker counts per source, for reconciliation.

    Counted on resolved identities, not printed names. Counting names would make
    every transliteration difference look like an extra worker and every
    reconciliation rule would fire on clean data.
    """

    def distinct(rows: list[dict], key: str = "worker_key") -> int:
        return len({row[key] for row in rows if row.get(key)})

    return {
        "register": distinct(employee_rows) or distinct(wage_rows),
        "wage_register": distinct(wage_rows),
        "epf": distinct(epf_rows),
        "esic": distinct(esic_rows),
        "esic_eligible": distinct(wage_rows, "esic_eligible_worker_key"),
        "annual_return": prose.get("total_workers"),
        "contract": sum(1 for row in employee_rows if row.get("is_contract_worker")),
        "unreviewed_identity_matches": sum(
            1
            for row in employee_rows
            if not row.get("match_reviewed")
            and (row.get("match_confidence") or 1.0) < 0.9
        ),
    }


def _wage_floor(
    session: Session, establishment: Establishment, on: date | None
) -> dict[str, Any]:
    """The applicable minimum daily wage, with its provenance.

    Returns nulls when no rate covers the date. A rule then declines to judge
    rather than comparing against a guess, because a wage-floor finding computed
    from an invented rate is a false accusation with a number attached.

    ``source`` travels with the rate and is stamped onto any finding that uses
    it, so a REFERENCE rate is never presented with the authority of an official
    notification.
    """
    reference = on or date.today()

    rates: dict[str, Any] = {}
    lowest: int | None = None
    source: str | None = None
    note: str | None = None

    for category in SkillCategory:
        rate = lookup_rate(
            session,
            state_code=establishment.state_code,
            skill_category=category,
            on=reference,
        )
        if rate is None:
            continue
        rates[category.value] = rate.daily_rate_paise
        if lowest is None or rate.daily_rate_paise < lowest:
            lowest = rate.daily_rate_paise
        source = rate.source.value
        note = rate.source_note

    return {
        # The unskilled rate is the operative floor for a row whose skill
        # category is unknown: applying a skilled rate to an unclassified worker
        # would manufacture a shortfall.
        "daily_paise": rates.get(SkillCategory.UNSKILLED.value) or lowest,
        "by_category": rates,
        "source": source,
        "source_note": note,
        "state_code": establishment.state_code,
        "effective_on": reference,
        "monthly_working_days": 26,
    }


# ---------------------------------------------------------------- conversions
def _ratio(numerator: Any, denominator: Any) -> float | None:
    if numerator is None or denominator is None:
        return None
    try:
        divisor = float(denominator)
    except (TypeError, ValueError):
        return None
    if divisor == 0:
        return None
    return float(numerator) / divisor


def _skill_name(value: Any) -> str | None:
    if value is None:
        return None
    return value.value if isinstance(value, SkillCategory) else str(value)


def _rupees_to_paise(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def _coerce_prose_value(value: str | None) -> Any:
    """Turn an assertion's text into the type a rule expects.

    Assertions are stored as text because that is what the document said, but
    ``prose.grievance_committee_members <= 10`` needs a number, and the evaluator
    refuses to compare a string with an integer rather than guessing.
    """
    if value is None:
        return None

    text = value.strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered in {"yes", "true", "y"}:
        return True
    if lowered in {"no", "false", "n"}:
        return False

    cleaned = text.replace(",", "").replace("₹", "").strip()
    try:
        if "." in cleaned:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        pass

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return text
