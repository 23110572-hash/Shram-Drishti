"""Deciding which establishment and which period a document belongs to.

An employer's register header almost never matches the registered name exactly.
It carries a trading name, a unit or plant name, an abbreviation, a different
transliteration, or a group name with the unit in brackets. "Sunrise Textiles
(Unit II), Bhiwandi" and "M/s Sunrise Textile Mills Pvt Ltd" are the same
establishment; "Sunrise Textiles Ltd" and "Sunrise Textile Processors" may not be.

String comparison cannot settle that, so the model does, using the LIN, the
registration numbers and the address as well as the name. The consequence of
getting it wrong is severe in a specific way: a wage register attached to the
wrong employer produces findings against a business that never filed it. So the
model is told plainly that refusing to decide is the better answer when unsure,
and an unbound document waits for a human rather than being attached to a guess.

Period binding is here for the same reason. A header reading "March 2026", "3/26"
or "Wage period: 26.02.2026 to 25.03.2026" all have to become a concrete range,
and the last of those is a real convention that no calendar-month assumption
would survive.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.establishment import Establishment
from app.services.doc_schemas import BINDING_SCHEMA
from app.services.llm import BudgetTracker, LlmClient, LlmError, text_part

logger = logging.getLogger(__name__)

# Below this the document is left unbound for a human to attach. Set high: the
# cost of waiting is a queue item, the cost of being wrong is a finding against
# the wrong employer.
ACCEPT_CONFIDENCE = 0.8

# Establishments offered to the model in one call. An organisation with more than
# this many units is beyond what a single prompt should decide over, and the
# caller narrows by organisation first anyway.
MAX_ESTABLISHMENTS_SHOWN = 40

BINDING_SYSTEM = """\
You decide which of an employer's registered establishments a submitted document \
belongs to, and which period it covers.

Establishment names in Indian labour records vary constantly. A register header \
may use a trading name, a unit or plant name, an abbreviation, a group name, or a \
different transliteration of the same name. Treat the LIN, the registration or \
licence numbers, the ESIC or EPF code and the address as stronger evidence than \
the name, because those are issued identifiers and the name is however the clerk \
wrote it that day.

Be careful with unit numbers. "Unit I" and "Unit II" of the same company are \
different establishments with separate registrations, separate registers and \
separate compliance positions. Do not merge them.

If you cannot tell, answer null. The document will be held for a person to \
attach, which is a minor delay. Attaching a wage register to the wrong employer \
produces findings against a business that never filed it, which is not minor.

For the period: resolve whatever the document states into concrete first and last \
days. A header reading "March 2026" means 1 to 31 March 2026. A header reading \
"26.02.2026 to 25.03.2026" means exactly that — some establishments run wage \
periods across calendar months and you must not round it to a month. If no \
period is stated at all, answer null rather than assuming the current month.
"""


@dataclass
class BindingResult:
    establishment_id: str | None = None
    confidence: float = 0.0
    reason: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    period_basis: str | None = None
    period_reason: str | None = None
    failed_reason: str | None = None

    @property
    def is_bound(self) -> bool:
        return self.establishment_id is not None

    @property
    def has_period(self) -> bool:
        return self.period_start is not None and self.period_end is not None

    @property
    def period_days(self) -> int | None:
        if not self.has_period:
            return None
        assert self.period_start is not None and self.period_end is not None
        return (self.period_end - self.period_start).days + 1


@dataclass
class DocumentHeaderBrief:
    """What the document says about itself."""

    establishment_name: str | None = None
    lin: str | None = None
    registration_number: str | None = None
    address: str | None = None
    state: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    wage_period_basis: str | None = None
    doc_type: str | None = None
    filename: str | None = None
    first_page_text: str | None = None

    def render(self) -> str:
        rows = [
            ("document type", self.doc_type),
            ("file name", self.filename),
            ("establishment name on document", self.establishment_name),
            ("LIN on document", self.lin),
            ("registration or code on document", self.registration_number),
            ("address on document", self.address),
            ("state on document", self.state),
            (
                "period stated on document",
                _range(self.period_start, self.period_end),
            ),
            ("wage period basis stated", self.wage_period_basis),
        ]
        lines = [f"{label}: {value}" for label, value in rows if value]

        if self.first_page_text:
            head = self.first_page_text.strip()[:2500]
            lines.append(f"\ntext of the first page:\n{head}")

        return "\n".join(lines) or "(the document header could not be read)"


class DocumentBinder:
    def __init__(self, client: LlmClient, budget: BudgetTracker) -> None:
        self._client = client
        self._budget = budget

    async def bind(
        self,
        session: Session,
        *,
        organisation_id: str,
        header: DocumentHeaderBrief,
        uploaded_at: date | None = None,
    ) -> BindingResult:
        """Choose the establishment and period for one document.

        Candidates are restricted to the uploading organisation before the model
        sees them. That is an authorisation boundary, not an optimisation: an
        employer must not be able to attach a document to somebody else's
        establishment by naming it in a header.
        """
        candidates = (
            session.execute(
                select(Establishment)
                .where(
                    Establishment.organisation_id == organisation_id,
                    Establishment.is_active.is_(True),
                )
                .order_by(Establishment.name)
                .limit(MAX_ESTABLISHMENTS_SHOWN)
            )
            .scalars()
            .all()
        )

        if not candidates:
            return BindingResult(
                failed_reason=(
                    "this organisation has no active establishments on file, so "
                    "there is nothing to attach the document to"
                )
            )

        # Exactly one establishment: there is no decision to make, and paying a
        # model call to confirm the obvious is waste. The period still needs
        # resolving, so the call is not skipped — only the choice is settled.
        forced = candidates[0].id if len(candidates) == 1 else None

        listing = "\n".join(_describe(e) for e in candidates)
        instruction = (
            "DOCUMENT:\n"
            f"{header.render()}\n\n"
            "REGISTERED ESTABLISHMENTS OF THE SUBMITTING EMPLOYER:\n"
            f"{listing}\n\n"
            + (
                f"Only one establishment is registered, so the document belongs "
                f"to {forced} unless its header clearly contradicts that. "
                if forced
                else "Choose the establishment this document belongs to, or "
                "answer null if you cannot tell. "
            )
            + "Then resolve the period it covers into concrete first and last days."
            + (
                f"\n\nFor context, the document was uploaded on "
                f"{uploaded_at.isoformat()}. Use this only to disambiguate a "
                "year the document states ambiguously, never to invent a period "
                "the document does not state."
                if uploaded_at
                else ""
            )
        )

        try:
            response = await self._client.complete(
                system=BINDING_SYSTEM,
                parts=[text_part(instruction)],
                budget=self._budget,
                json_schema=BINDING_SCHEMA,
                schema_name="document_binding",
                max_tokens=1500,
            )
        except LlmError as exc:
            logger.warning("binding failed", extra={"error": str(exc)})
            return BindingResult(failed_reason=f"binding could not run: {exc}")

        payload = response.parsed or {}
        valid_ids = {e.id for e in candidates}

        matched = payload.get("matched_establishment_id")
        matched_id = str(matched) if matched else None
        confidence = float(payload.get("confidence") or 0.0)

        # An id outside the candidate set means the model invented one. Discard it
        # rather than trusting a hallucinated foreign key.
        if matched_id is not None and matched_id not in valid_ids:
            logger.warning(
                "binding returned an unknown establishment id",
                extra={"returned": matched_id},
            )
            matched_id = None
            confidence = 0.0

        if matched_id is not None and confidence < ACCEPT_CONFIDENCE:
            matched_id = None

        result = BindingResult(
            establishment_id=matched_id,
            confidence=round(confidence, 3),
            reason=_clean(payload.get("reason")),
            period_start=_parse_date(payload.get("period_start")),
            period_end=_parse_date(payload.get("period_end")),
            period_basis=_clean(payload.get("period_basis")),
            period_reason=_clean(payload.get("period_reason")),
        )

        # A reversed range is a reading error, not a period. Drop it: a rule that
        # divides by the period length would otherwise produce nonsense.
        if (
            result.period_start
            and result.period_end
            and result.period_end < result.period_start
        ):
            result.period_start = None
            result.period_end = None
            result.period_reason = (
                "the period read from the document ended before it began, so it "
                "was discarded"
            )

        if not result.is_bound and result.reason is None:
            result.reason = (
                "no establishment could be identified from the document header "
                "with enough confidence to attach it automatically"
            )

        return result


# -------------------------------------------------------------------- helpers
def _describe(establishment: Establishment) -> str:
    bits = [f"id={establishment.id}", f"name={establishment.name!r}"]
    if establishment.lin:
        bits.append(f"LIN={establishment.lin}")
    bits.append(f"state={establishment.state_code}")
    if establishment.district:
        bits.append(f"district={establishment.district!r}")
    if establishment.address:
        bits.append(f"address={establishment.address[:120]!r}")
    if establishment.sector:
        bits.append(f"sector={establishment.sector!r}")
    bits.append(f"workers={establishment.worker_count}")

    registrations = [
        f"{r.kind}:{r.number}" for r in (establishment.registrations or [])[:6]
    ]
    if registrations:
        bits.append("registrations=" + ", ".join(registrations))

    return "- " + "  ".join(bits)


def _range(start: date | None, end: date | None) -> str | None:
    if start and end:
        return f"{start.isoformat()} to {end.isoformat()}"
    if start:
        return f"from {start.isoformat()}"
    if end:
        return f"until {end.isoformat()}"
    return None


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "-"}:
        return None
    return text


def _parse_date(value: object) -> date | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
