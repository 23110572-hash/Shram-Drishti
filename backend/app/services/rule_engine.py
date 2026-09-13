"""Running rule packs against facts and emitting findings.

This is where a compliance verdict is actually decided, and it is deliberately
the least clever module in the system. Every decision is a comparison between a
number read off a document and a number written in an Act. No model participates.

That is not distrust of models — models do all the reading, matching and judging
elsewhere in this system. It is that a compliance verdict has two requirements a
model cannot meet:

**Reproducibility.** An employer who disputes a finding must get the same answer
on a re-run, and so must the officer reviewing it six months later. A finding
that changes between runs cannot be enforced.

**Attribution.** "Section 18(3) caps deductions at fifty per cent, this row shows
seventy, here is the arithmetic and here is the cell it came from" is defensible.
"The model considered this non-compliant" is not, whatever the accuracy.

The statutory thresholds are also not an open-ended problem. Section 18(3) is one
number. There is nothing to infer.

Four things every rule run guarantees:

* **Applicability is checked before compliance.** A rule that does not apply
  raises nothing. "Does not apply" and "applies and passes" are different states
  and conflating them would score a small shop against a 300-worker obligation.
* **Missing data raises no finding.** The evaluator propagates None, so a rule
  whose inputs are absent is skipped and recorded as unassessed. Absent data is
  reported through completeness, not as compliance.
* **Findings are deduplicated by content.** A stable key over rule, period and
  subject means re-evaluating a period updates findings instead of multiplying
  them, and a repeat offence is countable.
* **Rule pack version is pinned onto every finding.** A pack upgrade cannot
  retroactively rewrite the basis of a historical finding.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.enums import (
    AuditAction,
    FindingKind,
    FindingStatus,
    LabourCode,
    Severity,
    WageRateSource,
)
from app.models.finding import Finding, FindingEvidence
from app.rules.evaluator import Evaluator, RuleEvaluationError
from app.rules.functions import FACT_ROOTS, RULE_FUNCTIONS
from app.rules.loader import LoadedRules, get_rules
from app.rules.schema import Rule
from app.services import audit as audit_service
from app.services.facts import ROW_VERIFIED_KEY, FactContext

logger = logging.getLogger(__name__)

# Evidence rows attached per finding. A row-level rule can fail on hundreds of
# workers; showing every one buries the point, and an inspector who sees eight
# examples plus a count understands the scale.
MAX_EVIDENCE_PER_FINDING = 8


@dataclass
class RuleOutcome:
    """What happened to one rule on one evaluation."""

    rule_id: str
    applied: bool
    passed: bool | None
    """None when the rule applied but could not be assessed for want of data."""

    failing_row_indices: list[int] = field(default_factory=list)
    observed: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    skipped_reason: str | None = None

    #: Which Code this rule belongs to. Set once when the outcome is recorded, so
    #: coverage can be reported per Code rather than only in aggregate. Without
    #: it, a Code no document spoke to is indistinguishable from a compliant one.
    code: LabourCode | None = None

    #: True only when the rule's own applicability test said this establishment is
    #: not bound by the obligation — a 50-worker unit against a 300-worker duty.
    #: Kept distinct from every other kind of skip, because this one is not a gap
    #: in the evidence and must not count against coverage.
    not_applicable: bool = False

    #: Rows excluded because they failed verification when the document was read.
    #: Reported so a clean result on a badly-read document cannot be mistaken for
    #: compliance.
    unverified_rows: int = 0

    @property
    def is_violation(self) -> bool:
        return self.applied and self.passed is False

    @property
    def is_assessed(self) -> bool:
        """The rule applied and produced a verdict either way."""
        return self.applied and self.passed is not None


@dataclass
class EvaluationReport:
    establishment_id: str
    period_start: date | None
    period_end: date | None
    jurisdiction: str

    outcomes: list[RuleOutcome] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    rules_considered: int = 0
    rules_applied: int = 0
    rules_unassessable: int = 0

    @property
    def violations(self) -> list[RuleOutcome]:
        return [o for o in self.outcomes if o.is_violation]

    @property
    def unassessable(self) -> list[RuleOutcome]:
        return [o for o in self.outcomes if o.applied and o.passed is None]

    @property
    def coverage(self) -> float:
        """Share of applicable rules that could actually be assessed.

        Reported separately from the score. An establishment assessed on three of
        forty rules has not demonstrated compliance, and this is the number that
        says so.
        """
        if self.rules_applied == 0:
            return 0.0
        assessed = self.rules_applied - self.rules_unassessable
        return round(assessed / self.rules_applied, 3)

    def coverage_for(self, code: LabourCode) -> float:
        """Share of this Code's *relevant* rules that produced a verdict.

        Rules the establishment is too small to be bound by are excluded from the
        denominator entirely. Counting them would mean a fifteen-worker shop
        scored badly on coverage for not answering a three-hundred-worker
        obligation, which is not a gap in its evidence.

        What does count against coverage is a rule skipped for want of data. That
        is the case this measure exists for: no wage register was submitted, so
        nothing about wages was tested, and the resulting silence must not be
        read as compliance.

        Returns 0.0 when no rule of this Code was relevant — the caller decides
        what that means, since an empty denominator is not evidence of anything.
        """
        relevant = [
            o for o in self.outcomes if o.code is code and not o.not_applicable
        ]
        if not relevant:
            return 0.0
        assessed = sum(1 for o in relevant if o.is_assessed)
        return round(assessed / len(relevant), 3)

    def relevant_rule_count(self, code: LabourCode) -> int:
        """How many of this Code's rules bind this establishment at all."""
        return sum(
            1 for o in self.outcomes if o.code is code and not o.not_applicable
        )


class RuleEngine:
    def __init__(self, rules: LoadedRules | None = None) -> None:
        self._rules = rules or get_rules()
        self._evaluator = Evaluator(functions=RULE_FUNCTIONS, fact_roots=FACT_ROOTS)

    @property
    def rules(self) -> LoadedRules:
        return self._rules

    # ------------------------------------------------------------------ run
    def evaluate(
        self,
        session: Session,
        context: FactContext,
        *,
        actor_id: str | None = None,
    ) -> EvaluationReport:
        """Evaluate every applicable rule and persist the findings."""
        establishment = context.establishment
        jurisdiction = establishment.jurisdiction_code
        assessed_on = context.period_end or context.period_start or date.today()

        report = EvaluationReport(
            establishment_id=establishment.id,
            period_start=context.period_start,
            period_end=context.period_end,
            jurisdiction=jurisdiction,
        )

        facts = context.as_facts()
        applicable = self._rules.effective_on(jurisdiction, assessed_on)
        report.rules_considered = len(applicable)

        existing = self._existing_findings(
            session, establishment.id, context.period_start, context.period_end
        )
        seen_keys: set[str] = set()

        for rule, pack_version in applicable:
            outcome = self._run_rule(rule, facts, context)
            outcome.code = rule.code
            report.outcomes.append(outcome)

            if outcome.error:
                report.errors.append(f"{rule.id}: {outcome.error}")

            if not outcome.applied:
                continue
            report.rules_applied += 1

            if outcome.passed is None:
                report.rules_unassessable += 1
                continue

            if outcome.passed:
                # A previously open finding for a rule that now passes is
                # resolved rather than deleted, so the remediation is visible in
                # the establishment's history.
                key = _dedupe_key(rule, establishment.id, context)
                seen_keys.add(key)
                prior = existing.get(key)
                if prior is not None and prior.is_open:
                    prior.status = FindingStatus.RESOLVED
                    prior.status_changed_at = utcnow()
                    prior.status_reason = (
                        "the condition no longer holds on the current documents"
                    )
                continue

            key = _dedupe_key(rule, establishment.id, context)
            seen_keys.add(key)

            finding = self._emit(
                session,
                rule=rule,
                pack_version=pack_version,
                outcome=outcome,
                context=context,
                existing=existing.get(key),
                dedupe_key=key,
                actor_id=actor_id,
            )
            report.findings.append(finding)

        logger.info(
            "rules evaluated",
            extra={
                "establishment_id": establishment.id,
                "considered": report.rules_considered,
                "applied": report.rules_applied,
                "violations": len(report.violations),
                "unassessable": report.rules_unassessable,
                "coverage": report.coverage,
            },
        )
        return report

    # --------------------------------------------------------------- one rule
    def _run_rule(
        self, rule: Rule, facts: dict[str, Any], context: FactContext
    ) -> RuleOutcome:
        # A rule whose required collections are absent is not a violation. The
        # missing document is itself covered by a MISSING_DOCUMENT rule, and
        # failing here as well would report the same gap twice with different
        # severities.
        for requirement in rule.requires:
            value = facts.get(requirement)
            if value is None or (isinstance(value, list | dict) and len(value) == 0):
                return RuleOutcome(
                    rule_id=rule.id,
                    applied=False,
                    passed=None,
                    skipped_reason=f"no {requirement} data held for this period",
                )

        if rule.applicability:
            try:
                applies = self._evaluator.evaluate(rule.applicability, facts)
            except RuleEvaluationError as exc:
                return RuleOutcome(
                    rule_id=rule.id,
                    applied=False,
                    passed=None,
                    error=f"applicability could not be evaluated: {exc}",
                )
            if not applies:
                return RuleOutcome(
                    rule_id=rule.id,
                    applied=False,
                    passed=None,
                    not_applicable=True,
                    skipped_reason="the rule does not apply to this establishment",
                )

        if rule.for_each:
            return self._run_row_rule(rule, facts)
        return self._run_scalar_rule(rule, facts, context)

    def _run_scalar_rule(
        self, rule: Rule, facts: dict[str, Any], context: FactContext
    ) -> RuleOutcome:
        try:
            raw = self._evaluator.evaluate(rule.expression, facts)
        except RuleEvaluationError as exc:
            return RuleOutcome(
                rule_id=rule.id, applied=True, passed=None, error=str(exc)
            )

        # None means the inputs were not determinable. Not a pass and not a
        # violation: unassessed, and reported through coverage.
        if raw is None:
            return RuleOutcome(
                rule_id=rule.id,
                applied=True,
                passed=None,
                skipped_reason="the values this rule depends on are missing",
            )

        passed = bool(raw)
        return RuleOutcome(
            rule_id=rule.id,
            applied=True,
            passed=passed,
            observed={} if passed else self._render(rule.observe, facts),
            expected={} if passed else self._render(rule.expect, facts),
        )

    def _run_row_rule(self, rule: Rule, facts: dict[str, Any]) -> RuleOutcome:
        rows = facts.get(rule.for_each)
        if not isinstance(rows, list) or not rows:
            return RuleOutcome(
                rule_id=rule.id,
                applied=False,
                passed=None,
                skipped_reason=f"no rows in {rule.for_each}",
            )

        failing: list[int] = []
        assessed = 0
        unverified = 0

        for index, row in enumerate(rows):
            # A row that failed verification during reading is not judged. Its
            # figures may be transposed, and a transposition can put a real breach
            # on the compliant side of a threshold just as easily as the reverse.
            # Skipping it and reporting the gap through coverage is honest;
            # evaluating it would produce a verdict we have no basis for.
            if isinstance(row, dict) and row.get(ROW_VERIFIED_KEY) is False:
                unverified += 1
                continue

            row_facts = {**facts, "row": row}
            try:
                raw = self._evaluator.evaluate(rule.expression, row_facts)
            except RuleEvaluationError as exc:
                return RuleOutcome(
                    rule_id=rule.id,
                    applied=True,
                    passed=None,
                    error=f"row {index}: {exc}",
                )

            if raw is None:
                # This row could not be assessed. Other rows still can, so the
                # rule continues rather than abandoning the whole register.
                continue

            assessed += 1
            if not bool(raw):
                failing.append(index)

        if assessed == 0:
            reason = (
                f"all {unverified} row(s) failed verification when the document was "
                "read, so none could be assessed"
                if unverified
                else f"none of the {len(rows)} rows carried the values this rule needs"
            )
            return RuleOutcome(
                rule_id=rule.id,
                applied=True,
                passed=None,
                skipped_reason=reason,
                unverified_rows=unverified,
            )

        if not failing:
            return RuleOutcome(
                rule_id=rule.id,
                applied=True,
                passed=True,
                unverified_rows=unverified,
            )

        observed = self._render(rule.observe, facts)
        observed.setdefault("rows_assessed", assessed)
        observed["rows_failing"] = len(failing)
        if unverified:
            # Recorded on the finding so an inspector knows the count may be
            # understated: more workers could be affected among the rows we
            # declined to judge.
            observed["rows_not_assessed"] = unverified

        return RuleOutcome(
            rule_id=rule.id,
            applied=True,
            passed=False,
            failing_row_indices=failing,
            observed=observed,
            expected=self._render(rule.expect, facts),
            unverified_rows=unverified,
        )

    def _render(
        self, expressions: dict[str, str], facts: dict[str, Any]
    ) -> dict[str, Any]:
        """Evaluate the observe/expect expressions recorded on a finding.

        A failure here must never abandon a finding: an unreadable observation is
        a presentation problem, whereas losing the finding is a compliance
        problem. So each one is caught individually and reported in place.
        """
        rendered: dict[str, Any] = {}
        for name, expression in expressions.items():
            try:
                value = self._evaluator.evaluate(expression, facts)
            except RuleEvaluationError as exc:
                rendered[name] = f"(could not be computed: {exc})"
                continue
            rendered[name] = _jsonable(value)
        return rendered

    # ---------------------------------------------------------------- emit
    def _emit(
        self,
        session: Session,
        *,
        rule: Rule,
        pack_version: str,
        outcome: RuleOutcome,
        context: FactContext,
        existing: Finding | None,
        dedupe_key: str,
        actor_id: str | None,
    ) -> Finding:
        establishment = context.establishment
        wage_floor = context.namespaces.get("wage_floor") or {}

        affected, exposure, confidence, evidence = self._evidence(
            rule, outcome, context
        )

        # A rule written as a set comparison over the whole register — "who is in
        # the wage register but not in the EPF filing" — has no row to attach, so
        # the row-level path yields nothing. Without this, the most valuable finding
        # in the system reports zero affected workers and an inspector is told
        # someone is missing from the provident fund with no idea how many.
        if affected is None:
            affected = _affected_from_observed(outcome.observed)

        # Only stamp a wage-rate provenance when the rule actually consulted one.
        # A REFERENCE marker on an unrelated finding would misrepresent it.
        rate_source: WageRateSource | None = None
        if "wage_floor" in (rule.requires or []) and wage_floor.get("source"):
            try:
                rate_source = WageRateSource(str(wage_floor["source"]))
            except ValueError:
                rate_source = None

        message = rule.message.for_locale("en")
        remediation = rule.remediation.for_locale("en") if rule.remediation else None

        if existing is not None:
            # Same issue, seen again. Update in place so history and any
            # inspector decision on it survive.
            # The rule's declared severity is the baseline. Any contextual
            # assessment made later overwrites `severity`, so re-evaluation must
            # reset both together or a stale assessment would outlive the facts
            # it was made from.
            existing.severity = rule.severity
            existing.baseline_severity = rule.severity
            existing.severity_rationale = None
            existing.severity_assessed = False
            existing.rule_pack_version = pack_version
            existing.citation = rule.citation
            existing.rule_basis = rule.basis
            existing.title = rule.title
            existing.message = message
            existing.remediation = remediation
            existing.observed = outcome.observed
            existing.expected = outcome.expected
            existing.affected_worker_count = affected
            existing.exposure_paise = exposure
            existing.extraction_confidence = confidence
            existing.wage_rate_source = rate_source

            if existing.status is FindingStatus.RESOLVED:
                # It came back. Reopening rather than leaving it resolved is what
                # makes a repeat offence visible.
                existing.status = FindingStatus.OPEN
                existing.status_changed_at = utcnow()
                existing.status_reason = "the condition was found again on re-evaluation"

            existing.evidence.clear()
            for item in evidence:
                existing.evidence.append(item)

            session.flush()
            return existing

        finding = Finding(
            establishment_id=establishment.id,
            kind=rule.kind,
            code=rule.code,
            severity=rule.severity,
            baseline_severity=rule.severity,
            rule_id=rule.id,
            rule_pack_version=pack_version,
            jurisdiction=establishment.jurisdiction_code,
            citation=rule.citation,
            rule_basis=rule.basis,
            title=rule.title,
            message=message,
            remediation=remediation,
            observed=outcome.observed,
            expected=outcome.expected,
            period_start=context.period_start,
            period_end=context.period_end,
            affected_worker_count=affected,
            exposure_paise=exposure,
            wage_rate_source=rate_source,
            extraction_confidence=confidence,
            status=FindingStatus.OPEN,
            dedupe_key=dedupe_key,
        )
        for item in evidence:
            finding.evidence.append(item)

        session.add(finding)
        session.flush()

        audit_service.record(
            session,
            action=AuditAction.FINDING_CREATED,
            subject_type="finding",
            subject_id=finding.id,
            actor_id=actor_id,
            establishment_id=establishment.id,
            detail={
                "rule_id": rule.id,
                "rule_pack_version": pack_version,
                "severity": str(rule.severity),
                "kind": str(rule.kind),
                "citation": rule.citation,
                "affected_worker_count": affected,
            },
        )
        return finding

    def _evidence(
        self, rule: Rule, outcome: RuleOutcome, context: FactContext
    ) -> tuple[int | None, int | None, float | None, list[FindingEvidence]]:
        """Build evidence rows, and derive affected count, exposure and confidence.

        The evidence is the part that makes a finding believable. Without a page
        and a box, a finding is an assertion an employer can simply deny; with
        them, an inspector opens the scan and sees the cell.
        """
        if not rule.for_each or not outcome.failing_row_indices:
            return None, None, None, []

        namespace = rule.for_each
        rows = context.rows(namespace)
        indices = outcome.failing_row_indices

        affected = len({
            rows[i].get("worker_key")
            for i in indices
            if i < len(rows) and rows[i].get("worker_key")
        }) or len(indices)

        exposure = _exposure(rule, rows, indices)

        evidence: list[FindingEvidence] = []
        confidences: list[float] = []

        for index in indices[:MAX_EVIDENCE_PER_FINDING]:
            if index >= len(rows):
                continue
            row = rows[index]
            source = context.source_for(namespace, index)
            provenance: dict = source.get("provenance") or {}

            field_name, cell = _pick_cell(rule, provenance)
            page = cell.get("page") if cell else None
            bbox = cell.get("bbox") if cell else None

            if cell and cell.get("agreement") in {"agreed", "ocr_only"}:
                confidences.append(1.0)
            elif cell:
                confidences.append(0.5)

            evidence.append(
                FindingEvidence(
                    document_id=source.get("document_id"),
                    page_number=page,
                    bbox=bbox,
                    field_name=field_name,
                    value_shown=_display_value(row, field_name),
                    row_reference=source.get("row_reference"),
                    note=None
                    if bbox
                    else "this page was read without positional data, so evidence "
                    "is at page level",
                )
            )

        if len(indices) > MAX_EVIDENCE_PER_FINDING:
            evidence.append(
                FindingEvidence(
                    note=(
                        f"{len(indices) - MAX_EVIDENCE_PER_FINDING} further rows "
                        "are affected and are not listed individually"
                    )
                )
            )

        confidence = (
            round(sum(confidences) / len(confidences), 3) if confidences else None
        )
        return affected, exposure, confidence, evidence

    # ------------------------------------------------------------ existing
    def _existing_findings(
        self,
        session: Session,
        establishment_id: str,
        period_start: date | None,
        period_end: date | None,
    ) -> dict[str, Finding]:
        query = select(Finding).where(Finding.establishment_id == establishment_id)
        if period_start is not None:
            query = query.where(Finding.period_start == period_start)
        if period_end is not None:
            query = query.where(Finding.period_end == period_end)

        return {
            finding.dedupe_key: finding
            for finding in session.execute(query).scalars().all()
        }


# -------------------------------------------------------------------- helpers
def _dedupe_key(rule: Rule, establishment_id: str, context: FactContext) -> str:
    """Stable identity for "this issue, here, for this period".

    Deliberately excludes which rows failed. If it included them, one extra
    affected worker next month would create a second finding for the same
    underlying problem, and the establishment's history would read as two
    offences instead of one continuing one.
    """
    parts = [
        rule.id,
        establishment_id,
        context.period_start.isoformat() if context.period_start else "-",
        context.period_end.isoformat() if context.period_end else "-",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:48]


#: Observation keys that count affected workers. Read in order, so the most
#: specific measure wins where a rule records more than one.
_AFFECTED_KEYS: tuple[str, ...] = (
    "uncovered_workers",
    "workers_below_floor",
    "workers_with_overtime",
    "workers_with_unpaid_overtime",
    "workers_underpaid_days",
    "shortfall",
    "rows_failing",
    "gap",
)


def _affected_from_observed(observed: dict[str, Any]) -> int | None:
    """Recover an affected-worker count from what the rule recorded.

    Used for rules that compare whole sets rather than iterating rows. The count is
    already in the observation — "uncovered_workers: 2" — it simply has no row to
    hang off, so it is lifted onto the finding here rather than being lost.
    """
    for key in _AFFECTED_KEYS:
        value = observed.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, float) and value > 0:
            return int(value)
    return None


def _exposure(rule: Rule, rows: list[dict], indices: list[int]) -> int | None:
    """Money at stake, where the rule makes that computable.

    Drives triage better than severity alone: a HIGH affecting one worker matters
    less than a MEDIUM affecting two hundred, and only a rupee figure makes that
    comparable.
    """
    field_by_rule = {
        "WAGES.FLOOR.STATE_MINIMUM": "shortfall_vs_floor_paise",
        "WAGES.OVERTIME.RATE": "overtime_paise",
        "SS.EPF.WAGE_BASE_UNDERSTATED": "register_wages_paise",
    }
    field_name = field_by_rule.get(rule.id)
    if field_name is None:
        return None

    total = 0
    found = False
    for index in indices:
        if index >= len(rows):
            continue
        value = rows[index].get(field_name)
        if isinstance(value, int | float):
            total += int(value)
            found = True

    return total if found else None


def _pick_cell(rule: Rule, provenance: dict) -> tuple[str | None, dict]:
    """Choose which cell to highlight for a rule.

    Preference order per rule, because the cell that proves the point differs:
    a deduction-cap finding should highlight the deductions column, not the name.
    Falls back to any cell with coordinates rather than none, since a highlight on
    the right row is still useful.
    """
    preferred = _EVIDENCE_FIELDS.get(rule.id, ())

    for field_name in preferred:
        cell = provenance.get(field_name)
        if isinstance(cell, dict) and cell.get("bbox"):
            return field_name, cell

    for field_name, cell in provenance.items():
        if isinstance(cell, dict) and cell.get("bbox"):
            return field_name, cell

    for field_name in preferred:
        cell = provenance.get(field_name)
        if isinstance(cell, dict):
            return field_name, cell

    if provenance:
        field_name, cell = next(iter(provenance.items()))
        return field_name, cell if isinstance(cell, dict) else {}

    return None, {}


#: Which column proves each row-level rule. Anything not listed falls back to the
#: first cell with coordinates.
_EVIDENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "WAGES.OVERTIME.RATE": ("overtime_rate_paise", "overtime_paise", "overtime_hours"),
    "WAGES.PAYMENT.MONTHLY_BY_SEVENTH": ("paid_on",),
    "WAGES.PAYMENT.FINAL_SETTLEMENT": ("paid_on",),
    "WAGES.DEDUCTIONS.HALF_CAP": ("deductions_paise", "gross_paise"),
    "WAGES.DEFINITION.EXCLUDED_HALF": ("other_allowances_paise", "basic_paise"),
    "WAGES.FLOOR.STATE_MINIMUM": ("basic_paise", "da_paise", "days_paid"),
    "WAGES.ARITHMETIC.GROSS": ("gross_paise",),
    "WAGES.ARITHMETIC.NET": ("net_paid_paise",),
    "WAGES.REST_DAY.WEEKLY": ("worker_name_as_printed",),
    "SS.EPF.WAGE_BASE_UNDERSTATED": ("wage_base_paise",),
    "SS.EPF.DEPOSIT_TIMELINESS": ("deposited_on",),
    "SS.EPF.CONTRIBUTION_ARITHMETIC": ("employee_share_paise", "wage_base_paise"),
    "OSH.HOURS.DAILY_CAP": ("max_daily_hours",),
    "OSH.HOURS.WEEKLY_CAP": ("max_weekly_hours",),
    "OSH.ATTENDANCE.DAYS_PAID_MATCH": ("days_paid", "days_present"),
    "OSH.OVERTIME.HOURS_PAID": ("overtime_paise", "overtime_hours"),
    "OSH.ACCIDENT.NOTIFICATION_TIMELINESS": ("occurred_on",),
}


def _display_value(row: dict, field_name: str | None) -> str | None:
    if not field_name:
        return None
    value = row.get(field_name)
    if value is None:
        return None
    if field_name.endswith("_paise") and isinstance(value, int | float):
        return f"₹{value / 100:,.2f}"
    return str(value)[:255]


def _jsonable(value: Any) -> Any:
    """Make a value safe to store in a JSON column."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list | tuple | set):
        return [_jsonable(item) for item in list(value)[:50]]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in list(value.items())[:50]}
    return str(value)[:500]


def severity_weight(severity: Severity) -> int:
    """Relative weight of each severity in scoring.

    Steep on purpose: a critical breach is not three medium ones. Wage
    underpayment and an unnotified fatality should dominate a score that also
    counts a missing canteen record.
    """
    return {
        Severity.CRITICAL: 40,
        Severity.HIGH: 20,
        Severity.MEDIUM: 8,
        Severity.LOW: 3,
        Severity.INFO: 0,
    }[severity]


#: Severity in order of gravity. Used to bound how far a contextual assessment may
#: move a finding from the severity its rule declared.
SEVERITY_LADDER: tuple[Severity, ...] = (
    Severity.INFO,
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)


def resolve_assessed_severity(
    *,
    baseline: Severity,
    opinion: Severity | None,
    verdict_is_sound: bool,
    rationale: str | None,
) -> tuple[Severity, str | None]:
    """Reconcile a rule's declared severity with what the review saw in context.

    A rule cannot see magnitude, spread or repetition. ``WAGES.DEDUCTIONS.HALF_CAP``
    is HIGH whether the deduction was 51% for one worker in one month or 90% for
    every worker three months running. Those are not the same thing, and scoring
    them identically is the flaw this exists to correct.

    What it must not become is a model rewriting the statute's own view of gravity,
    so the adjustment is bounded hard:

    * **One step, either way.** A HIGH may become CRITICAL or MEDIUM, never LOW.
      The rule's severity carries a legislative judgement about the class of
      breach; context can sharpen it, not replace it.
    * **Never INFO.** INFO carries zero scoring weight, so allowing it would let a
      single model call erase a real breach from the score entirely.
    * **Escalation only on a sound verdict.** If the review is itself unsure the
      finding holds, it has no business arguing the finding is graver.
    * **A reason is required.** An adjustment with no stated reason is not an
      assessment, and it would be indefensible if an employer asked why. Without
      one the baseline stands.

    Returns the severity to record and the rationale to store with it. The
    rationale is None when nothing moved, so ``severity_rationale`` stays empty
    unless there is something to justify.
    """
    if opinion is None or opinion is baseline:
        return baseline, None

    reason = (rationale or "").strip()
    if not reason:
        return baseline, None

    try:
        base_index = SEVERITY_LADDER.index(baseline)
        want_index = SEVERITY_LADDER.index(opinion)
    except ValueError:  # pragma: no cover - both come from the same enum
        return baseline, None

    direction = 1 if want_index > base_index else -1
    if direction > 0 and not verdict_is_sound:
        return baseline, None

    target = SEVERITY_LADDER[base_index + direction]
    if target is Severity.INFO:
        return baseline, None

    return target, reason


def code_of(finding: Finding) -> LabourCode | None:
    return finding.code


def is_scored(finding: Finding) -> bool:
    """Whether a finding may affect a compliance score.

    Anomalies never do. A statistical outlier is not a breach of law, and a score
    that moved on one would be indefensible the moment an employer asked which
    section they had broken.
    """
    if finding.kind is FindingKind.ANOMALY:
        return False
    return finding.status in {
        FindingStatus.OPEN,
        FindingStatus.ACKNOWLEDGED,
        FindingStatus.DISPUTED,
    }
