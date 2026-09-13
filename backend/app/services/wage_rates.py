"""Loader for the state-wise minimum wage table.

Parses ``state wise minimum wages.md`` into ``MinimumWageRate`` rows.

The source file is explicit that it is "a general scheduled-employment
reference ... not a substitute for the applicable official notification", and
that monthly figures assume 26 paid working days. Both facts are carried into
the database: every row is marked ``source=REFERENCE`` and stores its
``monthly_working_days``, so any finding computed from these rates can state
its own provenance.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import SkillCategory, WageRateSource
from app.models.establishment import MinimumWageRate

logger = logging.getLogger(__name__)

# The reference table is dated March 2026.
REFERENCE_EFFECTIVE_FROM = date(2026, 3, 1)
REFERENCE_MONTHLY_WORKING_DAYS = 26
REFERENCE_NOTE = (
    "General scheduled-employment reference (LabourCodeCalc, March 2026). "
    "Not a substitute for the applicable official state notification."
)

# Two-letter codes used as the jurisdiction overlay key, e.g. IN/MH.
STATE_CODES: dict[str, str] = {
    "Andhra Pradesh": "AP",
    "Arunachal Pradesh": "AR",
    "Assam": "AS",
    "Bihar": "BR",
    "Chandigarh": "CH",
    "Chhattisgarh": "CG",
    "Delhi": "DL",
    "Goa": "GA",
    "Gujarat": "GJ",
    "Haryana": "HR",
    "Himachal Pradesh": "HP",
    "Jammu & Kashmir": "JK",
    "Jharkhand": "JH",
    "Karnataka": "KA",
    "Kerala": "KL",
    "Madhya Pradesh": "MP",
    "Maharashtra": "MH",
    "Manipur": "MN",
    "Meghalaya": "ML",
    "Mizoram": "MZ",
    "Nagaland": "NL",
    "Odisha": "OD",
    "Puducherry": "PY",
    "Punjab": "PB",
    "Rajasthan": "RJ",
    "Sikkim": "SK",
    "Tamil Nadu": "TN",
    "Telangana": "TG",
    "Tripura": "TR",
    "Uttar Pradesh": "UP",
    "Uttarakhand": "UK",
    "West Bengal": "WB",
}

# Matches "Andhra Pradesh<TAB>₹430/day<TAB>₹474/day<TAB>₹522/day", tolerating
# runs of whitespace instead of tabs and an optional thousands separator.
_ROW = re.compile(
    r"^(?P<state>[A-Za-z&.\s]+?)\s+"
    r"₹\s*(?P<unskilled>[\d,]+)\s*/\s*day\s+"
    r"₹\s*(?P<semi>[\d,]+)\s*/\s*day\s+"
    r"₹\s*(?P<skilled>[\d,]+)\s*/\s*day\s*$"
)


@dataclass(frozen=True)
class ParsedRate:
    state_name: str
    state_code: str
    skill_category: SkillCategory
    daily_rate_paise: int


def _to_paise(rupees: str) -> int:
    return int(rupees.replace(",", "")) * 100


def parse_wage_table(text: str) -> list[ParsedRate]:
    """Extract one ParsedRate per state per skill category.

    Unrecognised lines are skipped rather than raising: the file has a prose
    header and a column-title row that are not data. Unknown state names are
    logged loudly, because a silently dropped state means the wage-floor rule
    quietly stops working for every establishment there.
    """
    rates: list[ParsedRate] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or "₹" not in line:
            continue

        match = _ROW.match(line)
        if match is None:
            continue

        state_name = " ".join(match.group("state").split())
        code = STATE_CODES.get(state_name)
        if code is None:
            logger.warning(
                "minimum wage row for unmapped state skipped",
                extra={"state_name": state_name},
            )
            continue

        for category, group in (
            (SkillCategory.UNSKILLED, "unskilled"),
            (SkillCategory.SEMI_SKILLED, "semi"),
            (SkillCategory.SKILLED, "skilled"),
        ):
            rates.append(
                ParsedRate(
                    state_name=state_name,
                    state_code=code,
                    skill_category=category,
                    daily_rate_paise=_to_paise(match.group(group)),
                )
            )

    return rates


def load_wage_rates(session: Session, source_file: Path) -> int:
    """Load or refresh reference rates. Returns the number of rows written.

    Idempotent: re-running updates existing rows for the same
    (state, category, effective_from) key instead of duplicating them, so the
    loader can be re-run safely after editing the source file.
    """
    if not source_file.exists():
        logger.error("minimum wage source file missing", extra={"path": str(source_file)})
        return 0

    parsed = parse_wage_table(source_file.read_text(encoding="utf-8"))
    if not parsed:
        logger.error("no minimum wage rows parsed", extra={"path": str(source_file)})
        return 0

    written = 0
    for rate in parsed:
        existing = session.execute(
            select(MinimumWageRate).where(
                MinimumWageRate.state_code == rate.state_code,
                MinimumWageRate.skill_category == rate.skill_category,
                MinimumWageRate.effective_from == REFERENCE_EFFECTIVE_FROM,
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                MinimumWageRate(
                    state_code=rate.state_code,
                    state_name=rate.state_name,
                    skill_category=rate.skill_category,
                    daily_rate_paise=rate.daily_rate_paise,
                    monthly_working_days=REFERENCE_MONTHLY_WORKING_DAYS,
                    effective_from=REFERENCE_EFFECTIVE_FROM,
                    source=WageRateSource.REFERENCE,
                    source_note=REFERENCE_NOTE,
                )
            )
        else:
            existing.daily_rate_paise = rate.daily_rate_paise
            existing.state_name = rate.state_name
            existing.source = WageRateSource.REFERENCE
            existing.source_note = REFERENCE_NOTE
        written += 1

    session.flush()
    logger.info(
        "minimum wage rates loaded",
        extra={"rows": written, "states": len({r.state_code for r in parsed})},
    )
    return written


def lookup_rate(
    session: Session,
    *,
    state_code: str,
    skill_category: SkillCategory,
    on: date,
) -> MinimumWageRate | None:
    """Rate in force for a state and category on a given date.

    Picks the latest rate whose effective window contains ``on``. Returns None
    when nothing covers the date — the caller must then skip the wage-floor
    check rather than assume a rate, because a guessed floor produces a false
    finding against a real employer.
    """
    return session.execute(
        select(MinimumWageRate)
        .where(
            MinimumWageRate.state_code == state_code,
            MinimumWageRate.skill_category == skill_category,
            MinimumWageRate.effective_from <= on,
        )
        .order_by(MinimumWageRate.effective_from.desc())
        .limit(1)
    ).scalar_one_or_none()
