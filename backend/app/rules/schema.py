"""Rule pack schema.

Rules are data, validated on load. Three fields are mandatory and enforced here
rather than by convention:

* ``citation`` — the statutory provision. A finding without one is unusable when
  an employer disputes it.
* ``source_ref`` — where the citation was read from, so a reviewer can check it.
* ``basis`` — what the rule's operative number rests on. There is no default:
  every rule must state whether its number came from the Act, from Rules not yet
  obtained, or whether it needs no external number at all.

``for_each`` decides evaluation shape. When set, the expression runs once per row
of that collection with ``row`` bound, and the rule fails if any row fails. When
absent, the expression runs once against the whole fact context.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import FindingKind, LabourCode, RuleBasis, Severity


class RuleMessages(BaseModel):
    """Localised text. English is required; Hindi is strongly preferred."""

    en: str
    hi: str | None = None

    def for_locale(self, locale: str) -> str:
        if locale.startswith("hi") and self.hi:
            return self.hi
        return self.en


class RuleFixture(BaseModel):
    """A worked example proving the rule behaves as intended.

    Every rule ships one passing and one failing case. This is what stops a
    subtly inverted comparison from shipping — the commonest and most damaging
    rule bug, because it turns compliant employers into violators.
    """

    name: str
    facts: dict
    should_pass: bool
    note: str | None = None


class Rule(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(pattern=r"^[A-Z][A-Z0-9]*(\.[A-Z0-9_]+)+$")
    code: LabourCode
    kind: FindingKind = FindingKind.NON_COMPLIANCE
    severity: Severity
    weight: int = Field(ge=1, le=20)

    title: str
    citation: str = Field(min_length=3)
    source_ref: str = Field(min_length=3)
    basis: RuleBasis
    """Required. Stating it forces the question to be answered per rule instead of
    inherited from a default nobody revisits."""

    # ------------------------------------------------------------ applicability
    # Evaluated first. When it is false the rule does not apply and no finding is
    # raised — distinct from applying and passing.
    applicability: str | None = None
    # Collections that must be present for this rule to be meaningful. When one
    # is missing the rule is skipped and a MISSING_DOCUMENT finding covers it.
    requires: list[str] = Field(default_factory=list)

    effective_from: str | None = None
    effective_to: str | None = None

    # -------------------------------------------------------------- evaluation
    for_each: str | None = None
    """When set, ``expression`` is evaluated once per row of this collection with
    ``row`` in scope, and the rule fails if any row fails."""

    expression: str
    """Evaluates True when COMPLIANT. Inverting this convention per-rule would
    make the pack impossible to read safely."""

    # Expressions whose values are recorded on the finding for explainability.
    observe: dict[str, str] = Field(default_factory=dict)
    expect: dict[str, str] = Field(default_factory=dict)

    message: RuleMessages
    remediation: RuleMessages | None = None

    fixtures: list[RuleFixture] = Field(default_factory=list)

    @field_validator("expression")
    @classmethod
    def _expression_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("expression must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def _for_each_needs_row(self) -> Rule:
        if self.for_each and "row" not in self.expression:
            raise ValueError(
                f"rule {self.id}: for_each is set but the expression never "
                "references 'row', which is almost certainly a mistake"
            )
        if not self.for_each and "row." in self.expression:
            raise ValueError(
                f"rule {self.id}: expression references 'row' but for_each is "
                "not set, so 'row' will be unbound"
            )
        return self

    @property
    def is_advisory(self) -> bool:
        """Anomalies inform an inspector but never affect a score."""
        return self.kind is FindingKind.ANOMALY

    @property
    def needs_notified_rules(self) -> bool:
        """True when the number used here is not in the Act and the notified
        Rules that fix it have not been obtained. The rule still runs, but a
        finding from it must not be enforced without checking that notification.
        """
        return self.basis.needs_notified_rules


class RulePack(BaseModel):
    model_config = {"extra": "forbid"}

    pack: str
    version: str
    # "IN" for national, "IN/MH" for a state overlay that shadows national rules
    # of the same id.
    jurisdiction: str = "IN"
    description: str | None = None
    rules: list[Rule]

    @property
    def qualified_version(self) -> str:
        """Recorded on every finding, e.g. ``wages@2026.01``."""
        return f"{self.pack}@{self.version}"

    @property
    def is_overlay(self) -> bool:
        return "/" in self.jurisdiction

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> RulePack:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"duplicate rule id in pack {self.pack}: {rule.id}")
            seen.add(rule.id)
        return self


class RuleIssue(BaseModel):
    """A problem found by the rule-pack checker."""

    rule_id: str
    pack: str
    level: Literal["error", "warning"]
    message: str
