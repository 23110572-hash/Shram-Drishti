"""Rule pack loading, jurisdiction overlays and validation.

Overlay resolution: a state pack may redefine a rule that exists nationally. The
state version wins for establishments in that state, because most operative
thresholds under the Codes are notified by states. Resolution is by rule id, so
``IN/MH`` redefining ``WAGES.FLOOR`` shadows the national ``WAGES.FLOOR`` for
Maharashtra only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.rules.evaluator import Evaluator, RuleSyntaxError
from app.rules.functions import FACT_ROOTS, RULE_FUNCTIONS
from app.rules.schema import Rule, RuleIssue, RulePack

logger = logging.getLogger(__name__)


class RulePackError(Exception):
    pass


@dataclass
class LoadedRules:
    """All packs, plus the resolved view for a given jurisdiction."""

    packs: list[RulePack] = field(default_factory=list)
    issues: list[RuleIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.level == "error" for issue in self.issues)

    @property
    def all_rules(self) -> list[Rule]:
        return [rule for pack in self.packs for rule in pack.rules]

    @property
    def unverified_rules(self) -> list[Rule]:
        """Rules whose threshold has not been confirmed against primary text."""
        return [rule for rule in self.all_rules if not rule.verified]

    def version_for(self, rule_id: str) -> str:
        for pack in self.packs:
            if any(r.id == rule_id for r in pack.rules):
                return pack.qualified_version
        return "unknown"

    def resolve(self, jurisdiction: str) -> list[tuple[Rule, str]]:
        """Rules applying to a jurisdiction, as ``(rule, pack_version)``.

        National rules first, then state overlays replacing matching ids.
        """
        resolved: dict[str, tuple[Rule, str]] = {}

        for pack in self.packs:
            if pack.is_overlay:
                continue
            for rule in pack.rules:
                resolved[rule.id] = (rule, pack.qualified_version)

        for pack in self.packs:
            if not pack.is_overlay or pack.jurisdiction != jurisdiction:
                continue
            for rule in pack.rules:
                if rule.id in resolved:
                    logger.debug(
                        "state overlay replaces national rule",
                        extra={"rule_id": rule.id, "jurisdiction": jurisdiction},
                    )
                resolved[rule.id] = (rule, pack.qualified_version)

        return list(resolved.values())

    def effective_on(
        self, jurisdiction: str, on: date
    ) -> list[tuple[Rule, str]]:
        """Resolved rules in force on a date.

        A rule that came into force after the period being assessed must not
        fire against it — that would be retrospective enforcement.
        """
        out: list[tuple[Rule, str]] = []
        for rule, version in self.resolve(jurisdiction):
            if rule.effective_from and on < date.fromisoformat(rule.effective_from):
                continue
            if rule.effective_to and on > date.fromisoformat(rule.effective_to):
                continue
            out.append((rule, version))
        return out


def _build_evaluator() -> Evaluator:
    return Evaluator(functions=RULE_FUNCTIONS, fact_roots=FACT_ROOTS)


def load_pack_file(path: Path) -> RulePack:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RulePackError(f"{path.name}: invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise RulePackError(f"{path.name}: expected a mapping at the top level")

    try:
        return RulePack.model_validate(raw)
    except ValidationError as exc:
        raise RulePackError(f"{path.name}: {exc}") from exc


def validate_pack(pack: RulePack, evaluator: Evaluator | None = None) -> list[RuleIssue]:
    """Static checks over one pack.

    Runs at load time so a broken rule never reaches an evaluation. Compiling
    every expression up front is the important part: a syntax error discovered
    mid-run would abandon an inspection halfway through.
    """
    evaluator = evaluator or _build_evaluator()
    issues: list[RuleIssue] = []

    def error(rule_id: str, message: str) -> None:
        issues.append(
            RuleIssue(rule_id=rule_id, pack=pack.pack, level="error", message=message)
        )

    def warn(rule_id: str, message: str) -> None:
        issues.append(
            RuleIssue(rule_id=rule_id, pack=pack.pack, level="warning", message=message)
        )

    for rule in pack.rules:
        # Every expression the rule owns is compiled here, at load time. A syntax
        # error discovered mid-evaluation would abandon an inspection halfway
        # through, so it has to surface now.
        expressions: list[tuple[str, str]] = [("expression", rule.expression)]
        if rule.applicability:
            expressions.append(("applicability", rule.applicability))
        expressions.extend((f"observe.{k}", v) for k, v in rule.observe.items())
        expressions.extend((f"expect.{k}", v) for k, v in rule.expect.items())

        for label, expression in expressions:
            try:
                evaluator.compile(expression)
            except RuleSyntaxError as exc:
                error(rule.id, f"{label}: {exc}")

        if not rule.verified:
            warn(
                rule.id,
                f"threshold not verified against primary text (source_ref: {rule.source_ref})",
            )

        if not rule.fixtures:
            error(rule.id, "no fixtures: every rule needs a passing and a failing case")
        else:
            if not any(f.should_pass for f in rule.fixtures):
                error(rule.id, "no fixture asserts the compliant case")
            if not any(not f.should_pass for f in rule.fixtures):
                error(rule.id, "no fixture asserts the violating case")

        if rule.message.hi is None:
            warn(rule.id, "no Hindi message")

        if rule.for_each and rule.for_each not in FACT_ROOTS:
            error(
                rule.id,
                f"for_each references {rule.for_each!r}, which is not a fact namespace",
            )

        for requirement in rule.requires:
            if requirement not in FACT_ROOTS:
                error(rule.id, f"requires unknown collection {requirement!r}")

    return issues


def run_fixtures(pack: RulePack, evaluator: Evaluator | None = None) -> list[RuleIssue]:
    """Execute every fixture and report those whose outcome is wrong.

    This is the safety net against an inverted comparison. A rule that reports
    compliant employers as violators is worse than no rule at all.
    """
    evaluator = evaluator or _build_evaluator()
    issues: list[RuleIssue] = []

    for rule in pack.rules:
        for fixture in rule.fixtures:
            try:
                # Applicability first, exactly as the engine does it. A fixture
                # asserting "below the threshold, so nothing is raised" is a
                # genuinely valuable case — it is what proves a 300-worker
                # obligation does not fire on a 120-worker establishment — and
                # ignoring applicability here would report it as a failure.
                if rule.applicability and not evaluator.evaluate(
                    rule.applicability, fixture.facts
                ):
                    outcome = True
                elif rule.for_each:
                    rows = fixture.facts.get(rule.for_each) or []
                    outcome = all(
                        evaluator.evaluate_bool(
                            rule.expression, {**fixture.facts, "row": row}
                        )
                        for row in rows
                    )
                else:
                    outcome = evaluator.evaluate_bool(rule.expression, fixture.facts)
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    RuleIssue(
                        rule_id=rule.id,
                        pack=pack.pack,
                        level="error",
                        message=f"fixture {fixture.name!r} raised {type(exc).__name__}: {exc}",
                    )
                )
                continue

            if outcome != fixture.should_pass:
                issues.append(
                    RuleIssue(
                        rule_id=rule.id,
                        pack=pack.pack,
                        level="error",
                        message=(
                            f"fixture {fixture.name!r} expected "
                            f"{'pass' if fixture.should_pass else 'fail'} "
                            f"but the rule {'passed' if outcome else 'failed'}"
                        ),
                    )
                )

    return issues


def load_rules(directory: Path, *, run_fixtures_too: bool = True) -> LoadedRules:
    """Load and validate every pack under ``directory``."""
    result = LoadedRules()

    if not directory.exists():
        logger.warning("rule pack directory missing", extra={"path": str(directory)})
        return result

    evaluator = _build_evaluator()

    for path in sorted(directory.rglob("*.yaml")):
        try:
            pack = load_pack_file(path)
        except RulePackError as exc:
            result.issues.append(
                RuleIssue(
                    rule_id="-", pack=path.stem, level="error", message=str(exc)
                )
            )
            continue

        result.packs.append(pack)
        result.issues.extend(validate_pack(pack, evaluator))
        if run_fixtures_too:
            result.issues.extend(run_fixtures(pack, evaluator))

    logger.info(
        "rule packs loaded",
        extra={
            "packs": len(result.packs),
            "rules": len(result.all_rules),
            "unverified": len(result.unverified_rules),
            "errors": sum(1 for i in result.issues if i.level == "error"),
        },
    )
    return result


_cache: LoadedRules | None = None


def get_rules() -> LoadedRules:
    global _cache
    if _cache is None:
        from app.config import PROJECT_ROOT

        _cache = load_rules(PROJECT_ROOT / "rule_packs", run_fixtures_too=False)
    return _cache


def reset_rules() -> None:
    global _cache
    _cache = None
