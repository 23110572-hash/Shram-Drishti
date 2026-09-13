"""Statistical anomaly detection over extracted figures.

These are the checks that need arithmetic over a whole population rather than
judgement about a document, which is why they are here and not in the analyst
pass: Benford's law over a digit distribution and a robust z-score over a wage
column are exact computations, and asking a model to eyeball them would be worse
at it, not better.

Everything produced here is advisory and never affects a compliance score. That
is a hard constraint, not a caution. A statistical outlier is not a breach of
law: an establishment paying unusual wages may be generous, may be in an unusual
trade, or may have one highly paid supervisor. Presenting that as
non-compliance would be indefensible the moment an employer asked which section
they had broken.

What these are genuinely good for is telling an inspector where to look, and
catching fabricated records. Numbers people invent do not have the digit
distribution of numbers that arise from real rates and real day counts.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.models.enums import FindingKind, LabourCode, Severity

logger = logging.getLogger(__name__)

# Benford's law is meaningless on a small sample. Below this the digit
# distribution of perfectly genuine data looks wrong purely by chance.
MIN_SAMPLE_FOR_BENFORD = 60

# Minimum rows before a distribution check is worth running at all.
MIN_SAMPLE_FOR_DISTRIBUTION = 8

# Modified z-score threshold. 3.5 is the conventional cut-off for this statistic;
# it uses the median and MAD rather than mean and standard deviation, so a few
# extreme values do not mask themselves by inflating the spread they are measured
# against.
Z_THRESHOLD = 3.5

# Chi-square critical value for 8 degrees of freedom at p = 0.01. Deliberately
# strict: a loose threshold on a first-digit test produces a steady drip of false
# alarms and inspectors learn to ignore the signal entirely.
BENFORD_CHI2_CRITICAL = 20.09

# Share of identical values in a column that stops looking like coincidence.
DUPLICATE_SHARE_THRESHOLD = 0.35

#: Expected first-digit frequencies under Benford's law.
BENFORD_EXPECTED = {
    digit: math.log10(1 + 1 / digit) for digit in range(1, 10)
}


@dataclass
class Anomaly:
    """One advisory signal. Never a legal conclusion."""

    key: str
    title: str
    detail: str
    severity: Severity = Severity.LOW
    code: LabourCode | None = None
    statistic: dict[str, Any] = field(default_factory=dict)
    affected_rows: list[int] = field(default_factory=list)
    suggested_check: str | None = None

    #: Fixed, and not a parameter. An anomaly that could be emitted as any other
    #: kind would eventually be scored by accident.
    kind: FindingKind = FindingKind.ANOMALY


def detect(
    *,
    wage_rows: list[dict],
    attendance_rows: list[dict],
    epf_rows: list[dict],
    peer_medians: dict[str, float] | None = None,
) -> list[Anomaly]:
    """Run every applicable check over one establishment's period."""
    anomalies: list[Anomaly] = []

    anomalies.extend(_benford(wage_rows, "gross_paise", "gross wages"))
    anomalies.extend(_benford(wage_rows, "net_paid_paise", "net wages paid"))

    anomalies.extend(_outliers(wage_rows, "daily_wage_paise", "daily wage", money=True))
    anomalies.extend(
        _outliers(wage_rows, "deduction_share", "deduction share", money=False)
    )
    anomalies.extend(
        _outliers(attendance_rows, "overtime_hours", "overtime hours", money=False)
    )

    anomalies.extend(_duplicates(wage_rows, "gross_paise", "gross wages"))
    anomalies.extend(_duplicates(wage_rows, "net_paid_paise", "net wages paid"))
    anomalies.extend(
        _duplicates(attendance_rows, "days_present", "days present", min_distinct=2)
    )

    anomalies.extend(_round_numbers(wage_rows, "gross_paise", "gross wages"))
    anomalies.extend(_zero_variance(attendance_rows))
    anomalies.extend(_contribution_ratio(epf_rows))

    if peer_medians:
        anomalies.extend(_peer_comparison(wage_rows, peer_medians))

    return anomalies


# --------------------------------------------------------------------- Benford
def _benford(rows: list[dict], field_name: str, label: str) -> list[Anomaly]:
    """First-digit distribution test.

    Genuine wage figures arise from rates multiplied by day counts and inherit a
    Benford-like distribution. Figures somebody made up do not: invented numbers
    cluster on 2, 3 and 5 and avoid 1. This is the only check here that can catch
    a register that is internally consistent because it was fabricated as a whole.
    """
    values = [
        abs(int(row[field_name]))
        for row in rows
        if isinstance(row.get(field_name), int | float) and row[field_name]
    ]
    if len(values) < MIN_SAMPLE_FOR_BENFORD:
        return []

    digits = Counter(int(str(value)[0]) for value in values if str(value)[0].isdigit())
    total = sum(digits.values())
    if total < MIN_SAMPLE_FOR_BENFORD:
        return []

    chi2 = 0.0
    observed_share: dict[int, float] = {}
    for digit in range(1, 10):
        expected_count = BENFORD_EXPECTED[digit] * total
        observed_count = digits.get(digit, 0)
        observed_share[digit] = round(observed_count / total, 4)
        if expected_count > 0:
            chi2 += (observed_count - expected_count) ** 2 / expected_count

    if chi2 <= BENFORD_CHI2_CRITICAL:
        return []

    return [
        Anomaly(
            key=f"benford.{field_name}",
            title=f"Digit distribution of {label} is unusual",
            detail=(
                f"The leading digits of {total} {label} figures depart from the "
                f"distribution expected of figures that arise from real rates and "
                f"day counts (chi-square {chi2:.1f} against a critical value of "
                f"{BENFORD_CHI2_CRITICAL}). This can happen legitimately when a "
                "single rate is paid across the workforce, so it is a prompt to "
                "look, not a conclusion."
            ),
            severity=Severity.MEDIUM,
            statistic={
                "chi_square": round(chi2, 2),
                "critical_value": BENFORD_CHI2_CRITICAL,
                "sample_size": total,
                "observed_first_digit_share": observed_share,
                "expected_first_digit_share": {
                    d: round(v, 4) for d, v in BENFORD_EXPECTED.items()
                },
            },
            suggested_check=(
                "Compare a sample of register rows against the underlying "
                "attendance and rate records to confirm the figures were computed "
                "rather than entered."
            ),
        )
    ]


# -------------------------------------------------------------------- outliers
def _outliers(
    rows: list[dict], field_name: str, label: str, *, money: bool
) -> list[Anomaly]:
    """Modified z-score outlier detection.

    Median and median absolute deviation rather than mean and standard deviation:
    with a conventional z-score, three fabricated values inflate the standard
    deviation enough to hide themselves. The robust statistic does not have that
    weakness.
    """
    indexed = [
        (index, float(row[field_name]))
        for index, row in enumerate(rows)
        if isinstance(row.get(field_name), int | float)
    ]
    if len(indexed) < MIN_SAMPLE_FOR_DISTRIBUTION:
        return []

    values = np.array([value for _index, value in indexed], dtype=float)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))

    if mad == 0:
        # Every value identical. Handled by the duplicate check, which says
        # something more useful about it than "no variance to measure".
        return []

    # 0.6745 is the constant that makes the MAD a consistent estimator of the
    # standard deviation for normally distributed data.
    scores = 0.6745 * (values - median) / mad
    flagged = [
        (indexed[i][0], values[i], float(scores[i]))
        for i in range(len(values))
        if abs(scores[i]) >= Z_THRESHOLD
    ]
    if not flagged:
        return []

    def render(value: float) -> str:
        return f"₹{value / 100:,.2f}" if money else f"{value:,.2f}"

    worst = max(flagged, key=lambda item: abs(item[2]))

    return [
        Anomaly(
            key=f"outlier.{field_name}",
            title=f"Unusual {label} values in {len(flagged)} row(s)",
            detail=(
                f"Across {len(indexed)} rows the median {label} is "
                f"{render(median)}. {len(flagged)} row(s) sit far outside the "
                f"normal spread, the furthest at {render(worst[1])}. Legitimate "
                "explanations include a supervisor grade, a part-month joiner or "
                "a settlement payment."
            ),
            severity=Severity.LOW,
            statistic={
                "median": round(median, 2),
                "median_absolute_deviation": round(mad, 2),
                "threshold_z": Z_THRESHOLD,
                "sample_size": len(indexed),
                "outliers": [
                    {"row": index, "value": round(value, 2), "z": round(score, 2)}
                    for index, value, score in flagged[:12]
                ],
            },
            affected_rows=[index for index, _v, _z in flagged],
            suggested_check=(
                f"Ask for the basis of the {label} in the flagged rows and confirm "
                "it against the appointment letter or rate notification."
            ),
        )
    ]


# ------------------------------------------------------------------ duplicates
def _duplicates(
    rows: list[dict], field_name: str, label: str, *, min_distinct: int = 3
) -> list[Anomaly]:
    """Too many identical values in a column.

    Real payrolls repeat: several workers on the same grade earn the same. What is
    not real is a large share of a workforce sharing one gross figure while their
    day counts differ, because a gross that does not move with days worked cannot
    have been computed from a daily rate.
    """
    values = [
        row[field_name]
        for row in rows
        if isinstance(row.get(field_name), int | float) and row[field_name]
    ]
    if len(values) < MIN_SAMPLE_FOR_DISTRIBUTION:
        return []

    counts = Counter(values)
    if len(counts) < min_distinct:
        pass  # a near-uniform column is exactly what we are looking for

    value, occurrences = counts.most_common(1)[0]
    share = occurrences / len(values)
    if share < DUPLICATE_SHARE_THRESHOLD or occurrences < 4:
        return []

    # Only interesting when the driver of the amount varies. Identical pay for
    # identical days is unremarkable.
    varying_days = {
        row.get("days_paid")
        for row in rows
        if row.get(field_name) == value and row.get("days_paid") is not None
    }
    if len(varying_days) <= 1:
        return []

    return [
        Anomaly(
            key=f"duplicates.{field_name}",
            title=f"Identical {label} across {occurrences} workers with differing days",
            detail=(
                f"{occurrences} of {len(values)} rows show exactly "
                f"₹{float(value) / 100:,.2f} as {label}, yet those workers are "
                f"recorded with {len(varying_days)} different day counts. An amount "
                "computed from a daily rate cannot stay constant while the days "
                "change."
            ),
            severity=Severity.MEDIUM,
            statistic={
                "repeated_value": value,
                "occurrences": occurrences,
                "sample_size": len(values),
                "share": round(share, 3),
                "distinct_day_counts": len(varying_days),
            },
            affected_rows=[
                index
                for index, row in enumerate(rows)
                if row.get(field_name) == value
            ],
            suggested_check=(
                "Ask how the amount was computed for these workers and reconcile "
                "against the attendance record."
            ),
        )
    ]


def _round_numbers(rows: list[dict], field_name: str, label: str) -> list[Anomaly]:
    """An implausible share of suspiciously round amounts.

    Wages computed from a daily rate over 24, 26 or 30 days land on round hundreds
    only by coincidence. A register where most do has probably been written rather
    than calculated.
    """
    values = [
        int(row[field_name])
        for row in rows
        if isinstance(row.get(field_name), int | float) and row[field_name]
    ]
    if len(values) < MIN_SAMPLE_FOR_DISTRIBUTION:
        return []

    # Round to ₹500 or more, i.e. 50000 paise.
    round_count = sum(1 for value in values if value % 50_000 == 0)
    share = round_count / len(values)

    if share < 0.7:
        return []

    return [
        Anomaly(
            key=f"round_numbers.{field_name}",
            title=f"Most {label} figures are round amounts",
            detail=(
                f"{round_count} of {len(values)} {label} figures are exact "
                f"multiples of ₹500. Amounts derived from a daily rate and a day "
                "count rarely land on round figures, so this pattern suggests the "
                "register was written to a target rather than computed."
            ),
            severity=Severity.LOW,
            statistic={
                "round_count": round_count,
                "sample_size": len(values),
                "share": round(share, 3),
            },
            suggested_check=(
                "Recompute a sample of rows from the stated rate and attendance "
                "and compare against the register."
            ),
        )
    ]


def _zero_variance(rows: list[dict]) -> list[Anomaly]:
    """Attendance that never varies across a workforce.

    Every worker present the same number of days, with no absence anywhere, is a
    roster nobody achieves over a month. It is the signature of a muster roll
    filled in afterwards.
    """
    present = [
        float(row["days_present"])
        for row in rows
        if isinstance(row.get("days_present"), int | float)
    ]
    if len(present) < 10:
        return []

    if len(set(present)) > 1:
        return []

    absences = [
        float(row.get("days_absent") or 0)
        for row in rows
        if row.get("days_absent") is not None
    ]
    if absences and any(value > 0 for value in absences):
        return []

    return [
        Anomaly(
            key="attendance.zero_variance",
            title="Every worker shows identical attendance with no absence",
            detail=(
                f"All {len(present)} workers are recorded as present for exactly "
                f"{present[0]:.0f} days with no absence anywhere in the period. "
                "Real attendance varies across a workforce over a month."
            ),
            severity=Severity.MEDIUM,
            code=LabourCode.OSH,
            statistic={"workers": len(present), "days_present": present[0]},
            suggested_check=(
                "Compare the muster roll against gate or biometric records for "
                "the same period."
            ),
        )
    ]


def _contribution_ratio(rows: list[dict]) -> list[Anomaly]:
    """EPF wage bases clustered exactly on a single value.

    Contributions capped at an identical base across many workers whose register
    wages differ is the classic shape of wage-base suppression. The compliance
    finding for that is raised by a rule with a citation; this only says the
    pattern is present.
    """
    pairs = [
        (float(row["wage_base_paise"]), float(row["register_wages_paise"]))
        for row in rows
        if isinstance(row.get("wage_base_paise"), int | float)
        and isinstance(row.get("register_wages_paise"), int | float)
        and row["register_wages_paise"]
    ]
    if len(pairs) < MIN_SAMPLE_FOR_DISTRIBUTION:
        return []

    bases = Counter(base for base, _wages in pairs)
    base_value, occurrences = bases.most_common(1)[0]
    if occurrences / len(pairs) < 0.6:
        return []

    register_values = {wages for base, wages in pairs if base == base_value}
    if len(register_values) <= 1:
        return []

    return [
        Anomaly(
            key="epf.uniform_wage_base",
            title="Provident fund wage base identical across workers on different wages",
            detail=(
                f"{occurrences} of {len(pairs)} contribution lines declare a wage "
                f"base of exactly ₹{base_value / 100:,.2f}, while the wage "
                f"register shows {len(register_values)} different wage figures for "
                "those same workers."
            ),
            severity=Severity.HIGH,
            code=LabourCode.SOCIAL_SECURITY,
            statistic={
                "repeated_base_paise": base_value,
                "occurrences": occurrences,
                "sample_size": len(pairs),
                "distinct_register_wages": len(register_values),
            },
            suggested_check=(
                "Confirm whether the statutory wage ceiling was applied correctly "
                "and whether basic plus dearness allowance was used as the base."
            ),
        )
    ]


def _peer_comparison(
    rows: list[dict], peer_medians: dict[str, float]
) -> list[Anomaly]:
    """Compare against sector and state peers.

    Deliberately one-directional: only wages materially *below* the peer median
    are flagged. Paying above the market is not a compliance concern, and flagging
    it would waste an inspector's time and look absurd in a report.
    """
    peer_daily = peer_medians.get("daily_wage_paise")
    if not peer_daily:
        return []

    values = [
        float(row["daily_wage_paise"])
        for row in rows
        if isinstance(row.get("daily_wage_paise"), int | float)
    ]
    if len(values) < MIN_SAMPLE_FOR_DISTRIBUTION:
        return []

    median = float(np.median(np.array(values, dtype=float)))
    if median >= peer_daily * 0.7:
        return []

    return [
        Anomaly(
            key="peer.daily_wage_below_median",
            title="Daily wages well below comparable establishments",
            detail=(
                f"The median daily wage here is ₹{median / 100:,.2f}, against "
                f"₹{peer_daily / 100:,.2f} across comparable establishments in the "
                "same sector and state. This is not itself a breach — the "
                "statutory test is the notified minimum wage, which is checked "
                "separately — but the gap is large."
            ),
            severity=Severity.LOW,
            code=LabourCode.WAGES,
            statistic={
                "establishment_median_paise": round(median, 2),
                "peer_median_paise": round(peer_daily, 2),
                "ratio": round(median / peer_daily, 3),
                "sample_size": len(values),
            },
            suggested_check=(
                "Verify the skill classification of these workers and the "
                "notified minimum wage for the trade."
            ),
        )
    ]
