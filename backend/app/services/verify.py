"""Safety checks applied to everything a model returns.

A language model reading a scanned wage register will occasionally produce a
figure that is not on the page. It is not lying; it is completing a pattern. The
number looks entirely plausible, sits in a sensible column, and is wrong. Nothing
downstream can detect that, because by then it is just a row in a table.

So three checks run before any extracted value is trusted, in order of how much
they catch:

1. **Token tracing.** Every value must be locatable among the OCR tokens for the
   page it was claimed from. A value that cannot be traced is either invented or
   an unreported correction, and either way it is held for review rather than
   used. The trace also yields the bounding box, which is why this is not merely
   a check: it is how evidence coordinates are obtained at all.

2. **Arithmetic identities.** Gross must equal its components; net must equal
   gross less deductions. These hold in every real register, so a break means
   either the register is wrong (a genuine finding) or the reading is wrong (a
   review flag). Distinguishing the two needs the trace result from step 1.

3. **Format checks.** A UAN is twelve digits. A PAN is five letters, four digits,
   a letter. These catch transcription slips that arithmetic cannot see.

All three are deterministic and testable, and none of them asks the model whether
it was right.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

# One rupee. Registers routinely round to whole rupees, so demanding exact
# equality on arithmetic identities would flag nearly every establishment and
# bury the real findings under noise.
MONEY_TOLERANCE_PAISE = 100

# How many neighbouring OCR tokens may be joined when looking for a value. A
# figure like "15,250.50" is frequently split across three tokens by OCR, but
# allowing an unbounded window would let any digit sequence be assembled from
# unrelated parts of the page, which would defeat the whole check.
MAX_TOKEN_JOIN = 4


class Agreement(StrEnum):
    """How a value's two sources compare.

    Recorded on every extracted field, because a value the model corrected
    against OCR must be visibly different from one both sources agreed on.
    """

    AGREED = "agreed"
    """Found in the OCR tokens for the claimed page."""

    CORRECTED = "corrected"
    """Not in OCR, but the model declared the correction and gave a reason."""

    OCR_ONLY = "ocr_only"
    """Mode A: read from the PDF text layer, no model involved."""

    MODEL_ONLY = "model_only"
    """Mode C: no OCR was available, so there is nothing to check against."""

    UNSUPPORTED = "unsupported"
    """Not in OCR and not declared as a correction. Held for human review."""


@dataclass(frozen=True)
class Trace:
    """Where a value was found on the page, if it was found."""

    agreement: Agreement
    bbox: list[float] | None = None
    page: int | None = None
    matched_text: str | None = None
    note: str | None = None

    @property
    def is_trustworthy(self) -> bool:
        return self.agreement in {
            Agreement.AGREED,
            Agreement.CORRECTED,
            Agreement.OCR_ONLY,
        }


@dataclass
class CheckResult:
    """Outcome of validating one extracted record."""

    review_reasons: list[str] = field(default_factory=list)
    unsupported_fields: list[str] = field(default_factory=list)
    corrected_fields: list[str] = field(default_factory=list)
    arithmetic_breaks: list[str] = field(default_factory=list)
    format_breaks: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)

    def merge(self, other: CheckResult) -> None:
        self.review_reasons.extend(other.review_reasons)
        self.unsupported_fields.extend(other.unsupported_fields)
        self.corrected_fields.extend(other.corrected_fields)
        self.arithmetic_breaks.extend(other.arithmetic_breaks)
        self.format_breaks.extend(other.format_breaks)


# --------------------------------------------------------------------- parsing
_MONEY_CLEAN = re.compile(r"[^\d.\-]")
_DIGITS = re.compile(r"\d")


def parse_money_to_paise(value: Any) -> int | None:
    """Parse a rupee amount into integer paise.

    ``Decimal`` throughout: these figures decide whether a worker was underpaid,
    and binary floating point cannot represent ``0.1`` exactly. Returns None for
    anything unparseable rather than raising, because a malformed cell is a
    missing value, not a crash.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value * 100

    text = str(value).strip()
    if not text or not _DIGITS.search(text):
        return None

    # Accounting-style negatives, e.g. "(1,250.00)".
    negative = text.startswith("(") and text.endswith(")")
    cleaned = _MONEY_CLEAN.sub("", text)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None

    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None

    paise = int((amount * 100).to_integral_value(rounding="ROUND_HALF_UP"))
    return -paise if negative and paise > 0 else paise


def digits_only(value: Any) -> str:
    """Every digit in a value, in order. The basis of numeric token matching."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _token_numeric(text: str) -> Decimal | None:
    cleaned = _MONEY_CLEAN.sub("", text or "")
    if not cleaned or not _DIGITS.search(cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _normalise_text(value: str) -> str:
    """Casefold and strip punctuation, for comparing names and codes."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


# ------------------------------------------------------------- 1. token tracing
def _bbox_of(tokens: list[dict]) -> list[float]:
    """Union of several token boxes, so a split figure gets one enclosing box."""
    left = min(float(t.get("left", 0.0)) for t in tokens)
    top = min(float(t.get("top", 0.0)) for t in tokens)
    right = max(float(t.get("left", 0.0)) + float(t.get("width", 0.0)) for t in tokens)
    bottom = max(float(t.get("top", 0.0)) + float(t.get("height", 0.0)) for t in tokens)
    return [
        round(left, 5),
        round(top, 5),
        round(max(0.0, right - left), 5),
        round(max(0.0, bottom - top), 5),
    ]


def trace_number(
    value: Any,
    tokens: list[dict],
    *,
    page: int | None = None,
) -> Trace:
    """Locate a numeric value among a page's OCR tokens.

    Matching is numeric, not textual: the register may print ``15,250`` where the
    model returned ``15250.00``, and those are the same number. Comparing digit
    strings would call that a mismatch and raise a false review flag on a
    correct reading.
    """
    if value is None:
        return Trace(agreement=Agreement.AGREED, page=page, note="no value to trace")

    target = value if isinstance(value, Decimal) else _token_numeric(str(value))
    if target is None:
        return Trace(
            agreement=Agreement.UNSUPPORTED, page=page, note="value is not numeric"
        )

    if not tokens:
        return Trace(agreement=Agreement.MODEL_ONLY, page=page, note="no OCR tokens")

    # Single token, exact numeric equality.
    for token in tokens:
        parsed = _token_numeric(str(token.get("text", "")))
        if parsed is not None and parsed == target:
            return Trace(
                agreement=Agreement.AGREED,
                bbox=_bbox_of([token]),
                page=page,
                matched_text=str(token.get("text", "")),
            )

    # Adjacent tokens on the same line, joined. OCR splits "15,250.50" into
    # "15,250" and ".50" often enough that skipping this produces constant false
    # "unsupported" flags on clean documents.
    by_line: dict[int, list[dict]] = {}
    for token in tokens:
        by_line.setdefault(int(token.get("line", 0)), []).append(token)

    target_digits = digits_only(target)
    for line_tokens in by_line.values():
        for start in range(len(line_tokens)):
            for span in range(2, MAX_TOKEN_JOIN + 1):
                window = line_tokens[start : start + span]
                if len(window) < span:
                    break
                joined = "".join(str(t.get("text", "")) for t in window)
                parsed = _token_numeric(joined)
                if parsed is not None and parsed == target:
                    return Trace(
                        agreement=Agreement.AGREED,
                        bbox=_bbox_of(window),
                        page=page,
                        matched_text=joined,
                    )
                # Digit-sequence fallback: catches a decimal point OCR dropped.
                if target_digits and digits_only(joined) == target_digits:
                    return Trace(
                        agreement=Agreement.AGREED,
                        bbox=_bbox_of(window),
                        page=page,
                        matched_text=joined,
                        note="matched on digit sequence, decimal separator differed",
                    )

    return Trace(
        agreement=Agreement.UNSUPPORTED,
        page=page,
        note=f"no OCR token on page {page} carries the value {value!r}",
    )


def trace_text(value: Any, tokens: list[dict], *, page: int | None = None) -> Trace:
    """Locate a textual value, such as a worker name, among OCR tokens.

    Names are traced loosely on purpose: OCR mangles Indian names, and requiring
    an exact match would flag most rows on a real scan. A partial match is enough
    to establish that the row exists where the model claims and to give a
    bounding box; the name itself is verified by identity resolution, not here.
    """
    if value is None or not str(value).strip():
        return Trace(agreement=Agreement.AGREED, page=page, note="no value to trace")

    if not tokens:
        return Trace(agreement=Agreement.MODEL_ONLY, page=page, note="no OCR tokens")

    wanted = _normalise_text(value)
    if not wanted:
        return Trace(agreement=Agreement.AGREED, page=page)

    by_line: dict[int, list[dict]] = {}
    for token in tokens:
        by_line.setdefault(int(token.get("line", 0)), []).append(token)

    for line_tokens in by_line.values():
        joined = _normalise_text("".join(str(t.get("text", "")) for t in line_tokens))
        if not joined:
            continue
        if wanted in joined or (len(wanted) >= 6 and joined.find(wanted[:6]) >= 0):
            # Narrow the box to the tokens that actually contributed, so the
            # highlight lands on the name rather than the whole row.
            hits = [
                t
                for t in line_tokens
                if _normalise_text(str(t.get("text", "")))
                and _normalise_text(str(t.get("text", ""))) in wanted
            ]
            return Trace(
                agreement=Agreement.AGREED,
                bbox=_bbox_of(hits or line_tokens),
                page=page,
                matched_text=str(value),
            )

    return Trace(
        agreement=Agreement.UNSUPPORTED,
        page=page,
        note=f"no OCR line on page {page} resembles {str(value)[:40]!r}",
    )


def build_correction_index(corrections: list[dict] | None) -> dict[str, dict]:
    """Index declared corrections by their corrected value.

    A value absent from OCR is acceptable only when the model said it was
    correcting an OCR error and gave a reason. Anything else absent is treated as
    unsupported. Indexing by digit sequence so ``15250.00`` finds a correction
    declared as ``15,250``.
    """
    index: dict[str, dict] = {}
    for correction in corrections or []:
        corrected = correction.get("corrected_to")
        if corrected is None:
            continue
        key = digits_only(corrected) or _normalise_text(corrected)
        if key:
            index[key] = correction
    return index


def resolve_trace(
    trace: Trace, value: Any, corrections: dict[str, dict]
) -> Trace:
    """Upgrade an unsupported trace to CORRECTED when the model declared it."""
    if trace.agreement is not Agreement.UNSUPPORTED:
        return trace

    key = digits_only(value) or _normalise_text(value)
    correction = corrections.get(key)
    if correction is None:
        return trace

    return Trace(
        agreement=Agreement.CORRECTED,
        bbox=trace.bbox,
        page=trace.page,
        matched_text=str(value),
        note=str(correction.get("reason") or "declared correction, no reason given"),
    )


# --------------------------------------------------- 2. arithmetic identities
@dataclass(frozen=True)
class Identity:
    """One arithmetic relationship that must hold, expressed over paise."""

    name: str
    description: str


WAGE_IDENTITIES = (
    Identity("gross_equals_components", "gross = basic + DA + other allowances"),
    Identity("net_equals_gross_less_deductions", "net = gross - total deductions"),
    Identity("deductions_equal_parts", "total deductions = PF + ESI + advance recovery"),
    Identity("overtime_amount_matches_rate", "overtime amount = hours x rate"),
)


def _within(a: int | None, b: int | None, tolerance: int = MONEY_TOLERANCE_PAISE) -> bool:
    if a is None or b is None:
        return True  # not determinable, so not a break
    return abs(a - b) <= tolerance


def check_wage_arithmetic(row: dict[str, Any]) -> list[str]:
    """Check the internal arithmetic of one wage row.

    Every identity is skipped when an input is missing. A missing value is not
    zero, and treating it as zero here would invent breaks on partially filled
    registers — which is most of them.
    """
    breaks: list[str] = []

    basic = row.get("basic_paise")
    da = row.get("da_paise")
    other = row.get("other_allowances_paise")
    gross = row.get("gross_paise")

    if gross is not None and any(v is not None for v in (basic, da, other)):
        components = sum(v for v in (basic, da, other) if v is not None)
        if not _within(gross, components):
            breaks.append(
                f"gross {gross / 100:.2f} does not equal basic+DA+allowances "
                f"{components / 100:.2f}"
            )

    net = row.get("net_paid_paise")
    deductions = row.get("deductions_paise")
    overtime = row.get("overtime_paise")

    if net is not None and gross is not None:
        # Overtime is paid on top of gross and must be in this identity. Leaving it
        # out flags every worker who did overtime as a misread row — and because an
        # unverified row is excluded from evaluation, that quietly suppressed the
        # real overtime and deduction-cap findings on exactly those rows. A false
        # positive in a verification check is not merely noise: it destroys
        # detections downstream.
        expected = gross + (overtime or 0) - (deductions or 0)
        if not _within(net, expected):
            components = f"gross {gross / 100:.2f}"
            if overtime:
                components += f" plus overtime {overtime / 100:.2f}"
            components += f" less deductions {(deductions or 0) / 100:.2f}"
            breaks.append(
                f"net paid {net / 100:.2f} does not equal {components} "
                f"(= {expected / 100:.2f})"
            )

    parts = [row.get("pf_deduction_paise"), row.get("esi_deduction_paise"), row.get("advance_recovery_paise")]
    if deductions is not None and all(p is not None for p in parts):
        total_parts = sum(p for p in parts if p is not None)
        if not _within(deductions, total_parts):
            breaks.append(
                f"total deductions {deductions / 100:.2f} does not equal "
                f"PF+ESI+advance {total_parts / 100:.2f}"
            )

    hours = row.get("overtime_hours")
    rate = row.get("overtime_rate_paise")
    amount = row.get("overtime_paise")
    if amount is not None and hours and rate:
        expected_ot = int(round(float(hours) * float(rate)))
        # Wider tolerance: overtime is commonly rounded to the rupee per hour.
        if not _within(amount, expected_ot, tolerance=max(MONEY_TOLERANCE_PAISE, int(hours) * 100)):
            breaks.append(
                f"overtime amount {amount / 100:.2f} does not equal "
                f"{hours} hours x {rate / 100:.2f}"
            )

    days_paid = row.get("days_paid")
    if days_paid is not None and float(days_paid) > 31:
        breaks.append(f"days paid {days_paid} exceeds the days in any month")

    return breaks


def check_contribution_arithmetic(row: dict[str, Any]) -> list[str]:
    """Sanity-check one EPF or ESIC line.

    Deliberately not checking the contribution rate here: that is a compliance
    question with a statutory answer, and it belongs in a rule with a citation,
    not buried in an extraction check.
    """
    breaks: list[str] = []

    base = row.get("wage_base_paise")
    employee = row.get("employee_share_paise")

    if base is not None and employee is not None and employee > base:
        breaks.append(
            f"employee contribution {employee / 100:.2f} exceeds the wage base "
            f"{base / 100:.2f}"
        )

    ncp = row.get("ncp_days")
    if ncp is not None and (float(ncp) < 0 or float(ncp) > 31):
        breaks.append(f"non-contributory days {ncp} is outside 0-31")

    return breaks


def check_attendance_arithmetic(row: dict[str, Any]) -> list[str]:
    breaks: list[str] = []

    present = row.get("days_present")
    absent = row.get("days_absent")
    if present is not None and absent is not None and float(present) + float(absent) > 31:
        breaks.append(
            f"days present {present} plus days absent {absent} exceeds 31"
        )

    max_daily = row.get("max_daily_hours")
    if max_daily is not None and float(max_daily) > 24:
        breaks.append(f"maximum daily hours {max_daily} exceeds 24")

    max_weekly = row.get("max_weekly_hours")
    if max_weekly is not None and float(max_weekly) > 168:
        breaks.append(f"maximum weekly hours {max_weekly} exceeds 168")

    longest = row.get("longest_consecutive_days")
    if longest is not None and int(longest) > 31:
        breaks.append(f"longest consecutive run {longest} exceeds the period length")

    return breaks


# ------------------------------------------------------------ 3. format checks
_PAN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")


def check_uan(value: Any) -> str | None:
    """UAN must be exactly twelve digits.

    EPFO publishes no check-digit algorithm for the UAN, so length and character
    class are the whole of what can be validated. Claiming more certainty than
    that would be dishonest.
    """
    if value is None or not str(value).strip():
        return None
    cleaned = digits_only(value)
    if len(cleaned) != 12:
        return f"UAN {str(value)[:20]!r} is not twelve digits"
    return None


def check_pan(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()
    if not _PAN.match(cleaned):
        return f"PAN {str(value)[:20]!r} does not match the AAAAA9999A pattern"
    return None


def check_esic_number(value: Any) -> str | None:
    """ESIC insurance numbers are ten digits; employer codes are seventeen."""
    if value is None or not str(value).strip():
        return None
    cleaned = digits_only(value)
    if len(cleaned) not in {10, 17}:
        return f"ESIC number {str(value)[:24]!r} is neither ten nor seventeen digits"
    return None


def _verhoeff_valid(number: str) -> bool:
    """Verhoeff checksum, which Aadhaar numbers satisfy.

    Used only to decide whether a twelve-digit sequence on a page is genuinely an
    Aadhaar number and therefore needs redaction. A random twelve-digit employee
    code passes Verhoeff one time in ten, so this reduces false redaction flags
    without ever being used to validate identity.
    """
    d = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
        (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
        (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
        (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
        (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
        (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
        (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
        (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
        (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
    )
    p = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
        (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
        (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
        (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
        (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
        (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
        (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
    )
    inv = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)

    if len(number) != 12 or not number.isdigit():
        return False

    check = 0
    for index, digit in enumerate(reversed(number)):
        check = d[check][p[index % 8][int(digit)]]
    return inv[check] == 0


_AADHAAR_CANDIDATE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")


def detect_aadhaar(text: str) -> list[str]:
    """Find likely Aadhaar numbers in page text.

    Returned masked. The point is to know a page carries an Aadhaar number so
    the stored copy can be redacted and access logged — never to keep the number.
    """
    found: list[str] = []
    for match in _AADHAAR_CANDIDATE.finditer(text or ""):
        candidate = digits_only(match.group(0))
        if _verhoeff_valid(candidate):
            found.append(f"XXXXXXXX{candidate[-4:]}")
    return found


def check_identifier_formats(row: dict[str, Any]) -> list[str]:
    """Run every applicable format check over one row."""
    problems = [
        check_uan(row.get("uan")),
        check_pan(row.get("pan")),
        check_esic_number(row.get("esic_number")),
    ]
    return [p for p in problems if p]
