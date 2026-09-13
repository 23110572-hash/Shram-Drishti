"""JSON schemas the model must answer with, one per document type.

Three decisions shape every schema here.

**Money and dates are strings, not JSON numbers.** A JSON number goes through a
float on the way in, and ``1234.56`` does not survive that exactly. Since these
figures decide whether a worker was underpaid, amounts come back as strings and
are parsed with ``Decimal`` into integer paise. Dates come back as ``YYYY-MM-DD``
strings for the same reason: no locale ambiguity between 03/04 and 04/03.

**Blank is a value.** Every field is required by the schema and nullable in type,
because OpenAI-style strict mode demands that every property appear in
``required``. A field the model could omit would be indistinguishable from a
field it read as empty, and "the register has no entry here" is exactly the
finding we are looking for.

**No coordinates are requested.** Asking a model for bounding boxes produces
plausible-looking numbers that do not correspond to the page. Coordinates are
instead derived by locating each returned value among the OCR tokens, which does
double duty: it proves the value exists on the page and gives its true position.
"""

from __future__ import annotations

from typing import Any

from app.models.enums import DocumentType

# --------------------------------------------------------------- schema helpers
# Types are lists including "null" so a field can be present-but-empty. Strict
# mode requires every property in "required", so nullability is the only way to
# express "the model looked and there was nothing there".


def _text(description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "description": description}


def _money(description: str) -> dict[str, Any]:
    return {
        "type": ["string", "null"],
        "description": (
            f"{description} Plain rupees as digits with an optional decimal part, "
            "no currency symbol, no thousands separators, e.g. '15250.50'. "
            "Null if the cell is blank."
        ),
    }


def _number(description: str) -> dict[str, Any]:
    return {
        "type": ["number", "null"],
        "description": f"{description} Null if the cell is blank.",
    }


def _integer(description: str) -> dict[str, Any]:
    return {
        "type": ["integer", "null"],
        "description": f"{description} Null if the cell is blank.",
    }


def _date(description: str) -> dict[str, Any]:
    return {
        "type": ["string", "null"],
        "description": (
            f"{description} Format YYYY-MM-DD. If the document shows a partial "
            "date, use the first day of the stated period. Null if absent."
        ),
    }


def _bool(description: str) -> dict[str, Any]:
    return {"type": ["boolean", "null"], "description": description}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    """Strict object: no extra keys, every declared key required."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(properties),
    }


def _array(items: dict[str, Any], description: str) -> dict[str, Any]:
    return {"type": "array", "description": description, "items": items}


# ------------------------------------------------------------------ provenance
# Attached to every schema. Two blocks that make the output checkable rather
# than merely plausible.

_PAGE_FIELD = _integer(
    "The 1-based page number of this document that this row was read from."
)

CORRECTION_ITEM = _object(
    {
        "page": _integer("Page where the disagreement occurs."),
        "ocr_text": _text("Exactly what the OCR text contained."),
        "corrected_to": _text("What the page image actually shows."),
        "reason": _text(
            "Why the OCR reading is wrong, e.g. 'OCR merged two columns' or "
            "'8 misread as 3'."
        ),
    }
)

_PROVENANCE_PROPERTIES: dict[str, Any] = {
    "corrections": _array(
        CORRECTION_ITEM,
        "Every value where the OCR text and the page image disagree and you "
        "trusted the image. Leave empty if they agreed everywhere. Never "
        "silently override OCR: if it is not listed here it will be treated as "
        "an unsupported figure and held for human review.",
    ),
    "unreadable_regions": _array(
        _object(
            {
                "page": _integer("Page number."),
                "description": _text("What is illegible and roughly where."),
            }
        ),
        "Regions you could not read: torn paper, ink bleed, a stamp over "
        "figures, handwriting you cannot make out. Report them rather than "
        "guessing.",
    ),
    "notes": _text(
        "Anything an inspector should know about how this document was read. "
        "Null if there is nothing of note."
    ),
}


def _with_provenance(payload: dict[str, Any]) -> dict[str, Any]:
    return _object({**payload, **_PROVENANCE_PROPERTIES})


# ----------------------------------------------------------------- header block
# Fields that identify which establishment and which period a document covers.
# Extracted for every type, because a document that cannot be bound to an
# establishment and a period cannot be evaluated against anything.

HEADER = _object(
    {
        "establishment_name": _text("Establishment or employer name as printed."),
        "lin": _text("Labour Identification Number, if printed."),
        "registration_number": _text(
            "Any registration, licence, EPF or ESIC code printed on the document."
        ),
        "address": _text("Address as printed."),
        "state": _text("State or union territory named on the document."),
        "period_start": _date("First day of the period this document covers."),
        "period_end": _date("Last day of the period this document covers."),
        "wage_period_basis": {
            "type": ["string", "null"],
            "enum": ["daily", "weekly", "fortnightly", "monthly", None],
            "description": "Wage period stated on the document, if any.",
        },
    }
)


# --------------------------------------------------------------- classification
CLASSIFICATION_SCHEMA = _object(
    {
        "doc_type": {
            "type": "string",
            "enum": [t.value for t in DocumentType],
            "description": (
                "Which register, return or record this is. Use UNKNOWN if it "
                "does not clearly match one of the others — a wrong "
                "classification sends the document down the wrong extraction "
                "path and produces confident nonsense."
            ),
        },
        "confidence": {
            "type": "number",
            "description": "0 to 1. Be honest; a low score routes it to a human.",
        },
        "reasoning": _text("One sentence: which visible features decided this."),
        "header": HEADER,
        "looks_like_multiple_documents": _bool(
            "True if this file appears to contain several different documents "
            "bundled together."
        ),
        "contains_worker_identifiers": _bool(
            "True if Aadhaar, PAN, bank account or similar identifiers are "
            "visible. Used to decide whether the stored copy needs redaction."
        ),
    }
)


# ------------------------------------------------------------- wage register
WAGE_ROW = _object(
    {
        "page": _PAGE_FIELD,
        "row_number": _integer("Serial number printed against the row, if any."),
        "worker_name": _text("Worker name exactly as printed, no normalisation."),
        "father_or_husband_name": _text("Father's or husband's name, if a column exists."),
        "employee_code": _text("Employee number or token number as printed."),
        "uan": _text("Universal Account Number, 12 digits, if a column exists."),
        "designation": _text("Designation or trade as printed."),
        "skill_category": {
            "type": ["string", "null"],
            "enum": ["UNSKILLED", "SEMI_SKILLED", "SKILLED", "HIGHLY_SKILLED", None],
            "description": "Skill classification if the register states one.",
        },
        "gender": _text("Gender as printed, if a column exists."),
        "days_paid": _number("Number of days paid for."),
        "days_present": _number("Days present, if the register also shows attendance."),
        "normal_hours_per_day": _number("Normal daily hours, if stated."),
        "overtime_hours": _number("Overtime hours for the period."),
        "basic": _money("Basic wages for the period."),
        "dearness_allowance": _money("Dearness allowance."),
        "other_allowances": _money(
            "All other allowances combined: HRA, conveyance, special allowance "
            "and similar."
        ),
        "gross": _money("Gross wages as printed."),
        "overtime_amount": _money("Overtime wages paid."),
        "overtime_rate": _money("Overtime rate per hour, if stated."),
        "pf_deduction": _money("Provident fund deduction."),
        "esi_deduction": _money("Employees' State Insurance deduction."),
        "advance_recovery": _money("Advance or loan recovery."),
        "total_deductions": _money("Total of all deductions as printed."),
        "net_paid": _money("Net amount paid as printed."),
        "paid_on": _date("Date of payment for this row."),
        "date_of_joining": _date("Date of joining, if a column exists."),
        "date_of_exit": _date("Date of exit, leaving or discharge, if shown."),
    }
)

WAGE_REGISTER_SCHEMA = _with_provenance(
    {
        "header": HEADER,
        "rows": _array(
            WAGE_ROW,
            "One entry per worker row. Transcribe every row on every page you "
            "were given, in the order printed. Do not summarise, do not skip "
            "rows that look like duplicates, and do not compute values that are "
            "not printed.",
        ),
        "column_mapping": _array(
            _object(
                {
                    "printed_heading": _text("Column heading as printed."),
                    "mapped_to": _text(
                        "Which schema field you mapped it to, or null if you "
                        "ignored it."
                    ),
                }
            ),
            "How you interpreted each printed column heading. This is what lets "
            "a reviewer catch a wrong mapping, which is the failure mode that "
            "silently corrupts every row.",
        ),
        "printed_totals": _object(
            {
                "gross": _money("Column total for gross, if the register prints one."),
                "deductions": _money("Column total for deductions, if printed."),
                "net_paid": _money("Column total for net paid, if printed."),
                "worker_count": _integer("Worker count if the register states one."),
            }
        ),
    }
)


# ----------------------------------------------------------- employee register
EMPLOYEE_ROW = _object(
    {
        "page": _PAGE_FIELD,
        "row_number": _integer("Serial number printed against the row."),
        "worker_name": _text("Worker name exactly as printed."),
        "father_or_husband_name": _text("Father's or husband's name."),
        "employee_code": _text("Employee number as printed."),
        "uan": _text("Universal Account Number, if shown."),
        "esic_number": _text("ESIC insurance number, if shown."),
        "designation": _text("Designation or trade."),
        "skill_category": {
            "type": ["string", "null"],
            "enum": ["UNSKILLED", "SEMI_SKILLED", "SKILLED", "HIGHLY_SKILLED", None],
            "description": "Skill classification if stated.",
        },
        "gender": _text("Gender as printed."),
        "date_of_birth": _date("Date of birth."),
        "date_of_joining": _date("Date of joining."),
        "date_of_exit": _date("Date of exit or leaving."),
        "is_contract_worker": _bool(
            "True if the register marks this person as contract labour."
        ),
        "contractor_name": _text("Contractor name, for contract workers."),
    }
)

EMPLOYEE_REGISTER_SCHEMA = _with_provenance(
    {
        "header": HEADER,
        "rows": _array(EMPLOYEE_ROW, "One entry per worker listed in the register."),
        "printed_totals": _object(
            {
                "worker_count": _integer("Total workers if the register states one."),
                "women_count": _integer("Women workers if stated."),
            }
        ),
    }
)


# ---------------------------------------------------------------- muster roll
ATTENDANCE_ROW = _object(
    {
        "page": _PAGE_FIELD,
        "worker_name": _text("Worker name exactly as printed."),
        "employee_code": _text("Employee number as printed."),
        "days_present": _number("Total days marked present."),
        "days_absent": _number("Total days marked absent."),
        "weekly_offs_given": _integer("Number of weekly rest days marked."),
        "total_hours": _number("Total hours worked in the period, if recorded."),
        "overtime_hours": _number("Total overtime hours in the period."),
        "max_daily_hours": _number(
            "The highest hours recorded on any single day, including overtime. "
            "If the roll shows in and out times, use the longest day."
        ),
        "max_weekly_hours": _number("The highest hours recorded in any single week."),
        "longest_consecutive_days": _integer(
            "The longest unbroken run of worked days without a rest day. Count "
            "across the whole period shown, including runs that span weeks."
        ),
        "daily_marks": _text(
            "The day-by-day marks as a compact string, e.g. 'PPPPAPW' where "
            "P=present, A=absent, W=weekly off. Null if the roll only shows "
            "totals."
        ),
    }
)

MUSTER_ROLL_SCHEMA = _with_provenance(
    {
        "header": HEADER,
        "rows": _array(
            ATTENDANCE_ROW,
            "One entry per worker. Attendance rolls are wide grids; work row by "
            "row and do not let your eye drift between rows.",
        ),
    }
)


# ------------------------------------------------------------- contributions
CONTRIBUTION_ROW = _object(
    {
        "page": _PAGE_FIELD,
        "worker_name": _text("Member name exactly as printed."),
        "uan": _text("Universal Account Number, 12 digits."),
        "member_id": _text("Member or insurance number as printed."),
        "wage_base": _money("Wages on which the contribution was computed."),
        "employee_share": _money("Employee contribution."),
        "employer_share": _money("Employer contribution."),
        "ncp_days": _number("Non-contributory period days, if shown."),
    }
)

CONTRIBUTION_SCHEMA = _with_provenance(
    {
        "header": HEADER,
        "scheme": {
            "type": "string",
            "enum": ["EPF", "ESIC"],
            "description": "Which scheme this filing belongs to.",
        },
        "challan_number": _text("Challan or TRRN number as printed."),
        "deposited_on": _date("Date the amount was deposited or remitted."),
        "rows": _array(CONTRIBUTION_ROW, "One entry per member in the filing."),
        "printed_totals": _object(
            {
                "wage_base": _money("Total wage base if printed."),
                "employee_share": _money("Total employee share if printed."),
                "employer_share": _money("Total employer share if printed."),
                "member_count": _integer("Member count if stated."),
            }
        ),
    }
)


# ------------------------------------------------------------------ incidents
INCIDENT_ROW = _object(
    {
        "page": _PAGE_FIELD,
        "occurred_on": _date("Date the accident or occurrence happened."),
        "description": _text("What happened, as recorded."),
        "severity": _text(
            "Severity as recorded, e.g. fatal, serious, reportable, minor."
        ),
        "workers_affected": _integer("Number of workers involved."),
        "notified_on": _date(
            "Date notice was given to the authority. Null if no notification is "
            "recorded — this absence is itself significant, so do not infer one."
        ),
        "notification_reference": _text("Reference number of the notification."),
    }
)

INCIDENT_SCHEMA = _with_provenance(
    {
        "header": HEADER,
        "rows": _array(INCIDENT_ROW, "One entry per recorded accident or occurrence."),
    }
)


# ----------------------------------------------------------- registrations
REGISTRATION_SCHEMA = _with_provenance(
    {
        "header": HEADER,
        "kind": _text(
            "What this certificate is, e.g. ESTABLISHMENT_REGISTRATION, "
            "FACTORY_LICENCE, CONTRACTOR_LICENCE, EPF, ESIC, BOCW."
        ),
        "number": _text("Registration, licence or certificate number."),
        "issuing_authority": _text("Authority that issued it."),
        "holder_name": _text("Name of the establishment or contractor it is issued to."),
        "valid_from": _date("Date validity begins."),
        "valid_to": _date(
            "Date validity ends. Null if the certificate is open-ended — do not "
            "invent an expiry, because a null means 'does not expire' and a "
            "wrong date would read as a lapsed licence."
        ),
        "licensed_worker_count": _integer(
            "Maximum workers permitted, for a contractor licence."
        ),
    }
)


# ------------------------------------------------------------------ prose
# Appointment letters, standing orders, committee records and policies are
# paragraphs, not tables. There is no cell to extract, so the model answers
# specific questions and each answer carries the sentence that supports it.

PROSE_ASSERTION = _object(
    {
        "key": _text("The question identifier you were asked about."),
        "present": {
            "type": "boolean",
            "description": "Whether the document states this at all.",
        },
        "value": _text(
            "The stated value, verbatim where possible. Null if not stated."
        ),
        "quote": _text(
            "The exact sentence or clause from the document that supports this. "
            "Null only when present is false. Do not paraphrase: this quotation "
            "is what makes the answer checkable."
        ),
        "page": _PAGE_FIELD,
        "confidence": _number("0 to 1."),
    }
)

PROSE_SCHEMA = _with_provenance(
    {
        "header": HEADER,
        "document_kind": _text("What kind of document this is, in your own words."),
        "assertions": _array(
            PROSE_ASSERTION,
            "One entry for every question you were asked, in the same order. "
            "Answer 'not stated' rather than inferring an answer from context.",
        ),
    }
)


# ------------------------------------------------------------- identity match
IDENTITY_MATCH_SCHEMA = _object(
    {
        "matches": _array(
            _object(
                {
                    "candidate_name": _text("The name from the list you were given."),
                    "candidate_id": _text("The identifier attached to that name."),
                    "is_same_person": {
                        "type": "boolean",
                        "description": "Whether this is the same person as the query.",
                    },
                    "confidence": _number("0 to 1."),
                    "reason": _text(
                        "Short justification, e.g. 'initial expanded, patronymic "
                        "dropped, same father name'."
                    ),
                }
            ),
            "One entry per candidate you were given, in the same order.",
        )
    }
)


# --------------------------------------------------------- false positive check
FALSE_POSITIVE_SCHEMA = _object(
    {
        "assessments": _array(
            _object(
                {
                    "finding_id": _text("The finding identifier you were given."),
                    "possible_false_positive": {
                        "type": "boolean",
                        "description": (
                            "True only if there is a concrete reason visible in "
                            "the evidence why this finding is likely wrong — a "
                            "misread figure, a column mapped to the wrong field, "
                            "a legitimate exemption stated on the document. "
                            "Disagreeing with the law is not a reason."
                        ),
                    },
                    "reason": _text("Why. Null when the finding looks sound."),
                    "plain_explanation": _text(
                        "Two or three sentences an employer with no legal "
                        "training would understand, explaining what was found "
                        "and what to do about it. Do not restate the statute."
                    ),
                }
            ),
            "One entry per finding you were given, in the same order.",
        )
    }
)


# -------------------------------------------------------------- routing tables

#: Which schema to use for each document type.
SCHEMA_BY_DOC_TYPE: dict[DocumentType, dict[str, Any]] = {
    DocumentType.WAGE_REGISTER: WAGE_REGISTER_SCHEMA,
    DocumentType.WAGE_SLIP: WAGE_REGISTER_SCHEMA,
    DocumentType.OVERTIME_REGISTER: WAGE_REGISTER_SCHEMA,
    DocumentType.DEDUCTION_REGISTER: WAGE_REGISTER_SCHEMA,
    DocumentType.EMPLOYEE_REGISTER: EMPLOYEE_REGISTER_SCHEMA,
    DocumentType.MUSTER_ROLL: MUSTER_ROLL_SCHEMA,
    DocumentType.LEAVE_REGISTER: MUSTER_ROLL_SCHEMA,
    DocumentType.EPF_ECR: CONTRIBUTION_SCHEMA,
    DocumentType.ESIC_CHALLAN: CONTRIBUTION_SCHEMA,
    DocumentType.ACCIDENT_REGISTER: INCIDENT_SCHEMA,
    DocumentType.ESTABLISHMENT_REGISTRATION: REGISTRATION_SCHEMA,
    DocumentType.CONTRACTOR_LICENCE: REGISTRATION_SCHEMA,
    DocumentType.BOCW_CESS_RECEIPT: REGISTRATION_SCHEMA,
    DocumentType.APPOINTMENT_LETTER: PROSE_SCHEMA,
    DocumentType.STANDING_ORDERS: PROSE_SCHEMA,
    DocumentType.GRIEVANCE_COMMITTEE_RECORD: PROSE_SCHEMA,
    DocumentType.HEALTH_CHECKUP_RECORD: PROSE_SCHEMA,
    DocumentType.WELFARE_FACILITY_RECORD: PROSE_SCHEMA,
    DocumentType.ANNUAL_RETURN: PROSE_SCHEMA,
}

#: Which questions to ask of each prose document type. These map directly onto
#: the ``prose.*`` facts the rule packs read, so adding a rule that needs a new
#: prose fact means adding the question here.
PROSE_QUESTIONS: dict[DocumentType, list[tuple[str, str]]] = {
    DocumentType.APPOINTMENT_LETTER: [
        ("states_employee_name", "Does it name the employee it is addressed to?"),
        ("states_designation", "Does it state the designation or post?"),
        ("states_date_of_joining", "Does it state the date of joining?"),
        ("states_wage_rate", "Does it state the wages or salary payable?"),
        ("states_wage_period", "Does it state how often wages are paid?"),
        ("states_working_hours", "Does it state the daily or weekly working hours?"),
        ("states_notice_period", "Does it state a notice period for termination?"),
        ("states_leave_entitlement", "Does it state leave entitlement?"),
        ("is_fixed_term", "Is this a fixed term appointment with an end date?"),
        ("is_signed_by_employer", "Is it signed or stamped on behalf of the employer?"),
    ],
    DocumentType.STANDING_ORDERS: [
        ("is_certified", "Do these standing orders bear a certification by the certifying officer?"),
        ("certified_on", "What date were they certified?"),
        ("adopts_model_standing_orders", "Do they state that the model standing orders are adopted?"),
        ("covers_classification_of_workers", "Do they classify workers, e.g. permanent, probationer, fixed term?"),
        ("covers_disciplinary_procedure", "Do they set out a disciplinary procedure?"),
        ("covers_termination", "Do they set out termination and notice conditions?"),
        ("covers_grievance_procedure", "Do they set out how grievances are raised?"),
        ("is_displayed", "Do they record that they are displayed at the establishment?"),
    ],
    DocumentType.GRIEVANCE_COMMITTEE_RECORD: [
        ("grievance_committee_members", "How many members does the committee have in total? Answer with a number."),
        ("grievance_committee_women", "How many members are women? Answer with a number."),
        ("grievance_committee_employer_reps", "How many members represent the employer? Answer with a number."),
        ("grievance_committee_worker_reps", "How many members represent the workers? Answer with a number."),
        ("has_chairperson", "Is a chairperson named?"),
        ("grievances_received", "How many grievances were received in the period? Answer with a number."),
        ("grievances_decided", "How many were decided? Answer with a number."),
        ("longest_grievance_days", "For the slowest grievance, how many days passed between the application and the decision? Answer with a number."),
    ],
    DocumentType.HEALTH_CHECKUP_RECORD: [
        ("examination_date", "What date were the examinations carried out?"),
        ("workers_examined", "How many workers were examined? Answer with a number."),
        ("examined_by", "Who carried out the examinations?"),
        ("free_of_cost", "Does it record that the examination was free of cost to the worker?"),
    ],
    DocumentType.WELFARE_FACILITY_RECORD: [
        ("facility_kind", "Which facility does this record concern, e.g. creche, canteen, first aid, drinking water, washing?"),
        ("is_provided", "Does it record the facility as actually provided and in use?"),
        ("capacity", "What capacity or quantity is recorded? Answer with a number if stated."),
        ("inspected_on", "What date was it last inspected or verified?"),
    ],
    DocumentType.ANNUAL_RETURN: [
        ("total_workers", "What total number of workers does the return declare? Answer with a number."),
        ("women_workers", "How many women workers does it declare? Answer with a number."),
        ("contract_workers", "How many contract workers does it declare? Answer with a number."),
        ("fixed_term_employee_count", "How many fixed term employees does it declare? Answer with a number."),
        ("fixed_term_gratuity_accrued", "Does it record gratuity as accrued for fixed term employees?"),
        ("retrenchment_count", "How many workers were laid off or retrenched in the year? Answer with a number."),
        ("has_government_permission", "Does it record prior government permission for any lay-off, retrenchment or closure?"),
        ("strike_notice_days", "If a strike or lock-out occurred, how many days notice were given? Answer with a number."),
        ("is_aggregator", "Does the establishment describe itself as an aggregator or platform?"),
        ("gig_worker_count", "How many gig or platform workers does it declare? Answer with a number."),
        ("aggregator_contribution", "What aggregator contribution amount does it record? Answer with an amount in rupees."),
        ("accidents_reported", "How many accidents does it report for the year? Answer with a number."),
    ],
}


def prose_questions_for(doc_type: DocumentType) -> list[tuple[str, str]]:
    return PROSE_QUESTIONS.get(doc_type, [])


# =============================================================================
# Schemas for the judgement passes.
#
# Everything above reads a document. Everything below asks the model to make a
# judgement about messy reality — which name is which person, which
# establishment a document belongs to, whether a figure means what it appears to
# mean, and what is wrong here that no rule thought to look for.
#
# These are the places where a hand-written Python heuristic would be guessing.
# The variation in real Indian labour records is unbounded: transliteration
# differs between filings, establishments trade under several names, dates appear
# in half a dozen formats, and registers are laid out however the shop chose. A
# threshold tuned on the documents we happened to see would fail on the next one.
# =============================================================================


# --------------------------------------------------------- roster resolution
# One call resolves a whole document's roster against every known worker, rather
# than one call per name. This is not only cheaper: it is more accurate, because
# the model can see that two printed names compete for the same person and
# resolve them together instead of independently.

ROSTER_RESOLUTION_SCHEMA = _object(
    {
        "resolutions": _array(
            _object(
                {
                    "printed_index": _integer(
                        "The index of the printed name from the list you were "
                        "given, starting at 0."
                    ),
                    "matched_worker_id": _text(
                        "The id of the known worker this is the same person as. "
                        "Null when this is a worker not seen before, which is a "
                        "normal and correct answer."
                    ),
                    "same_as_printed_index": _integer(
                        "If this printed name refers to the same person as an "
                        "earlier printed name in this same list, give that "
                        "index. Null otherwise. Registers do contain the same "
                        "worker twice."
                    ),
                    "confidence": _number(
                        "0 to 1. Below 0.75 no link is made and the row is held "
                        "for review, which is the right outcome when unsure."
                    ),
                    "reason": _text(
                        "Why, specifically. 'initial expanded and father's name "
                        "matches' is useful; 'names are similar' is not."
                    ),
                    "canonical_name": _text(
                        "The fullest, most complete spelling among all the "
                        "variants you have seen for this person. This becomes "
                        "the display name."
                    ),
                }
            ),
            "One entry for every printed name you were given, in the same order. "
            "Do not omit any, and do not add any.",
        ),
        "warnings": _array(
            _text("A caution an inspector should see."),
            "Anything troubling about this roster: two workers with identical "
            "names and different identifiers, a name that could plausibly be "
            "either of two known workers, a row that looks like a subtotal "
            "rather than a person.",
        ),
    }
)


# ------------------------------------------------------------------- binding
# Deciding which establishment and which period a document belongs to. An
# employer's register header rarely matches the registered name exactly: it uses
# a trading name, a unit name, an abbreviation, or a different transliteration.

BINDING_SCHEMA = _object(
    {
        "matched_establishment_id": _text(
            "The id of the establishment this document belongs to, or null if "
            "you cannot tell. Null routes it to a human, which is far better "
            "than attaching a wage register to the wrong employer."
        ),
        "confidence": _number("0 to 1."),
        "reason": _text(
            "Which specific evidence decided it: a matching LIN, a matching "
            "registration number, the address, the unit name."
        ),
        "period_start": _date(
            "The first day of the period this document covers, resolved from "
            "whatever the document states."
        ),
        "period_end": _date("The last day of that period."),
        "period_basis": {
            "type": ["string", "null"],
            "enum": ["daily", "weekly", "fortnightly", "monthly", "annual", None],
            "description": "The period type this document covers.",
        },
        "period_reason": _text(
            "How you arrived at the period, especially if the document states it "
            "loosely, e.g. 'header reads March 2026 so the month is 1 to 31 "
            "March 2026'."
        ),
    }
)


# -------------------------------------------------------------- normalisation
# A fallback for values that could not be parsed mechanically. Rather than
# guessing at "05-04-26" or discarding it, the model is asked what it means, in
# context. Discarding a legible date loses a finding; guessing produces a wrong
# one.

NORMALISATION_SCHEMA = _object(
    {
        "results": _array(
            _object(
                {
                    "index": _integer("Index of the value you were given, from 0."),
                    "kind": {
                        "type": "string",
                        "enum": ["date", "amount", "number", "unresolved"],
                        "description": (
                            "What this value turned out to be. Use 'unresolved' "
                            "when it is genuinely not interpretable — that is an "
                            "honest answer and it will be treated as missing."
                        ),
                    },
                    "iso_date": _date("The date, if kind is date."),
                    "amount_rupees": _text(
                        "The amount in plain rupees as digits, if kind is amount "
                        "or number, e.g. '15250.50'."
                    ),
                    "reason": _text("How you read it, one short sentence."),
                    "confidence": _number("0 to 1."),
                }
            ),
            "One entry per value you were given, in the same order.",
        )
    }
)


# ---------------------------------------------------------------- the analyst
# The open-ended pass. Rules encode what the statute says; this asks what is
# actually wrong with these documents. A fixed rule list cannot anticipate every
# way an employer's records can be inconsistent, so this exists to catch what the
# rules did not think to look for.
#
# Everything it raises is advisory. It cannot create a non-compliance finding,
# because a legal conclusion needs a statutory citation and a reproducible test,
# and this pass has neither. What it can do is tell an inspector where to look.

ANALYST_SCHEMA = _object(
    {
        "rule_assessments": _array(
            _object(
                {
                    "finding_id": _text("The finding id you were given."),
                    "verdict": {
                        "type": "string",
                        "enum": ["sound", "possible_false_positive", "unclear"],
                        "description": (
                            "Whether the finding holds up against the evidence. "
                            "Answer possible_false_positive only for a concrete "
                            "reason visible in the documents: a misread figure, "
                            "a column mapped to the wrong field, an exemption "
                            "stated on the document itself. Disagreeing with the "
                            "law is not a reason."
                        ),
                    },
                    "reason": _text("Why, citing what you saw. Null if sound."),
                    "plain_explanation": _text(
                        "Two or three sentences an employer with no legal "
                        "training would understand: what was found, in which "
                        "document, and what to do. Do not restate the statute."
                    ),
                    "severity_opinion": {
                        "type": ["string", "null"],
                        "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", None],
                        "description": (
                            "How serious this looks in context. Advisory only: "
                            "it is recorded beside the rule's severity, never "
                            "instead of it."
                        ),
                    },
                }
            ),
            "One entry per finding you were given, in the same order.",
        ),
        "additional_observations": _array(
            _object(
                {
                    "kind": {
                        "type": "string",
                        "enum": ["DISCREPANCY", "MISSING_FIELD", "ANOMALY"],
                        "description": (
                            "DISCREPANCY when two documents contradict each "
                            "other. MISSING_FIELD when a register omits "
                            "something it should carry. ANOMALY when a pattern "
                            "is merely suspicious. You may not raise a "
                            "non-compliance: that requires a statutory citation "
                            "and a reproducible test, which is what the rules "
                            "are for."
                        ),
                    },
                    "code": {
                        "type": ["string", "null"],
                        "enum": [
                            "WAGES",
                            "INDUSTRIAL_RELATIONS",
                            "SOCIAL_SECURITY",
                            "OSH",
                            None,
                        ],
                        "description": "Which Code this concerns, if clear.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
                        "description": "How serious this looks.",
                    },
                    "title": _text("One line, specific. Not 'data quality issue'."),
                    "detail": _text(
                        "What you observed and in which documents, with the "
                        "actual figures. An inspector must be able to verify "
                        "this from the documents without asking you."
                    ),
                    "evidence_pages": _array(
                        _integer("Page number."),
                        "Pages that show this. Empty if it is a pattern across "
                        "the whole document rather than a specific place.",
                    ),
                    "affected_workers": _array(
                        _text("Worker name as printed."),
                        "Workers this concerns, if it is specific to some.",
                    ),
                    "suggested_check": _text(
                        "What an inspector should verify to confirm or dismiss "
                        "this."
                    ),
                    "confidence": _number("0 to 1."),
                }
            ),
            "Problems you can see that the rules did not raise. Be specific and "
            "quantitative. Report nothing rather than padding this list: a "
            "vague observation costs an inspector time and finds nothing. "
            "Look especially for figures that are internally consistent but "
            "implausible, patterns that repeat too regularly to be real, "
            "documents that agree with each other but not with the workforce "
            "they describe, and entries that appear to have been altered.",
        ),
        "overall_assessment": _text(
            "Three or four sentences for the inspector: what these documents "
            "collectively suggest about this establishment, and where you would "
            "look first. Say plainly if the records look sound."
        ),
        "records_quality": {
            "type": "string",
            "enum": ["good", "adequate", "poor", "unusable"],
            "description": (
                "How well these records support any conclusion at all. Reported "
                "separately from compliance: records too poor to judge are a "
                "different problem from records that show a breach."
            ),
        },
    }
)


# ------------------------------------------------------- cross-document review
# Given several documents for the same establishment and period, look for
# contradictions between them. This is where real evasion shows up: each
# document is internally consistent and correct-looking, and only the comparison
# reveals the problem.

CROSS_DOCUMENT_SCHEMA = _object(
    {
        "contradictions": _array(
            _object(
                {
                    "title": _text("One line naming the contradiction."),
                    "detail": _text(
                        "Which documents disagree, about what, with the figures "
                        "from each."
                    ),
                    "documents_involved": _array(
                        _text("Document id as given to you."),
                        "The documents that disagree.",
                    ),
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
                        "description": "How serious this looks.",
                    },
                    "code": {
                        "type": ["string", "null"],
                        "enum": [
                            "WAGES",
                            "INDUSTRIAL_RELATIONS",
                            "SOCIAL_SECURITY",
                            "OSH",
                            None,
                        ],
                        "description": "Which Code this concerns, if clear.",
                    },
                    "affected_workers": _array(
                        _text("Worker name as printed."), "Workers concerned."
                    ),
                    "confidence": _number("0 to 1."),
                }
            ),
            "Every contradiction between the documents. Each must name the "
            "documents and quote the conflicting figures.",
        ),
        "consistency_notes": _text(
            "What is consistent across the documents. Worth stating, because an "
            "establishment whose records reconcile cleanly deserves to be told so."
        ),
    }
)
