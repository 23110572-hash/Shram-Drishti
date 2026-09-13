"""Generator for an evaluation corpus with known ground truth.

The problem this solves: without documents whose correct answers are already
known, there is no way to say whether the system works. Running it over real
employer filings tells you what it found, not what it missed, and a missed
violation is invisible by definition.

So this builds a set of registers, muster rolls and challans for a fictitious
establishment, injects specific labelled violations, and records exactly what
should be found. Running the pipeline over the corpus then gives real numbers:
which violations were detected, which were missed, and which findings were raised
against rows that were compliant.

Three things make the output a fair test rather than a rehearsal.

**The documents are internally consistent.** Gross equals its components, net
equals gross less deductions, and the challan totals add up. A corpus of
arithmetically broken documents would be caught by the arithmetic checks and
would say nothing about the compliance rules.

**Names vary between documents, the way they really do.** The same worker appears
with initials expanded in one filing and contracted in another, with and without a
patronymic. If identity resolution is not actually working, the cross-document
coverage checks will produce a flood of false "concealed worker" findings, and this
corpus is what reveals that.

**Violations are injected individually and labelled.** Each expected finding names
the rule it should trigger and the worker it concerns, so a run produces a per-rule
detection rate rather than a single overall number that hides which rules are broken.

The PDFs carry a real text layer, so a corpus run exercises Mode A and costs
nothing in OCR or model calls. Scanned variants for exercising Modes B and C have
to be produced by printing and photographing these, which is deliberate: a
synthetically degraded image does not have the failure modes of a real phone photo
of a real register, and pretending otherwise would flatter the system.
"""

from __future__ import annotations

import io
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# Fixed so a corpus is reproducible. A run whose documents change between
# invocations cannot be compared against a previous run's detection rate.
DEFAULT_SEED = 20260401

# Plausible unskilled daily rate for the reference table, in paise. Workers are
# generated above this so that only the deliberately injected wage-floor
# violations fall below it.
COMPLIANT_DAILY_PAISE = 65_000

GIVEN_NAMES = [
    "Rajesh", "Sunita", "Mohammed", "Lakshmi", "Anil", "Pooja", "Ramesh",
    "Kavita", "Suresh", "Meena", "Vijay", "Anita", "Prakash", "Rekha",
    "Santosh", "Geeta", "Dinesh", "Sarita", "Manoj", "Shanti", "Arun",
    "Usha", "Rakesh", "Nirmala", "Ashok", "Radha", "Deepak", "Savita",
]

SURNAMES = [
    "Kumar", "Devi", "Sharma", "Yadav", "Patil", "Khan", "Singh", "Prasad",
    "Chaudhary", "Rathod", "Mishra", "Pawar", "Reddy", "Nair", "Das", "Bhosale",
]

FATHER_NAMES = [
    "Ram Lal", "Shyam Singh", "Abdul Rahim", "Govind Rao", "Hari Prasad",
    "Bhola Nath", "Mangal Singh", "Kishan Lal", "Devi Das", "Raghu Nath",
]

DESIGNATIONS = [
    ("Helper", "UNSKILLED"),
    ("Loader", "UNSKILLED"),
    ("Machine Operator", "SEMI_SKILLED"),
    ("Fitter", "SKILLED"),
    ("Electrician", "SKILLED"),
    ("Supervisor", "HIGHLY_SKILLED"),
]


# --------------------------------------------------------------------- model
@dataclass
class Worker:
    """One fictitious worker, with the name variants a real filing produces."""

    serial: int
    given: str
    surname: str
    father: str
    designation: str
    skill: str
    gender: str
    uan: str
    employee_code: str
    date_of_joining: date

    days_paid: int = 26
    days_present: int = 26
    basic_paise: int = 0
    da_paise: int = 0
    other_allowances_paise: int = 0
    overtime_hours: float = 0.0
    overtime_rate_paise: int = 0
    pf_deduction_paise: int = 0
    esi_deduction_paise: int = 0
    advance_recovery_paise: int = 0
    paid_on: date | None = None
    date_of_exit: date | None = None

    max_daily_hours: float = 8.0
    max_weekly_hours: float = 48.0
    longest_consecutive_days: int = 6

    #: Whether this worker is present in the EPF filing. False models concealment.
    in_epf: bool = True
    epf_wage_base_paise: int | None = None

    @property
    def full_name(self) -> str:
        return f"{self.given} {self.surname}"

    @property
    def register_name(self) -> str:
        """As printed in the wage register: full name with patronymic."""
        return f"{self.given} {self.surname} S/O {self.father}"

    @property
    def muster_name(self) -> str:
        """As printed on the muster roll: initial contracted.

        This is the variant that breaks naive matching, and it is extremely
        common on hand-kept rolls where space is tight.
        """
        return f"{self.given[0]}. {self.surname}"

    @property
    def epf_name(self) -> str:
        """As printed in the EPF filing: uppercase, patronymic run together."""
        return f"{self.given} {self.surname} {self.father}".upper().replace(" ", " ")

    @property
    def gross_paise(self) -> int:
        return self.basic_paise + self.da_paise + self.other_allowances_paise

    @property
    def statutory_wages_paise(self) -> int:
        return self.basic_paise + self.da_paise

    @property
    def overtime_paise(self) -> int:
        return int(round(self.overtime_hours * self.overtime_rate_paise))

    @property
    def deductions_paise(self) -> int:
        return (
            self.pf_deduction_paise
            + self.esi_deduction_paise
            + self.advance_recovery_paise
        )

    @property
    def net_paid_paise(self) -> int:
        return self.gross_paise + self.overtime_paise - self.deductions_paise

    @property
    def daily_wage_paise(self) -> int:
        return int(self.statutory_wages_paise / self.days_paid) if self.days_paid else 0

    @property
    def ordinary_hourly_paise(self) -> int:
        hours = self.days_paid * 8
        return int(self.statutory_wages_paise / hours) if hours else 0


@dataclass
class ExpectedFinding:
    """A violation deliberately injected, and the rule that must catch it."""

    rule_id: str
    worker_serial: int | None
    description: str
    severity: str


@dataclass
class Corpus:
    establishment_name: str
    state_code: str
    period_start: date
    period_end: date
    workers: list[Worker] = field(default_factory=list)
    expected: list[ExpectedFinding] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def ground_truth(self) -> dict[str, Any]:
        """Machine-readable answer key, written beside the documents."""
        return {
            "establishment_name": self.establishment_name,
            "state_code": self.state_code,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "worker_count": len(self.workers),
            "workers_in_epf": sum(1 for w in self.workers if w.in_epf),
            "files": self.files,
            "expected_findings": [
                {
                    "rule_id": item.rule_id,
                    "worker_serial": item.worker_serial,
                    "worker_name": (
                        next(
                            (
                                w.full_name
                                for w in self.workers
                                if w.serial == item.worker_serial
                            ),
                            None,
                        )
                        if item.worker_serial
                        else None
                    ),
                    "severity": item.severity,
                    "description": item.description,
                }
                for item in self.expected
            ],
            "expected_rule_ids": sorted({item.rule_id for item in self.expected}),
            "note": (
                "Any finding whose rule id is not in expected_rule_ids is either a "
                "false positive or a genuine consequence of the injected data that "
                "was not anticipated. Both need looking at."
            ),
        }


# ----------------------------------------------------------------- generation
def build_corpus(
    *,
    establishment_name: str = "Sunrise Textile Works (Unit II)",
    state_code: str = "MH",
    worker_count: int = 24,
    period: date | None = None,
    seed: int = DEFAULT_SEED,
    clean: bool = False,
) -> Corpus:
    """Generate one establishment's filings for one wage month.

    ``clean=True`` produces a fully compliant set. That case matters as much as
    the violating one: a system that finds breaches everywhere is useless, and the
    only way to detect that is to run it over records that are actually correct.
    """
    rng = random.Random(seed)

    month_start = period or date(2026, 3, 1)
    month_end = _month_end(month_start)

    corpus = Corpus(
        establishment_name=establishment_name,
        state_code=state_code,
        period_start=month_start,
        period_end=month_end,
    )

    used_uans: set[str] = set()

    for serial in range(1, worker_count + 1):
        designation, skill = DESIGNATIONS[rng.randrange(len(DESIGNATIONS))]

        while True:
            uan = "".join(str(rng.randrange(10)) for _ in range(12))
            if uan not in used_uans:
                used_uans.add(uan)
                break

        # Rate scales with skill, so the corpus has a realistic spread rather than
        # one value repeated — which the duplicate-value anomaly check would flag.
        multiplier = {
            "UNSKILLED": 1.0,
            "SEMI_SKILLED": 1.18,
            "SKILLED": 1.45,
            "HIGHLY_SKILLED": 1.9,
        }[skill]

        daily = int(COMPLIANT_DAILY_PAISE * multiplier * rng.uniform(1.02, 1.16))
        days = rng.choice([26, 26, 26, 25, 24, 23])

        worker = Worker(
            serial=serial,
            given=GIVEN_NAMES[rng.randrange(len(GIVEN_NAMES))],
            surname=SURNAMES[rng.randrange(len(SURNAMES))],
            father=FATHER_NAMES[rng.randrange(len(FATHER_NAMES))],
            designation=designation,
            skill=skill,
            gender="F" if rng.random() < 0.32 else "M",
            uan=uan,
            employee_code=f"EMP{serial:04d}",
            date_of_joining=month_start - timedelta(days=rng.randrange(120, 2400)),
            days_paid=days,
            days_present=days,
            paid_on=month_end + timedelta(days=rng.choice([3, 4, 5, 6])),
        )

        basic = int(daily * days * 0.62)
        worker.basic_paise = _round_to_rupee(basic)
        worker.da_paise = _round_to_rupee(int(daily * days * 0.38))
        # Excluded allowances kept below half of total remuneration, so only the
        # injected case breaches the s.2(y) proviso.
        worker.other_allowances_paise = _round_to_rupee(
            int(worker.statutory_wages_paise * rng.uniform(0.16, 0.34))
        )

        if rng.random() < 0.45:
            worker.overtime_hours = float(rng.choice([4, 6, 8, 10, 12, 16]))
            # Twice the ordinary hourly rate, as s.14 requires.
            worker.overtime_rate_paise = worker.ordinary_hourly_paise * 2

        worker.pf_deduction_paise = _round_to_rupee(
            int(worker.statutory_wages_paise * 0.12)
        )
        if worker.gross_paise <= 2_100_000:
            worker.esi_deduction_paise = _round_to_rupee(
                int(worker.gross_paise * 0.0075)
            )
        if rng.random() < 0.2:
            worker.advance_recovery_paise = _round_to_rupee(
                rng.randrange(50_000, 200_000)
            )

        worker.epf_wage_base_paise = worker.statutory_wages_paise
        worker.max_daily_hours = float(rng.choice([8, 8, 8.5, 9, 9.5]))
        worker.max_weekly_hours = float(rng.choice([44, 46, 48, 48]))
        worker.longest_consecutive_days = rng.choice([5, 6, 6, 6, 7])

        corpus.workers.append(worker)

    if not clean:
        _inject_violations(corpus, rng)

    return corpus


def _inject_violations(corpus: Corpus, rng: random.Random) -> None:
    """Inject one labelled violation per selected worker.

    One violation per worker, so a missed detection points at a single rule rather
    than being masked by another finding on the same row.
    """
    workers = corpus.workers
    if len(workers) < 12:
        raise ValueError("the corpus needs at least 12 workers to inject the full set")

    picks = rng.sample(range(len(workers)), 11)

    # 1. Paid below the minimum daily wage — the headline wage violation.
    worker = workers[picks[0]]
    worker.basic_paise = _round_to_rupee(int(COMPLIANT_DAILY_PAISE * 0.62 * worker.days_paid))
    worker.da_paise = _round_to_rupee(int(COMPLIANT_DAILY_PAISE * 0.14 * worker.days_paid))
    worker.epf_wage_base_paise = worker.statutory_wages_paise
    corpus.expected.append(
        ExpectedFinding(
            "WAGES.FLOOR.STATE_MINIMUM",
            worker.serial,
            f"daily wage reduced to about {worker.daily_wage_paise / 100:.2f}, "
            "below the reference minimum",
            "CRITICAL",
        )
    )

    # 2. Overtime at the single rate rather than twice.
    worker = workers[picks[1]]
    worker.overtime_hours = 12.0
    worker.overtime_rate_paise = worker.ordinary_hourly_paise
    corpus.expected.append(
        ExpectedFinding(
            "WAGES.OVERTIME.RATE",
            worker.serial,
            "overtime paid at the ordinary rate instead of twice it",
            "HIGH",
        )
    )

    # 3. Deductions above the fifty per cent cap.
    worker = workers[picks[2]]
    worker.advance_recovery_paise = _round_to_rupee(
        int(worker.gross_paise * 0.55) - worker.pf_deduction_paise - worker.esi_deduction_paise
    )
    corpus.expected.append(
        ExpectedFinding(
            "WAGES.DEDUCTIONS.HALF_CAP",
            worker.serial,
            "total deductions raised past half of wages via an advance recovery",
            "HIGH",
        )
    )

    # 4. Wages paid after the seventh of the following month.
    worker = workers[picks[3]]
    worker.paid_on = corpus.period_end + timedelta(days=19)
    corpus.expected.append(
        ExpectedFinding(
            "WAGES.PAYMENT.MONTHLY_BY_SEVENTH",
            worker.serial,
            f"paid on {worker.paid_on.isoformat()}, past the seventh",
            "HIGH",
        )
    )

    # 5. Final settlement well beyond two working days of exit.
    worker = workers[picks[4]]
    worker.date_of_exit = corpus.period_start + timedelta(days=9)
    worker.paid_on = worker.date_of_exit + timedelta(days=24)
    worker.days_paid = 9
    worker.days_present = 9
    worker.basic_paise = _round_to_rupee(int(worker.basic_paise * 9 / 26))
    worker.da_paise = _round_to_rupee(int(worker.da_paise * 9 / 26))
    worker.other_allowances_paise = _round_to_rupee(
        int(worker.other_allowances_paise * 9 / 26)
    )
    worker.pf_deduction_paise = _round_to_rupee(int(worker.statutory_wages_paise * 0.12))
    worker.esi_deduction_paise = 0
    worker.advance_recovery_paise = 0
    worker.epf_wage_base_paise = worker.statutory_wages_paise
    corpus.expected.append(
        ExpectedFinding(
            "WAGES.PAYMENT.FINAL_SETTLEMENT",
            worker.serial,
            "settled 24 days after exit",
            "HIGH",
        )
    )

    # 6. Excluded allowances above half of total remuneration — structural
    #    avoidance, and the one an employer is most likely to argue about.
    worker = workers[picks[5]]
    worker.other_allowances_paise = _round_to_rupee(
        int(worker.statutory_wages_paise * 1.4)
    )
    corpus.expected.append(
        ExpectedFinding(
            "WAGES.DEFINITION.EXCLUDED_HALF",
            worker.serial,
            "allowances inflated past half of total remuneration",
            "HIGH",
        )
    )

    # 7. Two workers absent from the EPF filing entirely.
    for index in picks[6:8]:
        worker = workers[index]
        worker.in_epf = False
        corpus.expected.append(
            ExpectedFinding(
                "SS.EPF.WORKERS_NOT_COVERED",
                worker.serial,
                "present in the wage register, absent from the EPF filing",
                "CRITICAL",
            )
        )

    # 8. EPF wage base suppressed below the register wages.
    worker = workers[picks[8]]
    worker.epf_wage_base_paise = _round_to_rupee(int(worker.statutory_wages_paise * 0.6))
    corpus.expected.append(
        ExpectedFinding(
            "SS.EPF.WAGE_BASE_UNDERSTATED",
            worker.serial,
            "contribution computed on 60% of the register wages",
            "HIGH",
        )
    )

    # 9. Paid for fewer days than the muster roll shows present.
    worker = workers[picks[9]]
    worker.days_present = worker.days_paid + 4
    worker.max_daily_hours = 13.5
    worker.longest_consecutive_days = 11
    corpus.expected.extend(
        [
            ExpectedFinding(
                "OSH.ATTENDANCE.DAYS_PAID_MATCH",
                worker.serial,
                "four days present but unpaid",
                "HIGH",
            ),
            ExpectedFinding(
                "OSH.HOURS.DAILY_CAP",
                worker.serial,
                "13.5 hours recorded on one day",
                "HIGH",
            ),
            ExpectedFinding(
                "WAGES.REST_DAY.WEEKLY",
                worker.serial,
                "eleven consecutive days without a rest day",
                "MEDIUM",
            ),
        ]
    )

    # 10. Overtime hours recorded with no overtime payment at all.
    worker = workers[picks[10]]
    worker.overtime_hours = 18.0
    worker.overtime_rate_paise = 0
    corpus.expected.append(
        ExpectedFinding(
            "OSH.OVERTIME.HOURS_PAID",
            worker.serial,
            "18 overtime hours recorded, nothing paid",
            "HIGH",
        )
    )

    # 11. Establishment-level: no wage slips are produced with the filing set.
    corpus.expected.append(
        ExpectedFinding(
            "WAGES.WAGE_SLIP.ISSUED",
            None,
            "no wage slips are included in the corpus",
            "MEDIUM",
        )
    )


# --------------------------------------------------------------------- output
def write_scanned_variants(out_dir: Path, *, dpi: int = 200) -> list[str]:
    """Render each PDF to an image-only PDF, removing the text layer.

    The reason this exists: every generated document carries a text layer, which is
    the easiest input the pipeline will ever see. Real employers photograph ledgers
    and scan carbon copies, and on those pages OCR is the only source of text and
    the only source of coordinates. Without image-only versions, that path — the
    one that actually decides whether this works in the field — is never exercised.

    The rendering is deliberately plain: no synthetic blur, skew or speckle. A
    filter applied to a clean render does not reproduce the failure modes of a real
    phone photograph, and pretending otherwise would flatter the system. This
    isolates one variable — no text layer — and leaves genuine scan quality to be
    tested with genuine scans.
    """
    import img2pdf  # noqa: PLC0415  optional, only needed for this path

    scanned_dir = out_dir / "scanned"
    scanned_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for source in sorted(out_dir.glob("*.pdf")):
        images: list[bytes] = []
        pdf = pdfium.PdfDocument(source.read_bytes())
        try:
            for index in range(len(pdf)):
                bitmap = pdf[index].render(scale=dpi / 72)
                image = bitmap.to_pil().convert("L")
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=80, optimize=True)
                images.append(buffer.getvalue())
        finally:
            pdf.close()

        if not images:
            continue

        target = scanned_dir / f"scan_{source.name}"
        target.write_bytes(img2pdf.convert(images))
        written.append(target.name)
        logger.info(
            "scanned variant written",
            extra={"source": source.name, "pages": len(images), "dpi": dpi},
        )

    return written


def write_corpus(corpus: Corpus, out_dir: Path, *, scanned: bool = False) -> Path:
    """Write the documents and the answer key. Returns the directory."""
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus.files = []
    _write_employee_register(corpus, out_dir)
    _write_wage_register(corpus, out_dir)
    _write_muster_roll(corpus, out_dir)
    _write_epf_ecr(corpus, out_dir)
    _write_appointment_letter(corpus, out_dir)

    if scanned:
        try:
            corpus.files.extend(write_scanned_variants(out_dir))
        except ImportError:
            logger.warning(
                "img2pdf is not installed, so image-only variants were not written; "
                "install it to exercise the OCR-only reading path"
            )

    truth = out_dir / "ground_truth.json"
    truth.write_text(
        json.dumps(corpus.ground_truth(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "corpus written",
        extra={
            "dir": str(out_dir),
            "files": len(corpus.files),
            "workers": len(corpus.workers),
            "expected_findings": len(corpus.expected),
        },
    )
    return out_dir


def _doc(path: Path, *, landscape_mode: bool) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4) if landscape_mode else A4,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=path.stem,
    )


def _header(corpus: Corpus, title: str, subtitle: str) -> list:
    styles = getSampleStyleSheet()
    return [
        Paragraph(f"<b>{corpus.establishment_name}</b>", styles["Title"]),
        Paragraph(
            f"State: {corpus.state_code} &nbsp;&nbsp; "
            f"Wage period: {corpus.period_start.strftime('%d-%m-%Y')} to "
            f"{corpus.period_end.strftime('%d-%m-%Y')} &nbsp;&nbsp; "
            "Wage period basis: monthly",
            styles["Normal"],
        ),
        Spacer(1, 4 * mm),
        Paragraph(f"<b>{title}</b>", styles["Heading2"]),
        Paragraph(subtitle, styles["Italic"]),
        Spacer(1, 3 * mm),
    ]


_TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.4),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
)


def _rupees(paise: int) -> str:
    return f"{paise / 100:,.2f}"


def _write_wage_register(corpus: Corpus, out_dir: Path) -> None:
    path = out_dir / "01_wage_register.pdf"
    document = _doc(path, landscape_mode=True)

    head = [
        "Sl", "Name of employee", "Desig.", "Cat.", "Days", "Basic", "DA",
        "Other allow.", "Gross", "OT hrs", "OT rate", "OT amt", "PF", "ESI",
        "Advance", "Total ded.", "Net paid", "Paid on",
    ]
    rows: list[list[str]] = [head]

    for worker in corpus.workers:
        rows.append(
            [
                str(worker.serial),
                worker.register_name,
                worker.designation,
                worker.skill.replace("_", " ").title(),
                str(worker.days_paid),
                _rupees(worker.basic_paise),
                _rupees(worker.da_paise),
                _rupees(worker.other_allowances_paise),
                _rupees(worker.gross_paise),
                f"{worker.overtime_hours:g}" if worker.overtime_hours else "-",
                _rupees(worker.overtime_rate_paise) if worker.overtime_rate_paise else "-",
                _rupees(worker.overtime_paise) if worker.overtime_paise else "-",
                _rupees(worker.pf_deduction_paise),
                _rupees(worker.esi_deduction_paise) if worker.esi_deduction_paise else "-",
                _rupees(worker.advance_recovery_paise) if worker.advance_recovery_paise else "-",
                _rupees(worker.deductions_paise),
                _rupees(worker.net_paid_paise),
                worker.paid_on.strftime("%d-%m-%Y") if worker.paid_on else "-",
            ]
        )

    # Printed column totals, so the extraction check that compares them against
    # the rows actually read has something to compare against.
    rows.append(
        [
            "", "TOTAL", "", "", "", "", "", "",
            _rupees(sum(w.gross_paise for w in corpus.workers)),
            "", "", "", "", "", "",
            _rupees(sum(w.deductions_paise for w in corpus.workers)),
            _rupees(sum(w.net_paid_paise for w in corpus.workers)),
            "",
        ]
    )

    table = Table(rows, repeatRows=1, hAlign="LEFT")
    style = TableStyle(_TABLE_STYLE.getCommands())
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    style.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e2e8f0"))
    table.setStyle(style)

    styles = getSampleStyleSheet()
    document.build(
        [
            *_header(
                corpus,
                "Register of Wages",
                "Maintained under section 50 of the Code on Wages, 2019. "
                f"Total workers: {len(corpus.workers)}.",
            ),
            table,
            Spacer(1, 5 * mm),
            Paragraph(
                "Certified that the wages shown above have been paid to the persons "
                "named. Signature of employer: ______________________",
                styles["Normal"],
            ),
        ]
    )
    corpus.files.append(path.name)


def _write_employee_register(corpus: Corpus, out_dir: Path) -> None:
    path = out_dir / "00_employee_register.pdf"
    document = _doc(path, landscape_mode=True)

    rows: list[list[str]] = [
        [
            "Sl", "Name of employee", "Father / husband name", "Emp. code", "UAN",
            "Designation", "Category", "Sex", "Date of joining", "Date of exit",
        ]
    ]
    for worker in corpus.workers:
        rows.append(
            [
                str(worker.serial),
                worker.full_name,
                worker.father,
                worker.employee_code,
                worker.uan,
                worker.designation,
                worker.skill.replace("_", " ").title(),
                worker.gender,
                worker.date_of_joining.strftime("%d-%m-%Y"),
                worker.date_of_exit.strftime("%d-%m-%Y") if worker.date_of_exit else "-",
            ]
        )

    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(_TABLE_STYLE)

    document.build(
        [
            *_header(
                corpus,
                "Register of Employees",
                f"Total workers: {len(corpus.workers)}. "
                f"Women workers: {sum(1 for w in corpus.workers if w.gender == 'F')}.",
            ),
            table,
        ]
    )
    corpus.files.append(path.name)


def _write_muster_roll(corpus: Corpus, out_dir: Path) -> None:
    path = out_dir / "02_muster_roll.pdf"
    document = _doc(path, landscape_mode=True)

    rows: list[list[str]] = [
        [
            "Sl", "Name", "Days present", "Days absent", "Weekly offs",
            "Total hours", "OT hours", "Max hours in a day",
            "Max hours in a week", "Longest run of worked days",
        ]
    ]
    for worker in corpus.workers:
        total_days = _month_length(corpus.period_start)
        absent = max(0, total_days - worker.days_present - 4)
        rows.append(
            [
                str(worker.serial),
                # Contracted form on purpose: this is the variant that tests
                # whether identity resolution is genuinely working.
                worker.muster_name,
                str(worker.days_present),
                str(absent),
                "4",
                f"{worker.days_present * 8:g}",
                f"{worker.overtime_hours:g}" if worker.overtime_hours else "-",
                f"{worker.max_daily_hours:g}",
                f"{worker.max_weekly_hours:g}",
                str(worker.longest_consecutive_days),
            ]
        )

    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(_TABLE_STYLE)

    document.build(
        [
            *_header(
                corpus,
                "Muster Roll",
                "Attendance summary for the wage period. P = present, A = absent, "
                "W = weekly off.",
            ),
            table,
        ]
    )
    corpus.files.append(path.name)


def _write_epf_ecr(corpus: Corpus, out_dir: Path) -> None:
    """EPF electronic challan cum return.

    Written as a PDF with a text layer rather than the pipe-delimited ECR text
    format, so the corpus exercises the same table-reading path as the registers.
    """
    path = out_dir / "03_epf_ecr.pdf"
    document = _doc(path, landscape_mode=False)

    included = [w for w in corpus.workers if w.in_epf]
    deposited = corpus.period_end + timedelta(days=13)

    rows: list[list[str]] = [
        ["UAN", "Member name", "EPF wages", "Employee share", "Employer share", "NCP days"]
    ]
    for worker in included:
        base = worker.epf_wage_base_paise or worker.statutory_wages_paise
        employee = _round_to_rupee(int(base * 0.12))
        employer = _round_to_rupee(int(base * 0.0367))
        ncp = max(0, 26 - worker.days_paid)
        rows.append(
            [
                worker.uan,
                worker.epf_name,
                _rupees(base),
                _rupees(employee),
                _rupees(employer),
                str(ncp),
            ]
        )

    total_base = sum(
        (w.epf_wage_base_paise or w.statutory_wages_paise) for w in included
    )
    rows.append(
        [
            "",
            "TOTAL",
            _rupees(total_base),
            _rupees(_round_to_rupee(int(total_base * 0.12))),
            _rupees(_round_to_rupee(int(total_base * 0.0367))),
            "",
        ]
    )

    table = Table(rows, repeatRows=1, hAlign="LEFT")
    style = TableStyle(_TABLE_STYLE.getCommands())
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    table.setStyle(style)

    styles = getSampleStyleSheet()
    document.build(
        [
            *_header(
                corpus,
                "Electronic Challan cum Return (EPF)",
                f"Members in this return: {len(included)}. "
                f"Amount remitted on {deposited.strftime('%d-%m-%Y')}. "
                f"TRRN: {corpus.period_start.strftime('%Y%m')}0004417.",
            ),
            table,
            Spacer(1, 4 * mm),
            Paragraph(
                f"Challan number: MHBAN{corpus.period_start.strftime('%y%m')}009812 "
                f"&nbsp;&nbsp; Date of deposit: {deposited.strftime('%d-%m-%Y')}",
                styles["Normal"],
            ),
        ]
    )
    corpus.files.append(path.name)


def _write_appointment_letter(corpus: Corpus, out_dir: Path) -> None:
    """One appointment letter, to exercise the prose reading path.

    Deliberately omits the notice period. That absence is what the prose
    assertions are meant to detect, and a letter with every clause present would
    not test anything.
    """
    path = out_dir / "04_appointment_letter.pdf"
    document = _doc(path, landscape_mode=False)

    worker = corpus.workers[0]
    styles = getSampleStyleSheet()

    body = [
        Paragraph(f"<b>{corpus.establishment_name}</b>", styles["Title"]),
        Spacer(1, 6 * mm),
        Paragraph(
            f"Ref: APPT/{corpus.period_start.strftime('%Y')}/{worker.serial:03d}"
            f" &nbsp;&nbsp;&nbsp; Date: {worker.date_of_joining.strftime('%d-%m-%Y')}",
            styles["Normal"],
        ),
        Spacer(1, 4 * mm),
        Paragraph("<b>LETTER OF APPOINTMENT</b>", styles["Heading2"]),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Dear {worker.full_name}, son/daughter of {worker.father},",
            styles["Normal"],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            f"We are pleased to appoint you to the post of <b>{worker.designation}</b> "
            f"at our establishment with effect from "
            f"{worker.date_of_joining.strftime('%d %B %Y')}. Your employee code is "
            f"{worker.employee_code}.",
            styles["Normal"],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Your consolidated monthly wages shall be Rs. "
            f"{_rupees(worker.gross_paise)}, comprising basic wages of Rs. "
            f"{_rupees(worker.basic_paise)}, dearness allowance of Rs. "
            f"{_rupees(worker.da_paise)} and other allowances of Rs. "
            f"{_rupees(worker.other_allowances_paise)}. Wages are payable on a "
            "monthly basis before the expiry of the seventh day of the succeeding "
            "month.",
            styles["Normal"],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            "Your normal hours of work shall be eight hours per day and forty-eight "
            "hours per week, with one day of rest in every period of seven days. "
            "Work beyond normal hours shall be paid at twice the ordinary rate of "
            "wages.",
            styles["Normal"],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            "You shall be entitled to leave with wages as provided under the "
            "applicable law and to the benefits of the Employees' Provident Fund "
            "and Employees' State Insurance schemes.",
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
        Paragraph(
            "For <b>%s</b><br/><br/><br/>Authorised Signatory"
            % corpus.establishment_name,
            styles["Normal"],
        ),
        PageBreak(),
        Paragraph(
            "<i>Note for the evaluation corpus: this letter deliberately omits any "
            "notice period for termination. The prose reading path should report "
            "states_notice_period as not stated.</i>",
            styles["Italic"],
        ),
    ]

    document.build(body)
    corpus.files.append(path.name)


# -------------------------------------------------------------------- helpers
def _round_to_rupee(paise: int) -> int:
    """Round to whole rupees, as registers do.

    Important for the corpus to be realistic: the arithmetic checks allow a
    one-rupee tolerance precisely because real registers round, and a corpus with
    exact paise would not exercise that tolerance.
    """
    return int(round(paise / 100.0)) * 100


def _month_end(start: date) -> date:
    if start.month == 12:
        return date(start.year, 12, 31)
    return date(start.year, start.month + 1, 1) - timedelta(days=1)


def _month_length(start: date) -> int:
    return _month_end(start).day
