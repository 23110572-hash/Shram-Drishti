"""Rule pack inspection.

Read-only, and open to every authenticated role on purpose. An employer accused
of a breach is entitled to see the exact test that was applied, the section it
comes from, and whether that threshold has been confirmed against the primary
statutory text. A compliance system that will not show its own rules cannot
expect to be trusted by the people it judges.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.deps import CurrentUser
from app.models.enums import FindingKind, LabourCode, RuleBasis, Severity
from app.rules.loader import get_rules, reset_rules

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["rules"])


class FixtureOut(BaseModel):
    name: str
    should_pass: bool
    note: str | None


class RuleOut(BaseModel):
    id: str
    code: LabourCode
    kind: FindingKind
    severity: Severity
    weight: int
    title: str
    citation: str
    source_ref: str
    basis: RuleBasis
    #: Convenience for the UI, which needs the caveat far more often than the
    #: basis itself. True only for RULES_PENDING.
    awaiting_notification: bool
    applicability: str | None
    requires: list[str]
    for_each: str | None
    expression: str
    message_en: str
    message_hi: str | None
    remediation_en: str | None
    remediation_hi: str | None
    pack: str
    pack_version: str
    jurisdiction: str
    fixture_count: int
    fixtures: list[FixtureOut]


class PackOut(BaseModel):
    pack: str
    version: str
    jurisdiction: str
    description: str | None
    rule_count: int
    #: Rules that need no further document to stand: the number is in the Act, or
    #: there is no external number at all.
    sound_count: int
    awaiting_notification_count: int
    is_overlay: bool


class RulesOverview(BaseModel):
    packs: list[PackOut]
    total_rules: int
    sound_rules: int
    awaiting_notification: int
    #: Rules whose operative number the Act leaves to the appropriate Government,
    #: where that notification has not been obtained. Surfaced prominently rather
    #: than buried, because these must not be enforced as they stand.
    awaiting_notification_ids: list[str]
    #: Counts per basis, so the Rules page can explain the split rather than
    #: reducing it to a pass/fail figure.
    by_basis: dict[str, int]
    by_code: dict[str, int]
    by_severity: dict[str, int]
    by_kind: dict[str, int]
    issues: list[dict[str, Any]]


@router.get("", response_model=RulesOverview)
def overview(user: CurrentUser) -> RulesOverview:
    loaded = get_rules()
    rules = loaded.all_rules

    by_code: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_kind: dict[str, int] = {}

    for rule in rules:
        by_code[rule.code.value] = by_code.get(rule.code.value, 0) + 1
        by_severity[rule.severity.value] = by_severity.get(rule.severity.value, 0) + 1
        by_kind[rule.kind.value] = by_kind.get(rule.kind.value, 0) + 1

    pending = loaded.rules_pending_notification

    return RulesOverview(
        packs=[
            PackOut(
                pack=pack.pack,
                version=pack.version,
                jurisdiction=pack.jurisdiction,
                description=pack.description,
                rule_count=len(pack.rules),
                sound_count=sum(
                    1 for r in pack.rules if not r.needs_notified_rules
                ),
                awaiting_notification_count=sum(
                    1 for r in pack.rules if r.needs_notified_rules
                ),
                is_overlay=pack.is_overlay,
            )
            for pack in loaded.packs
        ],
        total_rules=len(rules),
        sound_rules=len(rules) - len(pending),
        awaiting_notification=len(pending),
        awaiting_notification_ids=[r.id for r in pending],
        by_basis={
            basis.value: len(group) for basis, group in loaded.by_basis().items()
        },
        by_code=by_code,
        by_severity=by_severity,
        by_kind=by_kind,
        issues=[issue.model_dump() for issue in loaded.issues],
    )


@router.get("/list", response_model=list[RuleOut])
def list_rules(
    user: CurrentUser,
    code: Annotated[LabourCode | None, Query()] = None,
    basis: Annotated[RuleBasis | None, Query()] = None,
    awaiting_notification: Annotated[bool | None, Query()] = None,
    jurisdiction: Annotated[str | None, Query()] = None,
) -> list[RuleOut]:
    loaded = get_rules()
    out: list[RuleOut] = []

    for pack in loaded.packs:
        if jurisdiction and pack.jurisdiction != jurisdiction:
            continue
        for rule in pack.rules:
            if code and rule.code is not code:
                continue
            if basis is not None and rule.basis is not basis:
                continue
            if (
                awaiting_notification is not None
                and rule.needs_notified_rules is not awaiting_notification
            ):
                continue
            out.append(_render(rule, pack))

    # Rules awaiting a notification first. Those are the ones a reviewer needs to
    # look at, so burying them below thirty sound ones would defeat the purpose.
    out.sort(key=lambda r: (not r.awaiting_notification, r.code.value, r.id))
    return out


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(rule_id: str, user: CurrentUser) -> RuleOut:
    loaded = get_rules()
    for pack in loaded.packs:
        for rule in pack.rules:
            if rule.id == rule_id:
                return _render(rule, pack)
    raise HTTPException(status_code=404, detail="rule not found")


@router.post("/reload", response_model=RulesOverview)
def reload_rules(user: CurrentUser) -> RulesOverview:
    """Re-read the rule packs from disk.

    Restricted to administrators. A rule pack change alters what every
    establishment is judged against, so it is not a routine operation.
    """
    from app.models.enums import Role

    if user.role is not Role.ADMIN:
        raise HTTPException(status_code=403, detail="administrators only")

    reset_rules()
    return overview(user)


def _render(rule: Any, pack: Any) -> RuleOut:
    return RuleOut(
        id=rule.id,
        code=rule.code,
        kind=rule.kind,
        severity=rule.severity,
        weight=rule.weight,
        title=rule.title,
        citation=rule.citation,
        source_ref=rule.source_ref,
        basis=rule.basis,
        awaiting_notification=rule.needs_notified_rules,
        applicability=rule.applicability,
        requires=list(rule.requires),
        for_each=rule.for_each,
        expression=rule.expression,
        message_en=rule.message.en,
        message_hi=rule.message.hi,
        remediation_en=rule.remediation.en if rule.remediation else None,
        remediation_hi=rule.remediation.hi if rule.remediation else None,
        pack=pack.pack,
        pack_version=pack.version,
        jurisdiction=pack.jurisdiction,
        fixture_count=len(rule.fixtures),
        fixtures=[
            FixtureOut(
                name=fixture.name, should_pass=fixture.should_pass, note=fixture.note
            )
            for fixture in rule.fixtures
        ],
    )
