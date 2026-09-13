"""Model-driven review of findings and open-ended discrepancy detection.

The rule packs encode what the statute says. This module asks the different
question: what is actually wrong with these documents.

Both are needed. A rule list is finite and the ways an employer's records can be
inconsistent are not, so a system built only on rules finds only what somebody
thought to look for. Equally, a model cannot be allowed to declare a
non-compliance: that is a legal conclusion, it needs a statutory citation and a
test that gives the same answer twice, and a model gives neither.

So the division is strict:

* **Rules decide compliance.** Deterministic, cited, reproducible.
* **The analyst reviews and observes.** It can annotate a rule finding as a
  likely false positive, explain it in plain language, and raise discrepancies,
  missing fields and anomalies the rules never anticipated. It cannot raise a
  non-compliance and its observations never move a compliance score.

That last constraint is enforin the schema and again here when the results are
persisted, because an advisory signal that quietly affected an employer's score
would be indefensible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import FindingKind, LabourCode, Severity
from app.services.doc_schemas import ANALYST_SCHEMA, CROSS_DOCUMENT_SCHEMA
from app.services.llm import BudgetTracker, LlmClient, LlmError, text_part

logger = logging.getLogger(__name__)

# Findings sent for review in one call. Enough context to reason across them,
# small enough that the response is not truncated.
ASSESSMENT_BATCH = 12

# Observations below this confidence are dropped. An inspector's time is the
# scarcest resource in the system and a speculative lead wastes it.
MIN_OBSERVATION_CONFIDENCE = 0.55

# Characters of document text given to the analyst per document. Registers can be
# enormous; this keeps the prompt affordable while still showing real figures.
TEXT_BUDGET_PER_DOC = 6000

ANALYST_SYSTEM = """\
You are a labour inspection analyst reviewing an Indian employer's compliance \
records under the Code on Wages 2019, the Industrial Relations Code 2020, the \
Code on Social Security 2020 and the Occupational Safety, Health and Working \
Conditions Code 2020.

A deterministic rule engine has already checked the documents against the \
statutory thresholds and produced the findings you are given. You have two jobs.

First, review those findings against the evidence. Most will be correct. Say so. \
Mark one as a possible false positive only when you can point to something \
concrete: a figure that was misread, a column that was mapped to the wrong \
field, an exemption stated on the document itself, a period mismatch. You are \
not being asked whether the law is fair or whether the employer meant well.

Part of that review is severity. Each rule declares one severity for its entire \
class of breach, so it cannot tell a deduction that crossed the cap by one per \
cent for a single worker from one at ninety per cent across the whole workforce \
three months running. You can see the difference. Where the documents show a \
breach is markedly graver or markedly slighter than its class, say so through \
severity_opinion and give the specific reason. It moves the recorded severity by \
one step and affects the score, so leave it null when the breach is simply \
typical of its kind — which is most of the time.

Second, and this is where you add what the rules cannot: tell the inspector what \
else is wrong. The rules only check what someone thought to encode. You are \
reading the actual documents. Look for:

- figures that are internally consistent but not credible for the work described
- patterns too regular to be real: identical amounts across many workers, \
attendance that never varies, round numbers everywhere
- documents that agree with each other but not with the workforce they describe
- entries that appear inserted, altered, or written in a different hand
- workers who appear and disappear between filings without joining or leaving dates
- registers whose totals do not reconcile with their own rows
- anything a competent inspector would notice on reading these papers

Be specific and quantitative. "Data quality issues" helps nobody. "Eleven of \
forty workers show gross pay of exactly 15,000 with different day counts, which \
cannot arise from a daily rate" is a lead an inspector can act on.

Report nothing rather than padding the list. And say plainly when the records \
look sound: an establishment with clean records deserves to be told so, and a \
system that always finds something will be ignored.

You may not declare a non-compliance. That needs a statutory citation and a \
reproducible test, which is what the rule engine is for. Your observations are \
advisory and are presented to inspectors as such.
"""

CROSS_DOCUMENT_SYSTEM = """\
You are comparing several documents an Indian employer submitted for the same \
establishment and the same period: registers, returns, challans and records.

Real non-compliance is usually invisible in any single document. Each one is \
internally consistent and looks correct. The breach only appears in the \
comparison — a worker in the wage register who is missing from the provident \
fund filing, a wage base in the challan lower than the basic pay in the \
register, attendance showing overtime that the wage register never paid, a \
headcount in the annual return that no register supports.

Find those contradictions. For each one, name the documents that disagree and \
quote the conflicting figures from each. An inspector must be able to verify it \
from the documents without asking you anything.

Say what reconciles cleanly too. An employer whose records agree deserves that \
recorded.
"""


# ------------------------------------------------------------------- results
@dataclass
class Assessment:
    """The analyst's view of one rule finding."""

    finding_id: str
    verdict: str = "sound"
    reason: str | None = None
    plain_explanation: str | None = None
    severity_opinion: Severity | None = None

    @property
    def is_possible_false_positive(self) -> bool:
        return self.verdict == "possible_false_positive"


@dataclass
class Observation:
    """Something the analyst noticed that no rule raised."""

    kind: FindingKind
    severity: Severity
    title: str
    detail: str
    code: LabourCode | None = None
    evidence_pages: list[int] = field(default_factory=list)
    affected_workers: list[str] = field(default_factory=list)
    suggested_check: str | None = None
    confidence: float = 0.0
    documents_involved: list[str] = field(default_factory=list)


@dataclass
class AnalystReport:
    assessments: list[Assessment] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    overall_assessment: str | None = None
    records_quality: str = "adequate"
    consistency_notes: str | None = None
    failed_reasons: list[str] = field(default_factory=list)

    def assessment_for(self, finding_id: str) -> Assessment | None:
        for assessment in self.assessments:
            if assessment.finding_id == finding_id:
                return assessment
        return None


# -------------------------------------------------------------------- inputs
@dataclass
class FindingBrief:
    """A rule finding, flattened for the analyst."""

    finding_id: str
    rule_id: str
    title: str
    citation: str
    message: str
    kind: str
    severity: str
    observed: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    awaiting_notification: bool = False
    """True when the Act left this rule's number to a notification not obtained."""

    def render(self) -> str:
        lines = [
            f"finding_id: {self.finding_id}",
            f"rule: {self.rule_id}  ({self.kind}, severity {self.severity})",
            f"citation: {self.citation}",
            f"title: {self.title}",
            f"message: {self.message}",
        ]
        if self.observed:
            lines.append(f"observed: {_render_mapping(self.observed)}")
        if self.expected:
            lines.append(f"expected: {_render_mapping(self.expected)}")
        if self.evidence:
            lines.append("evidence: " + "; ".join(self.evidence[:6]))
        if self.awaiting_notification:
            lines.append(
                "note: the Act leaves this rule's operative number to the "
                "appropriate Government and that notification has not been "
                "obtained, so the figure compared against came from a secondary "
                "source; treat it with extra caution"
            )
        return "\n".join(lines)


@dataclass
class DocumentBrief:
    """A document's identity and content, flattened for the analyst."""

    document_id: str
    doc_type: str
    filename: str
    period: str | None = None
    extraction_mode: str | None = None
    row_summary: str | None = None
    text: str | None = None
    review_reasons: list[str] = field(default_factory=list)

    def render(self, *, text_budget: int = TEXT_BUDGET_PER_DOC) -> str:
        lines = [
            f"document_id: {self.document_id}",
            f"type: {self.doc_type}   file: {self.filename}",
        ]
        if self.period:
            lines.append(f"period: {self.period}")
        if self.extraction_mode:
            lines.append(f"read by: {self.extraction_mode}")
        if self.review_reasons:
            lines.append("flagged during reading: " + "; ".join(self.review_reasons[:5]))
        if self.row_summary:
            lines.append(f"extracted data:\n{self.row_summary}")
        if self.text:
            body = self.text.strip()
            if len(body) > text_budget:
                # Truncate rather than drop: the head of a register carries the
                # header and the first rows, which is where most context lives.
                body = body[:text_budget] + "\n[...truncated...]"
            lines.append(f"document text:\n{body}")
        return "\n".join(lines)


# ------------------------------------------------------------------- analyst
class Analyst:
    def __init__(self, client: LlmClient, budget: BudgetTracker) -> None:
        self._client = client
        self._budget = budget

    async def review(
        self,
        *,
        establishment_summary: str,
        documents: list[DocumentBrief],
        findings: list[FindingBrief],
    ) -> AnalystReport:
        """Review rule findings and look for what the rules missed."""
        report = AnalystReport()

        if not documents:
            report.failed_reasons.append("no documents to review")
            return report

        document_block = "\n\n".join(doc.render() for doc in documents)

        # Batch the findings, but always send the documents: an assessment made
        # without the evidence is worthless, which is the whole point of asking.
        batches = _batch(findings, ASSESSMENT_BATCH) or [[]]

        for position, batch in enumerate(batches):
            finding_block = (
                "\n\n".join(f.render() for f in batch)
                if batch
                else "(the rule engine raised no findings for these documents)"
            )

            # Only the first call is asked for open-ended observations. Repeating
            # the request per batch would produce the same leads several times
            # over and pad the inspector's list with duplicates.
            wants_observations = position == 0
            instruction = (
                "ESTABLISHMENT:\n"
                f"{establishment_summary}\n\n"
                "DOCUMENTS:\n"
                f"{document_block}\n\n"
                "FINDINGS RAISED BY THE RULE ENGINE:\n"
                f"{finding_block}\n\n"
                "Assess every finding above, in order. "
                + (
                    "Then report what else is wrong with these records that the "
                    "rules did not raise, and give your overall assessment."
                    if wants_observations
                    else "Return an empty additional_observations list: another "
                    "pass is covering that."
                )
            )

            try:
                response = await self._client.complete(
                    system=ANALYST_SYSTEM,
                    parts=[text_part(instruction)],
                    budget=self._budget,
                    json_schema=ANALYST_SCHEMA,
                    schema_name="analyst_review",
                    max_tokens=12000,
                )
            except LlmError as exc:
                logger.warning("analyst review failed", extra={"error": str(exc)})
                report.failed_reasons.append(f"review pass failed: {exc}")
                continue

            self._absorb(report, response.parsed or {}, wants_observations)

        return report

    async def compare_documents(
        self,
        *,
        establishment_summary: str,
        documents: list[DocumentBrief],
    ) -> AnalystReport:
        """Look for contradictions between documents for the same period."""
        report = AnalystReport()

        if len(documents) < 2:
            # Nothing to compare. Not a failure: a single document is a normal
            # state, it just cannot contradict anything.
            return report

        instruction = (
            "ESTABLISHMENT:\n"
            f"{establishment_summary}\n\n"
            "DOCUMENTS FOR THE SAME ESTABLISHMENT AND PERIOD:\n"
            + "\n\n".join(doc.render() for doc in documents)
            + "\n\nFind every contradiction between these documents."
        )

        try:
            response = await self._client.complete(
                system=CROSS_DOCUMENT_SYSTEM,
                parts=[text_part(instruction)],
                budget=self._budget,
                json_schema=CROSS_DOCUMENT_SCHEMA,
                schema_name="cross_document_review",
                max_tokens=10000,
            )
        except LlmError as exc:
            logger.warning("cross-document review failed", extra={"error": str(exc)})
            report.failed_reasons.append(f"cross-document pass failed: {exc}")
            return report

        payload = response.parsed or {}
        report.consistency_notes = _clean(payload.get("consistency_notes"))

        for raw in payload.get("contradictions") or []:
            confidence = float(raw.get("confidence") or 0.0)
            if confidence < MIN_OBSERVATION_CONFIDENCE:
                continue
            title = _clean(raw.get("title"))
            detail = _clean(raw.get("detail"))
            if not title or not detail:
                continue
            report.observations.append(
                Observation(
                    # Always a discrepancy: by construction this pass is
                    # comparing documents against each other.
                    kind=FindingKind.DISCREPANCY,
                    severity=_severity(raw.get("severity")) or Severity.MEDIUM,
                    title=title,
                    detail=detail,
                    code=_code(raw.get("code")),
                    affected_workers=_strings(raw.get("affected_workers")),
                    documents_involved=_strings(raw.get("documents_involved")),
                    confidence=round(confidence, 3),
                )
            )

        return report

    # ------------------------------------------------------------- internals
    def _absorb(
        self, report: AnalystReport, payload: dict, wants_observations: bool
    ) -> None:
        for raw in payload.get("rule_assessments") or []:
            finding_id = _clean(raw.get("finding_id"))
            if not finding_id:
                continue
            report.assessments.append(
                Assessment(
                    finding_id=finding_id,
                    verdict=str(raw.get("verdict") or "sound"),
                    reason=_clean(raw.get("reason")),
                    plain_explanation=_clean(raw.get("plain_explanation")),
                    severity_opinion=_severity(raw.get("severity_opinion")),
                )
            )

        if not wants_observations:
            return

        report.overall_assessment = _clean(payload.get("overall_assessment"))
        quality = str(payload.get("records_quality") or "adequate")
        if quality in {"good", "adequate", "poor", "unusable"}:
            report.records_quality = quality

        for raw in payload.get("additional_observations") or []:
            confidence = float(raw.get("confidence") or 0.0)
            if confidence < MIN_OBSERVATION_CONFIDENCE:
                continue

            title = _clean(raw.get("title"))
            detail = _clean(raw.get("detail"))
            if not title or not detail:
                continue

            kind = _kind(raw.get("kind"))
            if kind is None:
                # The schema forbids NON_COMPLIANCE, but never rely on a model
                # honouring an enum. Anything unrecognised becomes an anomaly,
                # which is advisory and unscored.
                kind = FindingKind.ANOMALY

            report.observations.append(
                Observation(
                    kind=kind,
                    severity=_severity(raw.get("severity")) or Severity.LOW,
                    title=title,
                    detail=detail,
                    code=_code(raw.get("code")),
                    evidence_pages=_ints(raw.get("evidence_pages")),
                    affected_workers=_strings(raw.get("affected_workers")),
                    suggested_check=_clean(raw.get("suggested_check")),
                    confidence=round(confidence, 3),
                )
            )


# -------------------------------------------------------------------- helpers
def _batch(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "-"}:
        return None
    return text


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = _clean(item)
        if text:
            out.append(text[:255])
    return out[:50]


def _ints(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, int) and not isinstance(item, bool):
            out.append(item)
    return out[:50]


def _severity(value: Any) -> Severity | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return Severity(text.upper())
    except ValueError:
        return None


def _code(value: Any) -> LabourCode | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return LabourCode(text.upper())
    except ValueError:
        return None


def _kind(value: Any) -> FindingKind | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        kind = FindingKind(text.upper())
    except ValueError:
        return None
    # Hard stop. A model-raised legal conclusion would carry no citation and no
    # reproducible test, and would still show up beside real findings.
    if kind is FindingKind.NON_COMPLIANCE:
        return FindingKind.DISCREPANCY
    return kind


def _render_mapping(mapping: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value!r}" for key, value in mapping.items())
