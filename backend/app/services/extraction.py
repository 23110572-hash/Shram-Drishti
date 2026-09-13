"""Document reading: OCR, the model, and conversion into canonical records.

Reading mode is chosen per page, not per document, because one PDF routinely
mixes a typed cover sheet with photographed registers.

* **Mode A, native text.** The PDF carries a text layer, so it is read directly.
  Exact, costs nothing, involves neither OCR nor the model. The best outcome.
* **Mode B, OCR plus vision.** The OCR text *and* the page image go to the model
  in one request. This is the default. The model can see what OCR misread, and
  every figure it returns is checked back against the OCR tokens, which is what
  makes an invented number detectable.
* **Mode C, vision only.** OCR was unavailable, out of quota, or the page would
  not compress under the size limit. The model still reads the page, but there
  are no tokens to check against, so evidence degrades to page level and every
  numeric value is marked ``model_only``.

Sending OCR and image together rather than in sequence is deliberate. A
sequential design where the model only ever sees OCR text can never catch an OCR
misread, because it has nothing to compare against; and a design that only sends
the image has nothing to hold the model to. The combination is what makes the
three safety checks in ``verify`` possible at all.

This module deliberately does no database work. It takes plain page data in and
returns plain records out, so it can be exercised against fixtures without a
database or a network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.models.enums import DocumentType, ExtractionMode, SchemaSource, SkillCategory
from app.services import verify
from app.services.doc_schemas import (
    CLASSIFICATION_SCHEMA,
    SCHEMA_BY_DOC_TYPE,
    prose_questions_for,
)
from app.services.llm import (
    BudgetExceeded,
    BudgetTracker,
    ContentPart,
    LlmClient,
    LlmError,
    SchemaViolation,
    image_part,
    text_part,
)
from app.services.verify import Agreement, Trace

logger = logging.getLogger(__name__)

# Below this the OCR text is treated as a failed read rather than a sparse page.
# A register page with three recognised words is not a page we can check figures
# against, so it is better handled as Mode C.
MIN_USEFUL_OCR_CHARS = 40

# One page per request.
#
# Batching several pages together seemed sensible — a worker's row can continue
# across a page break, so keeping neighbouring pages in one call preserves that
# context. In practice the trade goes the other way. A single register page of
# twenty-four rows is roughly eight thousand tokens of JSON; two pages exceeded the
# completion limit and the model's reply was cut off mid-object. A truncated JSON
# object is unrecoverable, so the whole batch yielded nothing: a two-page wage
# register produced zero rows and ten violations went undetected.
#
# Losing a little cross-page context costs a few rows of accuracy. Losing the reply
# costs the entire document.
PAGES_PER_REQUEST = 1

# Generous ceiling. A dense register page with twenty-five fields per row needs far
# more than a conversational reply, and the failure mode when this is too low is
# total loss of the page rather than a graceful truncation.
EXTRACTION_MAX_TOKENS = 32_000

# Document types whose data is structured text and must never go near a model.
TEXT_PARSED_TYPES = frozenset({DocumentType.EPF_ECR})

#: Document types whose extraction schema follows an officially prescribed form.
#: Everything else is INFERRED, built from what the Act requires plus the layouts
#: that actually turn up. Recorded per document so a finding can say which.
PRESCRIBED_TYPES = frozenset(
    {
        DocumentType.EPF_ECR,
        DocumentType.ESIC_CHALLAN,
    }
)


# ------------------------------------------------------------------- inputs
@dataclass
class PageInput:
    """Everything known about one page before extraction runs.

    Up to three independent readings of the same page are carried here, and all of
    them are used:

    * ``native_text`` / ``native_tokens`` — the PDF's own text layer. Exact, free,
      and it carries word coordinates, so a digitally generated register yields
      cell-level evidence without OCR being involved at all.
    * ``ocr_text`` / ``ocr_tokens`` — recognition over the rendered page. The only
      source available for a scan or a photograph.
    * ``image`` — the page itself, given to the model so it can see what the other
      two got wrong.

    An earlier version short-circuited to the text layer alone whenever one
    existed, on the reasoning that exact text cannot be improved on. That was
    wrong in an important way: it meant the model never saw the page, so a column
    read in the wrong order had nothing to contradict it, and the cross-check the
    whole design rests on never ran.
    """

    page_number: int
    native_text: str | None = None
    native_tokens: list[dict] = field(default_factory=list)
    ocr_text: str | None = None
    ocr_markdown: str | None = None
    ocr_tokens: list[dict] = field(default_factory=list)
    image: bytes | None = None
    ocr_failed_reason: str | None = None

    @property
    def has_native_text(self) -> bool:
        return bool(
            self.native_text and len(self.native_text.strip()) >= MIN_USEFUL_OCR_CHARS
        )

    @property
    def has_useful_ocr(self) -> bool:
        return bool(self.ocr_text and len(self.ocr_text.strip()) >= MIN_USEFUL_OCR_CHARS)

    @property
    def tokens(self) -> list[dict]:
        """Every positioned word available for this page, text layer first.

        Text-layer words lead because they are authored characters rather than a
        recognition guess, so a value matched against them is certain. Tracing
        walks the list in order and stops at the first match.
        """
        return [*self.native_tokens, *self.ocr_tokens]

    @property
    def has_coordinates(self) -> bool:
        return bool(self.native_tokens or self.ocr_tokens)

    @property
    def mode(self) -> ExtractionMode:
        """What this page's evidence quality actually is.

        NATIVE_PDF is now reserved for the case where there genuinely is nothing
        else — a plain text file, or a page that could not be rendered. A page with
        both a text layer and a rendered image is reported as OCR_PLUS_VISION,
        because that is what happened: two sources were compared.
        """
        if self.image is None:
            return ExtractionMode.NATIVE_PDF
        if self.has_useful_ocr or self.native_tokens:
            return ExtractionMode.OCR_PLUS_VISION
        return ExtractionMode.VISION_ONLY

    def text_blocks(self) -> list[tuple[str, str]]:
        """Labelled text readings to put in front of the model, best first.

        Both readings are shown when both exist, and labelled so the model knows
        which is authored text and which is recognition. Where they disagree, that
        disagreement is itself the signal — it marks the cells worth looking at on
        the image.
        """
        blocks: list[tuple[str, str]] = []

        if self.has_native_text:
            blocks.append(("Text layer (exact, from the PDF itself)", self.native_text or ""))

        if self.ocr_markdown and len(self.ocr_markdown.strip()) >= MIN_USEFUL_OCR_CHARS:
            blocks.append(("OCR table reading (may contain errors)", self.ocr_markdown))
        elif self.has_useful_ocr:
            blocks.append(("OCR text (may contain errors)", self.ocr_text or ""))

        return blocks

    @property
    def best_text(self) -> str:
        """A single text reading, for callers that need only one — e.g. binding."""
        blocks = self.text_blocks()
        return blocks[0][1] if blocks else ""


# ------------------------------------------------------------------- outputs
@dataclass
class FieldProvenance:
    """Where one field's value came from, and whether it can be trusted."""

    page: int | None = None
    bbox: list[float] | None = None
    agreement: str = Agreement.MODEL_ONLY.value
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"agreement": self.agreement}
        if self.page is not None:
            out["page"] = self.page
        if self.bbox is not None:
            out["bbox"] = self.bbox
        if self.note:
            out["note"] = self.note
        return out


@dataclass
class Record:
    """One extracted row, its values and its per-field provenance."""

    kind: str
    values: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, dict] = field(default_factory=dict)
    page: int | None = None
    review_reasons: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)

    def lowest_confidence(self) -> float:
        """Crude confidence: the share of fields traced to the page.

        Reported on findings so an inspector can see that a finding rests on a
        clean digital read rather than a marginal scan.
        """
        if not self.provenance:
            return 0.0
        trusted = sum(
            1
            for p in self.provenance.values()
            if p.get("agreement") in {Agreement.AGREED.value, Agreement.OCR_ONLY.value}
        )
        return round(trusted / len(self.provenance), 3)


@dataclass
class Header:
    """Identifying fields common to every document type."""

    establishment_name: str | None = None
    lin: str | None = None
    registration_number: str | None = None
    address: str | None = None
    state: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    wage_period_basis: str | None = None

    @classmethod
    def from_payload(cls, payload: dict | None) -> Header:
        data = payload or {}
        return cls(
            establishment_name=_clean_text(data.get("establishment_name")),
            lin=_clean_text(data.get("lin")),
            registration_number=_clean_text(data.get("registration_number")),
            address=_clean_text(data.get("address")),
            state=_clean_text(data.get("state")),
            period_start=_parse_date(data.get("period_start")),
            period_end=_parse_date(data.get("period_end")),
            wage_period_basis=_clean_text(data.get("wage_period_basis")),
        )

    def merge(self, other: Header) -> None:
        """Fill blanks from a later batch. First non-empty answer wins.

        Later pages of the same document should not overwrite a header read
        cleanly from page one; a continuation sheet often has an abbreviated or
        missing header.
        """
        for name in (
            "establishment_name",
            "lin",
            "registration_number",
            "address",
            "state",
            "period_start",
            "period_end",
            "wage_period_basis",
        ):
            if getattr(self, name) is None:
                setattr(self, name, getattr(other, name))


@dataclass
class Classification:
    doc_type: DocumentType = DocumentType.UNKNOWN
    confidence: float = 0.0
    reasoning: str | None = None
    header: Header = field(default_factory=Header)
    looks_like_multiple_documents: bool = False
    contains_worker_identifiers: bool = False

    @property
    def is_confident(self) -> bool:
        """Threshold for acting on a classification without a human.

        0.7 rather than something higher because the cost of a wrong guess is
        bounded: an unexpected schema yields empty rows, which surfaces as a
        review flag rather than as silently wrong data.
        """
        return self.doc_type is not DocumentType.UNKNOWN and self.confidence >= 0.7


@dataclass
class ExtractionResult:
    """Everything read from one document."""

    doc_type: DocumentType = DocumentType.UNKNOWN
    doc_type_confidence: float = 0.0
    schema_source: SchemaSource = SchemaSource.INFERRED
    mode: ExtractionMode = ExtractionMode.VISION_ONLY
    header: Header = field(default_factory=Header)

    wage_rows: list[Record] = field(default_factory=list)
    employee_rows: list[Record] = field(default_factory=list)
    attendance_rows: list[Record] = field(default_factory=list)
    contribution_rows: list[Record] = field(default_factory=list)
    incident_rows: list[Record] = field(default_factory=list)
    registration_records: list[Record] = field(default_factory=list)
    prose_facts: list[Record] = field(default_factory=list)

    scheme: str | None = None
    challan_number: str | None = None
    deposited_on: date | None = None
    printed_totals: dict[str, Any] = field(default_factory=dict)
    column_mapping: list[dict] = field(default_factory=list)

    review_reasons: list[str] = field(default_factory=list)
    unreadable_regions: list[dict] = field(default_factory=list)
    corrections: list[dict] = field(default_factory=list)
    redaction_candidates: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    cost_usd: float = 0.0
    llm_calls: int = 0

    @property
    def all_records(self) -> list[Record]:
        return [
            *self.wage_rows,
            *self.employee_rows,
            *self.attendance_rows,
            *self.contribution_rows,
            *self.incident_rows,
            *self.registration_records,
            *self.prose_facts,
        ]

    @property
    def row_count(self) -> int:
        return len(self.all_records)

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons) or any(r.needs_review for r in self.all_records)

    def add_review(self, reason: str) -> None:
        if reason not in self.review_reasons:
            self.review_reasons.append(reason)


# ------------------------------------------------------------------- prompts
CLASSIFY_SYSTEM = """\
You are reading a document submitted by an Indian employer for a labour \
compliance inspection under the four Labour Codes.

Your only job here is to identify what the document is and which establishment \
and period it covers. Do not transcribe its contents.

Rules you must follow:
- Decide from what is visibly printed. Do not infer a document type from what \
you would expect an employer to submit.
- If it does not clearly match one of the listed types, answer UNKNOWN. An \
honest UNKNOWN routes the file to a human; a confident wrong answer sends it \
down the wrong extraction path and produces plausible nonsense.
- Set confidence honestly. Below 0.7 the document goes to a human, which is the \
correct outcome when you are unsure.
- Read the establishment name and period from the document's own header, not \
from any file name.
"""

EXTRACT_SYSTEM = """\
You are transcribing an Indian statutory labour register for a compliance \
inspection. The figures you return will be compared against the Code on Wages \
2019, the Industrial Relations Code 2020, the Code on Social Security 2020 and \
the Occupational Safety, Health and Working Conditions Code 2020, and may be put \
to an employer as evidence of underpayment.

You are given, for each page, the OCR text and the page image. Use both. The OCR \
text is machine-generated and contains errors; the image is the truth.

Absolute rules:
1. Transcribe only what is printed. Never compute, never complete a pattern, \
never fill a blank cell with a figure that would look reasonable. A blank cell \
is null, and a missing entry is exactly what an inspection needs to find.
2. Every figure you return will be searched for in the OCR tokens of the page \
you attribute it to. If it is not found and you have not listed it as a \
correction, the whole row is held for human review. So: when the image \
contradicts the OCR text, trust the image AND record it in "corrections" with \
the OCR reading, your reading, and why.
3. If a region is illegible, list it in "unreadable_regions". Do not guess at \
smudged or overwritten digits.
4. Amounts are plain rupees as digit strings, no symbols and no thousands \
separators: "15250.50". Dates are YYYY-MM-DD. Where a register shows only a \
month, use its first day.
5. Names are transcribed exactly as printed, including initials, honorifics and \
patronymics. Do not normalise, expand or correct spelling: matching the same \
person across documents is done later and needs the original spelling.
6. Attribute every row to the page number it was actually read from.
7. Transcribe every row on every page given to you, in printed order. Do not \
skip rows that look like duplicates and do not summarise.

COLUMN ALIGNMENT — read this before you start.

Wide registers run to eighteen or more columns and losing your place by one \
column is the single most damaging error you can make. It does not look like an \
error: every figure is real and the row reads plausibly. But if you read the \
deductions column as net pay and net pay as deductions, a worker whose wages were \
cut by fifty-five per cent appears to have been cut by forty-five, which is inside \
the legal limit, and a real underpayment disappears.

So work column by column, not row by row:

- Read the printed headings first and write down what each one maps to. Record \
that in "column_mapping" for every heading, including ones you ignore.
- Count the columns. Then count the values in a row. If they do not agree, some \
cells are blank and you must work out which — do not shuffle values leftward to \
fill the gap.
- A dash, a hyphen or an empty cell is null. It is not the next column's value.
- Before you finish each row, check it against itself: gross should equal basic \
plus dearness allowance plus other allowances, and net paid should equal gross \
plus overtime less total deductions. If either does not hold, you have almost \
certainly misaligned a column. Go back to the image and look again.
- Total deductions is usually printed to the LEFT of net paid, and net paid is \
almost always the smaller of the two. If the value you have called "net paid" is \
smaller than the one you have called "deductions", check whether you have swapped \
them.

Getting the alignment right matters more than reading every optional column.

TOTALS AND SUMMARY LINES ARE NOT WORKERS.

Registers print a total row at the foot of the table, and sometimes a carried-\
forward or sub-total line mid-page. These are sums, not people. Never transcribe \
one as a row. You can recognise them: no worker name, or the word TOTAL, GRAND \
TOTAL, SUB-TOTAL or C/F in the name column, and figures far larger than any \
individual's. Put those figures in "printed_totals" instead, which exists for \
exactly this purpose.

This is not a cosmetic error. A totals line transcribed as a worker adds a person \
who does not exist, doubles the establishment's wage bill, and makes the headcount \
disagree with every other document — which is then reported as the employer \
concealing workers.
"""

PROSE_SYSTEM = """\
You are reading a prose document submitted for an Indian labour compliance \
inspection: an appointment letter, standing orders, a committee record, a \
welfare record or an annual return.

You will be asked specific questions. For each one:
- Answer only from what the document states. "Not stated" is a valid and often \
correct answer, and is far more useful than an inferred one, because the absence \
of a required term is itself the finding.
- Quote the exact sentence or clause that supports your answer. The quotation is \
what makes your answer checkable; a paraphrase is not.
- Where a question asks for a number, give the number the document states.
- Set confidence honestly.
"""


# --------------------------------------------------------------- the extractor
class DocumentExtractor:
    """Turns pages into canonical records, with provenance and safety checks."""

    def __init__(self, client: LlmClient) -> None:
        self._client = client

    # ------------------------------------------------------------ classify
    async def classify(
        self, pages: list[PageInput], budget: BudgetTracker
    ) -> Classification:
        """Identify the document from its first few pages.

        Only the first three pages are sent. A document's identity is on its
        first page in every real case, and paying to classify page 40 of a muster
        roll is waste.
        """
        sample = pages[:3]
        if not sample:
            return Classification()

        parts = _build_parts(sample, instruction=(
            "Identify this document and read its header. Do not transcribe rows."
        ))

        try:
            response = await self._client.complete(
                system=CLASSIFY_SYSTEM,
                parts=parts,
                budget=budget,
                json_schema=CLASSIFICATION_SCHEMA,
                schema_name="classification",
                max_tokens=1200,
            )
        except (LlmError, SchemaViolation) as exc:
            logger.warning("classification failed", extra={"error": str(exc)})
            return Classification(reasoning=f"classification failed: {exc}")

        payload = response.parsed or {}
        raw_type = str(payload.get("doc_type") or DocumentType.UNKNOWN.value)
        try:
            doc_type = DocumentType(raw_type)
        except ValueError:
            doc_type = DocumentType.UNKNOWN

        return Classification(
            doc_type=doc_type,
            confidence=float(payload.get("confidence") or 0.0),
            reasoning=_clean_text(payload.get("reasoning")),
            header=Header.from_payload(payload.get("header")),
            looks_like_multiple_documents=bool(
                payload.get("looks_like_multiple_documents")
            ),
            contains_worker_identifiers=bool(payload.get("contains_worker_identifiers")),
        )

    # ------------------------------------------------------------- extract
    async def extract(
        self,
        *,
        doc_type: DocumentType,
        pages: list[PageInput],
        budget: BudgetTracker,
    ) -> ExtractionResult:
        """Read every page of a document of a known type."""
        result = ExtractionResult(
            doc_type=doc_type,
            schema_source=(
                SchemaSource.PRESCRIBED
                if doc_type in PRESCRIBED_TYPES
                else SchemaSource.INFERRED
            ),
            mode=_document_mode(pages),
        )

        schema = SCHEMA_BY_DOC_TYPE.get(doc_type)
        if schema is None:
            result.add_review(
                f"no extraction schema is defined for {doc_type.value}; the "
                "document was stored but nothing was read from it"
            )
            return result

        questions = prose_questions_for(doc_type)
        is_prose = bool(questions)

        for batch in _batch_pages(pages, PAGES_PER_REQUEST):
            instruction = (
                _prose_instruction(questions)
                if is_prose
                else _table_instruction(doc_type)
            )
            parts = _build_parts(batch, instruction=instruction)

            try:
                response = await self._client.complete(
                    system=PROSE_SYSTEM if is_prose else EXTRACT_SYSTEM,
                    parts=parts,
                    budget=budget,
                    json_schema=schema,
                    schema_name=f"extract_{doc_type.value.lower()}",
                    max_tokens=EXTRACTION_MAX_TOKENS,
                )
            except BudgetExceeded as exc:
                result.add_review(f"stopped early: {exc}")
                break
            except (LlmError, SchemaViolation) as exc:
                first, last = batch[0].page_number, batch[-1].page_number
                result.add_review(f"pages {first}-{last} could not be read: {exc}")
                logger.warning(
                    "extraction batch failed",
                    extra={"pages": f"{first}-{last}", "error": str(exc)},
                )
                continue

            self._absorb(result, response.parsed or {}, batch, doc_type)

        result.cost_usd = budget.spent_usd
        result.llm_calls = budget.calls
        _finalise(result, pages)
        return result

    # ------------------------------------------------------------- internals
    def _absorb(
        self,
        result: ExtractionResult,
        payload: dict,
        batch: list[PageInput],
        doc_type: DocumentType,
    ) -> None:
        """Fold one model response into the accumulating result."""
        result.header.merge(Header.from_payload(payload.get("header")))

        corrections = list(payload.get("corrections") or [])
        result.corrections.extend(corrections)
        result.unreadable_regions.extend(payload.get("unreadable_regions") or [])
        if note := _clean_text(payload.get("notes")):
            result.notes.append(note)

        correction_index = verify.build_correction_index(corrections)
        # Merged, not OCR-only: a value is traceable if it appears in either the
        # text layer or the OCR output, and the text layer is the stronger match.
        tokens_by_page = {p.page_number: p.tokens for p in batch}
        modes_by_page = {p.page_number: p.mode for p in batch}

        context = _RowContext(
            tokens_by_page=tokens_by_page,
            modes_by_page=modes_by_page,
            corrections=correction_index,
            default_page=batch[0].page_number,
        )


        if doc_type in {
            DocumentType.WAGE_REGISTER,
            DocumentType.WAGE_SLIP,
            DocumentType.OVERTIME_REGISTER,
            DocumentType.DEDUCTION_REGISTER,
        }:
            result.column_mapping.extend(payload.get("column_mapping") or [])
            _merge_totals(result, payload.get("printed_totals"))
            for raw in payload.get("rows") or []:
                result.wage_rows.append(_wage_record(raw, context))

        elif doc_type is DocumentType.EMPLOYEE_REGISTER:
            _merge_totals(result, payload.get("printed_totals"))
            for raw in payload.get("rows") or []:
                result.employee_rows.append(_employee_record(raw, context))

        elif doc_type in {DocumentType.MUSTER_ROLL, DocumentType.LEAVE_REGISTER}:
            for raw in payload.get("rows") or []:
                result.attendance_rows.append(_attendance_record(raw, context))

        elif doc_type in {DocumentType.EPF_ECR, DocumentType.ESIC_CHALLAN}:
            result.scheme = _clean_text(payload.get("scheme")) or (
                "EPF" if doc_type is DocumentType.EPF_ECR else "ESIC"
            )
            result.challan_number = (
                result.challan_number or _clean_text(payload.get("challan_number"))
            )
            result.deposited_on = result.deposited_on or _parse_date(
                payload.get("deposited_on")
            )
            _merge_totals(result, payload.get("printed_totals"))
            for raw in payload.get("rows") or []:
                result.contribution_rows.append(_contribution_record(raw, context))

        elif doc_type is DocumentType.ACCIDENT_REGISTER:
            for raw in payload.get("rows") or []:
                result.incident_rows.append(_incident_record(raw, context))

        elif doc_type in {
            DocumentType.ESTABLISHMENT_REGISTRATION,
            DocumentType.CONTRACTOR_LICENCE,
            DocumentType.BOCW_CESS_RECEIPT,
        }:
            result.registration_records.append(_registration_record(payload, context))

        else:
            for raw in payload.get("assertions") or []:
                result.prose_facts.append(_prose_record(raw, context))


# --------------------------------------------------------------- row plumbing
@dataclass
class _RowContext:
    """Per-batch lookup tables used while converting rows."""

    tokens_by_page: dict[int, list[dict]]
    modes_by_page: dict[int, ExtractionMode]
    corrections: dict[str, dict]
    default_page: int

    def page_for(self, raw: dict) -> int:
        claimed = raw.get("page")
        if isinstance(claimed, int) and claimed in self.tokens_by_page:
            return claimed
        return self.default_page

    def tokens(self, page: int) -> list[dict]:
        return self.tokens_by_page.get(page) or []

    def mode(self, page: int) -> ExtractionMode:
        return self.modes_by_page.get(page, ExtractionMode.VISION_ONLY)


def _record_value(
    record: Record,
    context: _RowContext,
    page: int,
    *,
    field_name: str,
    raw_value: Any,
    parsed: Any,
    numeric: bool,
) -> None:
    """Store one field with its provenance, tracing it back to the page.

    This is where the invented-number check actually bites. A value that cannot
    be found among the page's OCR tokens, and was not declared as a correction,
    is recorded as unsupported and puts the row into review.
    """
    record.values[field_name] = parsed

    if parsed is None:
        return

    tokens = context.tokens(page)
    if not tokens:
        # Mode C. Nothing to check against, so this is stated plainly rather
        # than dressed up as agreement.
        record.provenance[field_name] = FieldProvenance(
            page=page,
            agreement=Agreement.MODEL_ONLY.value,
            note="page had no OCR tokens; value could not be cross-checked",
        ).as_dict()
        return

    trace: Trace = (
        verify.trace_number(raw_value, tokens, page=page)
        if numeric
        else verify.trace_text(raw_value, tokens, page=page)
    )
    trace = verify.resolve_trace(trace, raw_value, context.corrections)

    record.provenance[field_name] = FieldProvenance(
        page=page,
        bbox=trace.bbox,
        agreement=trace.agreement.value,
        note=trace.note,
    ).as_dict()

    if trace.agreement is Agreement.UNSUPPORTED:
        record.review_reasons.append(
            f"{field_name}={raw_value!r} could not be located on page {page}"
        )


def _wage_record(raw: dict, context: _RowContext) -> Record:
    page = context.page_for(raw)
    record = Record(kind="wage_line", page=page)

    def money(field_name: str, source: str) -> None:
        value = raw.get(source)
        _record_value(
            record,
            context,
            page,
            field_name=field_name,
            raw_value=value,
            parsed=verify.parse_money_to_paise(value),
            numeric=True,
        )

    def number(field_name: str, source: str) -> None:
        value = raw.get(source)
        _record_value(
            record,
            context,
            page,
            field_name=field_name,
            raw_value=value,
            parsed=_parse_number(value),
            numeric=True,
        )

    def text(field_name: str, source: str, *, trace: bool = True) -> None:
        value = _clean_text(raw.get(source))
        if trace:
            _record_value(
                record,
                context,
                page,
                field_name=field_name,
                raw_value=value,
                parsed=value,
                numeric=False,
            )
        else:
            record.values[field_name] = value

    text("worker_name_as_printed", "worker_name")
    text("father_name", "father_or_husband_name", trace=False)
    text("employee_code", "employee_code", trace=False)
    text("uan", "uan", trace=False)
    text("designation", "designation", trace=False)
    text("gender", "gender", trace=False)

    record.values["row_number"] = _parse_int(raw.get("row_number"))
    record.values["skill_category"] = _parse_skill(raw.get("skill_category"))

    number("days_paid", "days_paid")
    number("days_present", "days_present")
    number("normal_hours_per_day", "normal_hours_per_day")
    number("overtime_hours", "overtime_hours")

    money("basic_paise", "basic")
    money("da_paise", "dearness_allowance")
    money("other_allowances_paise", "other_allowances")
    money("gross_paise", "gross")
    money("overtime_paise", "overtime_amount")
    money("overtime_rate_paise", "overtime_rate")
    money("pf_deduction_paise", "pf_deduction")
    money("esi_deduction_paise", "esi_deduction")
    money("advance_recovery_paise", "advance_recovery")
    money("deductions_paise", "total_deductions")
    money("net_paid_paise", "net_paid")

    record.values["paid_on"] = _parse_date(raw.get("paid_on"))
    record.values["date_of_joining"] = _parse_date(raw.get("date_of_joining"))
    record.values["date_of_exit"] = _parse_date(raw.get("date_of_exit"))

    record.review_reasons.extend(verify.check_wage_arithmetic(record.values))
    record.review_reasons.extend(verify.check_identifier_formats(record.values))
    return record


def _employee_record(raw: dict, context: _RowContext) -> Record:
    page = context.page_for(raw)
    record = Record(kind="employee", page=page)

    name = _clean_text(raw.get("worker_name"))
    _record_value(
        record,
        context,
        page,
        field_name="worker_name_as_printed",
        raw_value=name,
        parsed=name,
        numeric=False,
    )

    record.values.update(
        {
            "row_number": _parse_int(raw.get("row_number")),
            "father_name": _clean_text(raw.get("father_or_husband_name")),
            "employee_code": _clean_text(raw.get("employee_code")),
            "uan": _clean_text(raw.get("uan")),
            "esic_number": _clean_text(raw.get("esic_number")),
            "designation": _clean_text(raw.get("designation")),
            "skill_category": _parse_skill(raw.get("skill_category")),
            "gender": _clean_text(raw.get("gender")),
            "date_of_birth": _parse_date(raw.get("date_of_birth")),
            "date_of_joining": _parse_date(raw.get("date_of_joining")),
            "date_of_exit": _parse_date(raw.get("date_of_exit")),
            "is_contract_worker": bool(raw.get("is_contract_worker")),
            "contractor_name": _clean_text(raw.get("contractor_name")),
        }
    )

    record.review_reasons.extend(verify.check_identifier_formats(record.values))
    return record


def _attendance_record(raw: dict, context: _RowContext) -> Record:
    page = context.page_for(raw)
    record = Record(kind="attendance", page=page)

    name = _clean_text(raw.get("worker_name"))
    _record_value(
        record,
        context,
        page,
        field_name="worker_name_as_printed",
        raw_value=name,
        parsed=name,
        numeric=False,
    )

    for field_name, source in (
        ("days_present", "days_present"),
        ("days_absent", "days_absent"),
        ("total_hours", "total_hours"),
        ("overtime_hours", "overtime_hours"),
        ("max_daily_hours", "max_daily_hours"),
        ("max_weekly_hours", "max_weekly_hours"),
    ):
        value = raw.get(source)
        _record_value(
            record,
            context,
            page,
            field_name=field_name,
            raw_value=value,
            parsed=_parse_number(value),
            numeric=True,
        )

    record.values["employee_code"] = _clean_text(raw.get("employee_code"))
    record.values["weekly_offs_given"] = _parse_int(raw.get("weekly_offs_given"))
    record.values["daily_marks"] = _clean_text(raw.get("daily_marks"))

    # Prefer a run computed from the day-by-day marks over the model's own count.
    # Counting a long unbroken run across a wide grid is exactly the kind of
    # thing a model gets slightly wrong, and the marks make it deterministic.
    marks = record.values["daily_marks"]
    derived = _longest_run_from_marks(marks) if marks else None
    claimed = _parse_int(raw.get("longest_consecutive_days"))
    record.values["longest_consecutive_days"] = (
        derived if derived is not None else claimed
    )
    if derived is not None and claimed is not None and derived != claimed:
        record.provenance["longest_consecutive_days"] = FieldProvenance(
            page=page,
            agreement=Agreement.AGREED.value,
            note=(
                f"recomputed from the attendance marks as {derived}; the model "
                f"reported {claimed}"
            ),
        ).as_dict()

    record.review_reasons.extend(verify.check_attendance_arithmetic(record.values))
    return record


def _contribution_record(raw: dict, context: _RowContext) -> Record:
    page = context.page_for(raw)
    record = Record(kind="contribution", page=page)

    name = _clean_text(raw.get("worker_name"))
    _record_value(
        record,
        context,
        page,
        field_name="worker_name_as_printed",
        raw_value=name,
        parsed=name,
        numeric=False,
    )

    for field_name, source in (
        ("wage_base_paise", "wage_base"),
        ("employee_share_paise", "employee_share"),
        ("employer_share_paise", "employer_share"),
    ):
        value = raw.get(source)
        _record_value(
            record,
            context,
            page,
            field_name=field_name,
            raw_value=value,
            parsed=verify.parse_money_to_paise(value),
            numeric=True,
        )

    record.values["uan"] = _clean_text(raw.get("uan"))
    record.values["member_id"] = _clean_text(raw.get("member_id"))
    record.values["ncp_days"] = _parse_number(raw.get("ncp_days"))

    record.review_reasons.extend(verify.check_contribution_arithmetic(record.values))
    record.review_reasons.extend(verify.check_identifier_formats(record.values))
    return record


def _incident_record(raw: dict, context: _RowContext) -> Record:
    page = context.page_for(raw)
    record = Record(kind="incident", page=page)

    occurred = _parse_date(raw.get("occurred_on"))
    notified = _parse_date(raw.get("notified_on"))

    record.values.update(
        {
            "occurred_on": occurred,
            "notified_on": notified,
            "description": _clean_text(raw.get("description")),
            "severity": _clean_text(raw.get("severity")),
            "workers_affected": _parse_int(raw.get("workers_affected")),
            "notification_reference": _clean_text(raw.get("notification_reference")),
        }
    )
    record.provenance["occurred_on"] = FieldProvenance(
        page=page, agreement=context.mode(page).value
    ).as_dict()

    if occurred and notified and notified < occurred:
        record.review_reasons.append(
            f"accident notified on {notified} before it occurred on {occurred}"
        )
    return record


def _registration_record(payload: dict, context: _RowContext) -> Record:
    page = context.default_page
    record = Record(kind="registration", page=page)

    record.values.update(
        {
            "kind": _clean_text(payload.get("kind")) or "ESTABLISHMENT_REGISTRATION",
            "number": _clean_text(payload.get("number")),
            "issuing_authority": _clean_text(payload.get("issuing_authority")),
            "holder_name": _clean_text(payload.get("holder_name")),
            "valid_from": _parse_date(payload.get("valid_from")),
            "valid_to": _parse_date(payload.get("valid_to")),
            "licensed_worker_count": _parse_int(payload.get("licensed_worker_count")),
        }
    )

    number = record.values["number"]
    _record_value(
        record,
        context,
        page,
        field_name="number",
        raw_value=number,
        parsed=number,
        numeric=False,
    )

    if not record.values["number"]:
        record.review_reasons.append("no registration number could be read")

    valid_from = record.values["valid_from"]
    valid_to = record.values["valid_to"]
    if valid_from and valid_to and valid_to < valid_from:
        record.review_reasons.append(
            f"validity ends {valid_to} before it begins {valid_from}"
        )
    return record


def _prose_record(raw: dict, context: _RowContext) -> Record:
    page = context.page_for(raw)
    record = Record(kind="prose", page=page)

    present = bool(raw.get("present"))
    quote = _clean_text(raw.get("quote"))

    record.values.update(
        {
            "key": _clean_text(raw.get("key")),
            "present": present,
            "value_text": _clean_text(raw.get("value")),
            "quote": quote,
            "source_page": page,
            "confidence": _parse_number(raw.get("confidence")),
        }
    )

    # An assertion claiming the document says something, with no quotation to
    # show for it, is exactly the kind of unsupported claim this system exists to
    # avoid presenting to an inspector.
    if present and not quote:
        record.review_reasons.append(
            f"assertion {record.values['key']!r} claims the document states this "
            "but gives no supporting quotation"
        )
    elif present and quote and context.tokens(page):
        trace = verify.trace_text(quote[:60], context.tokens(page), page=page)
        record.provenance["quote"] = FieldProvenance(
            page=page, bbox=trace.bbox, agreement=trace.agreement.value, note=trace.note
        ).as_dict()
        if trace.agreement is Agreement.UNSUPPORTED:
            record.review_reasons.append(
                f"the quotation supporting {record.values['key']!r} was not found "
                f"on page {page}"
            )

    return record


# ------------------------------------------------------------------ assembly
def _build_parts(pages: list[PageInput], *, instruction: str) -> list[ContentPart]:
    """Assemble the multimodal message: instruction, then per page text + image.

    Text precedes its image so the model reads the OCR first and then looks at
    the page, which is the order that produces corrections rather than blind
    agreement with the OCR.
    """
    parts: list[ContentPart] = [text_part(instruction)]

    for page in pages:
        header = f"\n--- PAGE {page.page_number} ---"
        blocks = page.text_blocks()

        if blocks:
            rendered = "\n\n".join(
                f"{label}:\n{body.strip()}" for label, body in blocks if body.strip()
            )
            if len(blocks) > 1:
                rendered += (
                    "\n\nTwo readings of this page are given above. Where they "
                    "disagree, look at the image and record which is right in "
                    "\"corrections\"."
                )
            parts.append(text_part(f"{header}\n{rendered}"))
        else:
            reason = page.ocr_failed_reason or "no text could be recovered"
            parts.append(
                text_part(
                    f"{header}\nNo text is available for this page ({reason}). "
                    "Read it from the image alone and be conservative: report "
                    "anything you cannot read clearly as unreadable rather than "
                    "guessing."
                )
            )

        if page.image:
            parts.append(image_part(page.image))

    return parts


def _table_instruction(doc_type: DocumentType) -> str:
    return (
        f"Transcribe this {doc_type.value.replace('_', ' ').lower()} completely. "
        "Return one entry per printed row, attributed to the page it appears on. "
        "Also record how you interpreted each printed column heading, so a "
        "reviewer can catch a wrong column mapping."
    )


def _prose_instruction(questions: list[tuple[str, str]]) -> str:
    lines = "\n".join(f"- {key}: {text}" for key, text in questions)
    return (
        "Answer each question below about this document. Return one assertion "
        "per question, using the given key, in the same order, with the exact "
        "supporting quotation.\n\n" + lines
    )


def _batch_pages(pages: list[PageInput], size: int) -> list[list[PageInput]]:
    return [pages[i : i + size] for i in range(0, len(pages), size)]


def _document_mode(pages: list[PageInput]) -> ExtractionMode:
    """Document-level mode: the weakest page decides.

    Reporting the best mode would overstate evidence quality for the document as
    a whole, and evidence quality is the thing an inspector needs to judge.
    """
    if not pages:
        return ExtractionMode.VISION_ONLY
    modes = {page.mode for page in pages}
    if ExtractionMode.VISION_ONLY in modes:
        return ExtractionMode.VISION_ONLY
    if ExtractionMode.OCR_PLUS_VISION in modes:
        return ExtractionMode.OCR_PLUS_VISION
    return ExtractionMode.NATIVE_PDF


def _merge_totals(result: ExtractionResult, totals: dict | None) -> None:
    for key, value in (totals or {}).items():
        if value is not None and result.printed_totals.get(key) is None:
            result.printed_totals[key] = value


def _finalise(result: ExtractionResult, pages: list[PageInput]) -> None:
    """Document-level checks that only make sense once every page is in."""
    if result.row_count == 0 and result.doc_type not in {
        DocumentType.ESTABLISHMENT_REGISTRATION,
        DocumentType.CONTRACTOR_LICENCE,
        DocumentType.BOCW_CESS_RECEIPT,
    }:
        result.add_review(
            "nothing was extracted from this document; it may be blank, "
            "illegible, or not the type it was classified as"
        )

    unsupported = sum(
        1
        for record in result.all_records
        for prov in record.provenance.values()
        if prov.get("agreement") == Agreement.UNSUPPORTED.value
    )
    if unsupported:
        result.add_review(
            f"{unsupported} value(s) could not be traced to any text on the page "
            "they were attributed to"
        )

    if result.unreadable_regions:
        result.add_review(
            f"{len(result.unreadable_regions)} region(s) were reported illegible"
        )

    # Compare the register's own printed column total against the sum of the rows
    # we read. This catches a whole page silently dropped, which no per-row check
    # can see.
    printed_gross = verify.parse_money_to_paise(result.printed_totals.get("gross"))
    if printed_gross and result.wage_rows:
        summed = sum(
            row.values.get("gross_paise") or 0
            for row in result.wage_rows
            if row.values.get("gross_paise") is not None
        )
        if summed and abs(summed - printed_gross) > max(100, printed_gross // 100):
            result.add_review(
                f"the register prints a gross total of {printed_gross / 100:.2f} "
                f"but the rows read sum to {summed / 100:.2f}, so rows may be "
                "missing or misread"
            )

    printed_count = result.printed_totals.get("worker_count")
    if isinstance(printed_count, int) and printed_count > 0:
        read_count = len(result.wage_rows) or len(result.employee_rows)
        if read_count and read_count != printed_count:
            result.add_review(
                f"the document states {printed_count} workers but {read_count} "
                "rows were read"
            )

    # Aadhaar detection over whatever text we have, so the stored copy can be
    # redacted and access to it logged.
    for page in pages:
        text = page.ocr_text or page.native_text or ""
        for masked in verify.detect_aadhaar(text):
            if masked not in result.redaction_candidates:
                result.redaction_candidates.append(masked)


# -------------------------------------------------------------------- parsing
def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "-", "--"}:
        return None
    return " ".join(text.split())


def _parse_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = _clean_text(value)
    if text is None:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    number = _parse_number(value)
    return int(round(number)) if number is not None else None


def _parse_date(value: Any) -> date | None:
    """Parse a date, accepting the formats Indian registers actually use.

    ISO first because that is what the schema asks for. The rest are accepted
    because a model handed ``05-04-2026`` on a form will sometimes pass it
    through, and rejecting it would lose a date that is perfectly legible.
    Ambiguous day/month order resolves to day-first, the Indian convention.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    text = _clean_text(value)
    if text is None:
        return None

    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %Y",
        "%b %Y",
        "%Y-%m",
        "%m/%Y",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.date()

    return None


def _parse_skill(value: Any) -> SkillCategory | None:
    text = _clean_text(value)
    if text is None:
        return None
    try:
        return SkillCategory(text.upper().replace(" ", "_").replace("-", "_"))
    except ValueError:
        return None


def _longest_run_from_marks(marks: str) -> int | None:
    """Longest unbroken run of worked days in an attendance mark string.

    Anything that is not an absence or a weekly off counts as worked, so half
    days and holidays-worked are included. Returns None for a string with no
    recognisable marks rather than a misleading zero.
    """
    if not marks:
        return None

    breaks = {"a", "w", "h", "l", "o", "-", "x", " ", ".", "/"}
    longest = current = 0
    recognised = 0

    for char in marks.lower():
        if char in breaks:
            recognised += 1
            current = 0
            continue
        if char.isalnum():
            recognised += 1
            current += 1
            longest = max(longest, current)

    return longest if recognised >= 3 else None
