"""Rule pack checker.

Run as ``python -m app.cli check-rules``.

This is the closest thing in the project to a legal review gate. It refuses to
pass a rule pack unless every rule can prove itself:

* **A citation and a source reference.** A finding without a statutory provision
  is unusable the moment an employer disputes it, and a citation nobody can trace
  back to a document is not much better.
* **A passing and a failing fixture, both of which behave.** This is the check
  that matters most. The single most damaging rule bug is an inverted
  comparison — ``<=`` where ``>=`` belongs — because it turns compliant employers
  into violators and does so silently, with a confident citation attached. A
  fixture pair catches it immediately.
* **A compilable expression.** Every expression is parsed and validated against
  the evaluator's allow-list here, so a syntax error surfaces now rather than
  halfway through an inspection.

It also reports, without failing, every rule whose operative number the Act leaves
to a government notification that has not been obtained. Those rules are usable —
they are shown to inspectors and weighted lightly — but somebody has to know they
exist. Rules that need no external number at all are reported separately, because
they are not in the same position and lumping them together told nobody anything.

Exit codes: 0 clean, 1 errors found, 2 the packs could not be read at all.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import PROJECT_ROOT
from app.models.enums import RuleBasis
from app.rules.evaluator import Evaluator, RuleSyntaxError
from app.rules.functions import FACT_ROOTS, RULE_FUNCTIONS
from app.rules.loader import load_rules
from app.rules.schema import Rule, RulePack

#: One line per basis, printed in the summary so the counts are self-explanatory
#: to somebody reading the output without the source to hand.
_BASIS_BLURB: dict[RuleBasis, str] = {
    RuleBasis.STATUTE: "number is in the Act and quoted in source_ref",
    RuleBasis.RULES_PENDING: "number left to a notification not yet obtained",
    RuleBasis.RECONCILIATION: "compares documents to each other, no external number",
    RuleBasis.ARITHMETIC: "checks one document adds up, no external number",
}

# Reported when a rule's own fixtures never exercise the boundary. A rule for a
# fifty per cent cap whose fixtures test ten per cent and ninety per cent has not
# demonstrated that it is a fifty per cent cap rather than a sixty per cent one.
BOUNDARY_HINT = (
    "fixtures do not test near the threshold, so an off-by-one in the "
    "comparison would not be caught"
)


def _line(char: str = "-", width: int = 78) -> str:
    return char * width


def check(directory: Path, *, strict: bool) -> int:
    # Windows consoles default to cp1252, which cannot encode the rupee sign or
    # Devanagari — both of which appear throughout the packs, in citations and in
    # every Hindi message. Without this the checker dies with a UnicodeEncodeError
    # while printing a rule it has just validated successfully, which looks like a
    # rule pack failure and is not one.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    print(f"reading rule packs from {directory}")
    print(_line())

    loaded = load_rules(directory, run_fixtures_too=True)

    if not loaded.packs:
        print("no rule packs were found", file=sys.stderr)
        return 2

    errors = [issue for issue in loaded.issues if issue.level == "error"]
    warnings = [issue for issue in loaded.issues if issue.level == "warning"]

    # ------------------------------------------------------------ pack summary
    print("PACKS")
    for pack in loaded.packs:
        pending = sum(1 for rule in pack.rules if rule.needs_notified_rules)
        overlay = " (state overlay)" if pack.is_overlay else ""
        print(
            f"  {pack.pack}@{pack.version} [{pack.jurisdiction}]{overlay}: "
            f"{len(pack.rules)} rules, {len(pack.rules) - pending} sound, "
            f"{pending} awaiting a notification"
        )
    print()

    # ---------------------------------------------------------------- by basis
    # Printed as its own block because the distinction is the whole point: a rule
    # with no external number to confirm is not in the same position as one whose
    # number is still unnotified, and one count for both told nobody anything.
    print("BASIS")
    grouped = loaded.by_basis()
    for basis, rules in grouped.items():
        if not rules:
            continue
        print(f"  {basis.value:<16} {len(rules):>3}  {_BASIS_BLURB[basis]}")
    print()

    # -------------------------------------------------------- extra structural
    extra = _structural_checks(loaded.packs)
    for rule_id, message in extra:
        errors.append(_Issue(rule_id, "error", message))

    hints = _boundary_hints(loaded.packs)

    # -------------------------------------------------------------- reporting
    if errors:
        print(f"ERRORS ({len(errors)})")
        for issue in errors:
            print(f"  [{issue.rule_id}] {issue.message}")
        print()

    if warnings:
        print(f"WARNINGS ({len(warnings)})")
        for issue in warnings:
            print(f"  [{issue.rule_id}] {issue.message}")
        print()

    if hints:
        print(f"BOUNDARY COVERAGE ({len(hints)})")
        for rule_id, message in hints:
            print(f"  [{rule_id}] {message}")
        print()

    pending = loaded.rules_pending_notification
    if pending:
        print(f"AWAITING A NOTIFICATION ({len(pending)})")
        print(
            "  The Act creates each of these obligations but leaves the operative"
        )
        print(
            "  number to the appropriate Government. The value used here came from"
        )
        print(
            "  a secondary source. These rules run and are shown to inspectors, but"
        )
        print("  they are weighted lightly and must not be enforced as they stand.")
        print()
        for rule in pending:
            print(f"  {rule.id}")
            print(f"      citation: {rule.citation}")
            print(f"      source:   {rule.source_ref}")
        print()

    # ---------------------------------------------------------------- totals
    print(_line("="))
    fixtures = sum(len(rule.fixtures) for rule in loaded.all_rules)
    print(
        f"{len(loaded.all_rules)} rules across {len(loaded.packs)} packs; "
        f"{fixtures} fixtures executed"
    )
    print(
        f"{len(loaded.all_rules) - len(pending)} sound as they stand, "
        f"{len(pending)} awaiting a notification"
    )
    print(f"{len(errors)} errors, {len(warnings)} warnings, {len(hints)} coverage hints")

    if errors:
        print()
        print("FAILED: the rule packs must not be used until these errors are fixed.")
        return 1

    if strict and (warnings or pending):
        print()
        print(
            "FAILED under --strict: warnings or rules awaiting a notification "
            "present."
        )
        return 1

    print()
    print("PASSED: every rule compiles, is cited, and behaves as its fixtures assert.")
    return 0


class _Issue:
    """Minimal stand-in so extra checks can be printed alongside loader issues."""

    def __init__(self, rule_id: str, level: str, message: str) -> None:
        self.rule_id = rule_id
        self.level = level
        self.message = message


def _structural_checks(packs: list[RulePack]) -> list[tuple[str, str]]:
    """Checks the loader does not perform.

    These are about whether a rule is *usable in practice*, not whether it parses.
    A rule that references a fact nothing ever populates will silently never fire,
    which is worse than a rule that errors: nobody notices an absence.
    """
    problems: list[tuple[str, str]] = []
    evaluator = Evaluator(functions=RULE_FUNCTIONS, fact_roots=FACT_ROOTS)
    seen_ids: dict[str, str] = {}

    for pack in packs:
        for rule in pack.rules:
            # Rule ids must be globally unique across packs, not only within one.
            # Two packs defining the same id would make findings ambiguous about
            # which rule produced them, unless one is a deliberate state overlay.
            if rule.id in seen_ids and not pack.is_overlay:
                problems.append(
                    (
                        rule.id,
                        f"duplicate rule id, already defined in pack "
                        f"{seen_ids[rule.id]!r}",
                    )
                )
            seen_ids[rule.id] = pack.pack

            # A row-level rule must declare the collection it iterates in
            # ``requires``, or it will silently be skipped when that collection is
            # empty rather than reporting a missing document.
            if rule.for_each and rule.for_each not in rule.requires:
                problems.append(
                    (
                        rule.id,
                        f"for_each is {rule.for_each!r} but it is not listed in "
                        "requires, so the rule will not be skipped cleanly when "
                        "that data is absent",
                    )
                )

            # An anomaly with a statutory citation invites somebody to enforce it.
            if rule.is_advisory and rule.severity.value in {"CRITICAL", "HIGH"}:
                problems.append(
                    (
                        rule.id,
                        "an advisory anomaly should not carry CRITICAL or HIGH "
                        "severity: it is never scored and cannot be enforced, so "
                        "high severity misrepresents it",
                    )
                )

            # Every observe/expect expression must compile too. A broken one turns
            # into an error string on a real finding shown to a real employer.
            for label, expression in (
                *((f"observe.{k}", v) for k, v in rule.observe.items()),
                *((f"expect.{k}", v) for k, v in rule.expect.items()),
            ):
                try:
                    evaluator.compile(expression)
                except RuleSyntaxError as exc:
                    problems.append((rule.id, f"{label} does not compile: {exc}"))

            # A missing-document rule that iterates rows is contradictory: if there
            # are rows, the document is present.
            if rule.kind.value == "MISSING_DOCUMENT" and rule.for_each:
                problems.append(
                    (
                        rule.id,
                        "a MISSING_DOCUMENT rule cannot iterate rows: the presence "
                        "of rows means the document is not missing",
                    )
                )

    return problems


def _boundary_hints(packs: list[RulePack]) -> list[tuple[str, str]]:
    """Flag rules whose fixtures never approach the threshold.

    Advisory. A rule can be correct with distant fixtures, but distant fixtures
    cannot demonstrate that the comparison operator is right, and that is the bug
    class that hurts most.
    """
    hints: list[tuple[str, str]] = []

    for pack in packs:
        for rule in pack.rules:
            if len(rule.fixtures) < 2:
                continue
            if not _mentions_threshold(rule):
                continue
            if _fixtures_are_distant(rule):
                hints.append((rule.id, BOUNDARY_HINT))

    return hints


def _mentions_threshold(rule: Rule) -> bool:
    """Whether the rule compares against a literal number."""
    return any(
        operator in rule.expression
        for operator in ("<=", ">=", "<", ">")
    ) and any(char.isdigit() for char in rule.expression)


def _fixtures_are_distant(rule: Rule) -> bool:
    """Crude boundary heuristic.

    Only reports when every numeric fixture value sits far from every literal in
    the expression. Deliberately conservative: this produces a hint, and a hint
    that fires constantly would be ignored.
    """
    literals = _numeric_literals(rule.expression)
    if not literals:
        return False

    values = []
    for fixture in rule.fixtures:
        values.extend(_numeric_values(fixture.facts))
    if not values:
        return False

    for literal in literals:
        if literal == 0:
            continue
        for value in values:
            # Within twenty per cent of a threshold counts as testing near it.
            if abs(value - literal) <= abs(literal) * 0.2:
                return False
    return True


def _numeric_literals(expression: str) -> list[float]:
    import re

    return [
        float(match)
        for match in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", expression)
    ]


def _numeric_values(facts: object) -> list[float]:
    out: list[float] = []

    def walk(node: object) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, int | float):
            out.append(float(node))
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list | tuple):
            for value in node:
                walk(value)

    walk(facts)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app.rules.checker",
        description="Validate rule packs before they are used against real employers",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=PROJECT_ROOT / "rule_packs",
        help="directory containing rule pack YAML files",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "also fail on warnings and unverified thresholds. Use this once the "
            "Central and State Rules have been obtained and every threshold "
            "confirmed."
        ),
    )
    args = parser.parse_args(argv)

    return check(args.dir, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
