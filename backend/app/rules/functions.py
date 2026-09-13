"""Helper functions available inside rule expressions.

This is the whole vocabulary a rule author gets. Every function is total: given
missing or malformed input it returns None or a safe default rather than raising,
because a rule pack must not be able to crash an evaluation run.

The naming aims to make an expression read close to the statute. For example
s.14 of the Code on Wages becomes:

    all_rows(wage_register,
             row.overtime_hours == 0 or
             row.overtime_rate_paise >= 2 * ordinary_hourly_rate(row))
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Any

__all__ = ["FACT_ROOTS", "RULE_FUNCTIONS"]


# --------------------------------------------------------------- null handling
def coalesce(*values: Any) -> Any:
    """First non-None value, or None."""
    for value in values:
        if value is not None:
            return value
    return None


def is_missing(value: Any) -> bool:
    """True for None, empty string, or empty collection.

    Zero is *not* missing. A recorded wage of zero is a very different finding
    from a wage that was never recorded, and conflating them would hide one.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | dict | set | tuple):
        return len(value) == 0
    return False


def is_present(value: Any) -> bool:
    return not is_missing(value)


def default(value: Any, fallback: Any) -> Any:
    return fallback if is_missing(value) else value


# ------------------------------------------------------------------ arithmetic
def _numeric(values: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float) and not math.isnan(float(value)):
            out.append(float(value))
    return out


def total(values: Sequence[Any]) -> float:
    return sum(_numeric(values or []))


def count(values: Sequence[Any] | None) -> int:
    return len(values) if values else 0


def average(values: Sequence[Any]) -> float | None:
    numbers = _numeric(values or [])
    return sum(numbers) / len(numbers) if numbers else None


def minimum(values: Sequence[Any]) -> float | None:
    numbers = _numeric(values or [])
    return min(numbers) if numbers else None


def maximum(values: Sequence[Any]) -> float | None:
    numbers = _numeric(values or [])
    return max(numbers) if numbers else None


def abs_value(value: Any) -> float | None:
    return abs(float(value)) if isinstance(value, int | float) else None


def ratio(numerator: Any, denominator: Any) -> float | None:
    """Safe division. None when either side is missing or the divisor is zero."""
    if not isinstance(numerator, int | float) or not isinstance(denominator, int | float):
        return None
    return numerator / denominator if denominator else None


def percent(numerator: Any, denominator: Any) -> float | None:
    value = ratio(numerator, denominator)
    return value * 100 if value is not None else None


def within_tolerance(actual: Any, expected: Any, tolerance: Any = 100) -> bool:
    """Whether two amounts agree within an absolute tolerance.

    Default 100 paise (one rupee). Registers routinely round to the nearest
    rupee, so an exact-equality arithmetic check would flag almost every
    establishment and drown the real findings.
    """
    if not isinstance(actual, int | float) or not isinstance(expected, int | float):
        return False
    limit = float(tolerance) if isinstance(tolerance, int | float) else 100.0
    return abs(float(actual) - float(expected)) <= limit


# ----------------------------------------------------------------- collections
# Note on design: there are no predicate-taking helpers here. The evaluator has
# no lambdas by design, so a row-level test cannot be expressed as
# ``all_rows(rows, row.x > 0)`` — the inner expression would evaluate eagerly
# with ``row`` unbound. Row-level rules instead declare ``for_each: wage_register``
# and the engine evaluates the expression once per row with ``row`` in scope.
# Everything below therefore operates on plain values and field names.


def pluck(rows: Sequence[Any] | None, field: str) -> list[Any]:
    """Collect one field from every row, skipping rows where it is missing."""
    if not rows:
        return []
    out: list[Any] = []
    for row in rows:
        value = _field(row, field)
        if value is not None:
            out.append(value)
    return out


def count_missing(rows: Sequence[Any] | None, field: str) -> int:
    """How many rows lack a value for ``field``. The missing-field workhorse."""
    if not rows:
        return 0
    return sum(1 for row in rows if is_missing(_field(row, field)))


def count_below(values: Sequence[Any] | None, threshold: Any) -> int:
    if not isinstance(threshold, int | float):
        return 0
    return sum(1 for v in _numeric(values or []) if v < float(threshold))


def count_above(values: Sequence[Any] | None, threshold: Any) -> int:
    if not isinstance(threshold, int | float):
        return 0
    return sum(1 for v in _numeric(values or []) if v > float(threshold))


def count_equal(values: Sequence[Any] | None, target: Any) -> int:
    return sum(1 for v in (values or []) if v == target)


def count_nonzero(values: Sequence[Any] | None) -> int:
    return sum(1 for v in _numeric(values or []) if v != 0)


def all_below(values: Sequence[Any] | None, threshold: Any) -> bool:
    """True when every value is under the threshold.

    An empty set returns True: a rule about wage rows cannot be violated by a
    document with no rows. That case is a MISSING_DOCUMENT finding raised
    elsewhere, and failing here as well would double-count it.
    """
    return count_above(values, threshold) == 0 and count_equal(values, threshold) == 0


def all_at_least(values: Sequence[Any] | None, threshold: Any) -> bool:
    return count_below(values, threshold) == 0


def unique_count(rows: Sequence[Any] | None, field: str) -> int:
    """Distinct non-null values of a field. Used for headcount reconciliation."""
    return len(unique(pluck(rows, field)))


def unique(values: Sequence[Any] | None) -> list[Any]:
    if not values:
        return []
    seen: set[Any] = set()
    out: list[Any] = []
    for value in values:
        try:
            if value in seen:
                continue
            seen.add(value)
        except TypeError:
            pass  # unhashable, keep it
        out.append(value)
    return out


def difference(left: Sequence[Any] | None, right: Sequence[Any] | None) -> list[Any]:
    """Items in ``left`` that are absent from ``right``.

    The workhorse of coverage checks: workers in the employee register that do
    not appear in the EPF filing.
    """
    right_set = set(right or [])
    return [value for value in (left or []) if value not in right_set]


# ------------------------------------------------------------------ money/wages
def paise_to_rupees(paise: Any) -> float | None:
    return float(paise) / 100 if isinstance(paise, int | float) else None


def rupees_to_paise(rupees: Any) -> int | None:
    return int(round(float(rupees) * 100)) if isinstance(rupees, int | float) else None


def _field(row: Any, name: str) -> Any:
    if row is None:
        return None
    return row.get(name) if isinstance(row, dict) else getattr(row, name, None)


def statutory_wages(row: Any) -> int | None:
    """Basic plus DA — the "wages" base for contributions and overtime."""
    basic = _field(row, "basic_paise")
    da = _field(row, "da_paise")
    if basic is None and da is None:
        return None
    return int(basic or 0) + int(da or 0)


def total_remuneration(row: Any) -> int | None:
    """Everything paid, the denominator in the excluded-components 50% test."""
    parts = [
        _field(row, "basic_paise"),
        _field(row, "da_paise"),
        _field(row, "other_allowances_paise"),
    ]
    if all(part is None for part in parts):
        return _field(row, "gross_paise")
    return sum(int(part or 0) for part in parts)


def excluded_share(row: Any) -> float | None:
    """Excluded allowances as a fraction of total remuneration.

    Code on Wages s.2(y): where excluded components exceed one half of total
    remuneration, the excess counts as wages. A ratio above 0.5 is the signal.
    """
    return ratio(_field(row, "other_allowances_paise"), total_remuneration(row))


def ordinary_hourly_rate(row: Any) -> float | None:
    """Hourly rate that overtime is measured against under s.14."""
    wages = statutory_wages(row)
    days = _field(row, "days_paid")
    hours_per_day = _field(row, "normal_hours_per_day") or 8
    if not wages or not days or not hours_per_day:
        return None
    hours = float(days) * float(hours_per_day)
    return wages / hours if hours > 0 else None


def daily_wage(row: Any) -> float | None:
    """Per-day wage, for comparison against a notified minimum daily rate."""
    return ratio(statutory_wages(row), _field(row, "days_paid"))


def deduction_share(row: Any) -> float | None:
    """Deductions as a fraction of wages. s.18(3) caps this at one half."""
    return ratio(_field(row, "deductions_paise"), total_remuneration(row))


# ------------------------------------------------------------------- dates
def days_between(earlier: Any, later: Any) -> int | None:
    if not isinstance(earlier, date) or not isinstance(later, date):
        return None
    return (later - earlier).days


def is_after(value: Any, limit: Any) -> bool:
    return isinstance(value, date) and isinstance(limit, date) and value > limit


def is_before(value: Any, limit: Any) -> bool:
    return isinstance(value, date) and isinstance(limit, date) and value < limit


def day_of_month(value: Any) -> int | None:
    return value.day if isinstance(value, date) else None


def add_days(value: Any, days: Any) -> date | None:
    if not isinstance(value, date) or not isinstance(days, int | float):
        return None
    return value + timedelta(days=int(days))


def is_expired(valid_to: Any, on: Any) -> bool:
    """Whether a licence or registration had lapsed on a given date.

    A null ``valid_to`` means open-ended, which is legitimate for several
    registrations. Treating null as expired would flag every establishment
    holding a perpetual registration.
    """
    if valid_to is None:
        return False
    return is_after(on, valid_to)


def month_end_day(value: Any) -> int | None:
    """Number of days in the month of ``value``. Used for wage-period tests."""
    if not isinstance(value, date):
        return None
    if value.month == 12:
        return 31
    return (date(value.year, value.month + 1, 1) - timedelta(days=1)).day


# ------------------------------------------------------------------- text
def text_contains(haystack: Any, needle: Any) -> bool:
    if not isinstance(haystack, str) or not isinstance(needle, str):
        return False
    return needle.lower() in haystack.lower()


def matches_any(value: Any, options: Sequence[Any] | None) -> bool:
    if value is None or not options:
        return False
    lowered = str(value).strip().lower()
    return any(lowered == str(option).strip().lower() for option in options)


def normalise_number(value: Any) -> str | None:
    """Strip spaces and separators from an identifier before checking format."""
    if value is None:
        return None
    return "".join(ch for ch in str(value) if ch.isalnum()).upper()


def has_length(value: Any, length: Any) -> bool:
    cleaned = normalise_number(value)
    return cleaned is not None and len(cleaned) == int(length)


def is_all_digits(value: Any) -> bool:
    cleaned = normalise_number(value)
    return bool(cleaned) and cleaned.isdigit()


# ------------------------------------------------------------------- internals
def _truthy(value: Any) -> bool:
    return bool(value) if value is not None else False


# The complete allow-list handed to the evaluator.
RULE_FUNCTIONS: dict[str, Callable[..., Any]] = {
    # null handling
    "coalesce": coalesce,
    "is_missing": is_missing,
    "is_present": is_present,
    "default": default,
    # arithmetic
    "total": total,
    "count": count,
    "average": average,
    "minimum": minimum,
    "maximum": maximum,
    "abs_value": abs_value,
    "ratio": ratio,
    "percent": percent,
    "within_tolerance": within_tolerance,
    # collections
    "pluck": pluck,
    "count_missing": count_missing,
    "count_below": count_below,
    "count_above": count_above,
    "count_equal": count_equal,
    "count_nonzero": count_nonzero,
    "all_below": all_below,
    "all_at_least": all_at_least,
    "unique": unique,
    "unique_count": unique_count,
    "difference": difference,
    # money and wages
    "paise_to_rupees": paise_to_rupees,
    "rupees_to_paise": rupees_to_paise,
    "statutory_wages": statutory_wages,
    "total_remuneration": total_remuneration,
    "excluded_share": excluded_share,
    "ordinary_hourly_rate": ordinary_hourly_rate,
    "daily_wage": daily_wage,
    "deduction_share": deduction_share,
    # dates
    "days_between": days_between,
    "is_after": is_after,
    "is_before": is_before,
    "day_of_month": day_of_month,
    "add_days": add_days,
    "is_expired": is_expired,
    "month_end_day": month_end_day,
    # text and identifiers
    "text_contains": text_contains,
    "matches_any": matches_any,
    "normalise_number": normalise_number,
    "has_length": has_length,
    "is_all_digits": is_all_digits,
    # builtins that are safe and genuinely needed
    "len": lambda v: len(v) if v is not None else 0,
    "min": lambda *a: minimum(list(a)),
    "max": lambda *a: maximum(list(a)),
    "round": lambda v, n=0: round(v, int(n)) if isinstance(v, int | float) else None,
    "int": lambda v: int(v) if isinstance(v, int | float | str) and str(v).strip() else None,
    "float": lambda v: float(v) if isinstance(v, int | float) else None,
    "str": lambda v: str(v) if v is not None else None,
    "bool": _truthy,
}

# Fact namespaces a rule may traverse with attribute access.
FACT_ROOTS: tuple[str, ...] = (
    "estab",
    "period",
    "row",
    "wage_register",
    "employee_register",
    "attendance",
    "epf",
    "esic",
    "annual_return",
    "contractors",
    "registrations",
    "incidents",
    "prose",
    "wage_floor",
    "docs",
    "counts",
)
