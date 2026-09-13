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
from app.models.enums import FindingKind, LabourCode, Severity
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
    verified: bool
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
    verified_count: int
    unverified_count: int
    is_overlay: bool


class RulesOverview(BaseModel):
    packs: list[PackOut]
    total_rules: int
    verified_rules: int
    unverified_rules: int
    #: Rules whose threshold has not been confirmed against primary statutory
    #: text. Surfaced prominently rather than buried, because these must not be
    #: enforced without checking the notified Rules.
    unverified_rule_ids: list[str]
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

    return RulesOverview(
        packs=[
            PackOut(
                pack=pack.pack,
                version=pack.version,
                jurisdiction=pack.jurisdiction,
                description=pack.description,
                rule_count=len(pack.rules),
                verified_count=sum(1 for r in pack.rules if r.verified),
                unverified_count=sum(1 for r in pack.rules if not r.verified),
                is_overlay=pack.is_overlay,
            )
            for pack in loaded.packs
        ],
        total_rules=len(rules),
        verified_rules=sum(1 for r in rules if r.verified),
        unverified_rules=len(loaded.unverified_rules),
        unverified_rule_ids=[r.id for r in loaded.unverified_rules],
        by_code=by_code,
        by_severity=by_severity,
        by_kind=by_kind,
        issues=[issue.model_dump() for issue in loaded.issues],
    )


@router.get("/list", response_model=list[RuleOut])
def list_rules(
    user: CurrentUser,
    code: Annotated[LabourCode | None, Query()] = None,
    verified: Annotated[bool | None, Query()] = None,
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
            if verified is not None and rule.verified is not verified:
                continue
            out.append(_render(rule, pack))

    # Unverified first. These are the rules a reviewer needs to look at, so
    # burying them below eighty verified ones would defeat the purpose.
    out.sort(key=lambda r: (r.verified, r.code.value, r.id))
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
        verified=rule.verified,
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
