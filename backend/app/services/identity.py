"""Linking the same worker across documents.

The hardest data problem in the system, and the one where a hand-written rule is
guaranteed to fail. One person appears as "RAJESH KUMAR S/O RAM LAL" in the
employee register, "Rajesh Kumar" in the wage register, "R. Kumar" on the muster
roll and "RAJESH KUMAR RAMLAL" in the EPF filing. String equality fails on all
four. Edit distance is actively misleading: it scores "Rajesh Kumar" against
"Rajesh Kumari" as nearly identical — two different people — while scoring
"R. Kumar" against "Rajesh Kumar" as distant, and those are the same one.

There is no threshold that gets this right. Transliteration varies between
filings, patronymics come and go, initials expand and contract, and the same
establishment employs three men called Ramesh Kumar. So the model decides every
match, and it decides them **together**: the whole roster and every known worker
go in one call, because a name can only be judged against the alternatives
competing for it. Resolving each name independently is how two brothers get
merged.

Getting this wrong is not cosmetic. The highest-value check in the system —
workers in the wage register who are absent from the EPF filing — is entirely a
matching result. Over-match and real evasion vanishes; under-match and every
employer stands accused of concealing workers.

What stays mechanical, and why:

* **A shared UAN is proof, not a guess.** It is a national identifier issued for
  exactly this purpose. Asking a model to second-guess it would add error, not
  remove it.
* **A conflicting UAN is disqualifying.** Two records with the same name and
  different UANs are two people, whatever the names look like.
* **rapidfuzz only shortlists.** With two thousand identities on file, the prompt
  cannot hold them all, so a cheap similarity pass chooses which to show. It
  never decides a match, and its cutoff is deliberately loose so it does not
  hide a candidate the model would have recognised.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import SkillCategory
from app.models.extraction import (
    AttendanceRecord,
    ContributionLine,
    WageLine,
    WorkerIdentity,
)
from app.services.doc_schemas import ROSTER_RESOLUTION_SCHEMA
from app.services.llm import BudgetTracker, LlmClient, LlmError, text_part

logger = logging.getLogger(__name__)


class IdentityResolutionFailed(Exception):
    """The matcher could not run. The document must not be evaluated."""


# Model confidence below this creates a new identity and flags it for review. An
# unreviewed bad merge is invisible; a duplicate record is obvious and fixable.
MODEL_ACCEPT_CONFIDENCE = 0.75

# How many known workers to put in front of the model. Generous: the cost of one
# extra candidate is a few tokens, the cost of hiding the right one is a wrong
# match that nobody catches.
MAX_CANDIDATES_SHOWN = 60

# Loose on purpose. This bounds prompt size, it does not make decisions, so it
# errs towards including candidates the model can then dismiss.
SHORTLIST_FLOOR = 45.0

# Printed names per model call. Registers run to hundreds of rows; batching keeps
# each request answerable while still letting the model see names in context.
ROSTER_BATCH = 60

# Stripped before shortlisting only. The model always sees the original spelling,
# because an honorific or a patronymic is sometimes the only thing distinguishing
# two workers.
_NOISE_TOKENS = frozenset(
    {
        "SHRI", "SHRIMATI", "SMT", "SRI", "MR", "MRS", "MS", "MISS", "MASTER",
        "SARDAR", "LATE", "DECEASED", "SO", "DO", "WO", "CO", "OF",
    }
)

_PUNCT = re.compile(r"[^A-Z0-9\s]")
_SPACE = re.compile(r"\s+")


def shortlist_key(raw: str | None) -> str:
    """Reduce a name for similarity shortlisting only.

    Never used to decide identity — only to choose which candidates the model is
    shown. Cuts at a relationship marker so the father's name does not dominate
    the comparison.
    """
    if not raw:
        return ""

    upper = str(raw).upper()
    upper = re.split(r"\b[SDWC]\s*/\s*O\b", upper)[0]
    upper = re.split(r"\b(?:SON|DAUGHTER|WIFE)\s+OF\b", upper)[0]

    cleaned = _SPACE.sub(" ", _PUNCT.sub(" ", upper)).strip()
    return " ".join(t for t in cleaned.split() if t not in _NOISE_TOKENS)


def _digits(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = "".join(ch for ch in str(value) if ch.isdigit())
    return cleaned or None


# --------------------------------------------------------------------- inputs
@dataclass
class RosterEntry:
    """One printed worker row, before identity is known."""

    printed_name: str | None
    uan: str | None = None
    esic_number: str | None = None
    father_name: str | None = None
    employee_code: str | None = None
    designation: str | None = None
    skill_category: SkillCategory | None = None
    gender: str | None = None
    date_of_joining: date | None = None
    date_of_exit: date | None = None
    is_contract_worker: bool = False
    source_document: str | None = None
    """Which document this row came from, shown to the model as context."""

    @property
    def is_resolvable(self) -> bool:
        """False for rows that are not people.

        Subtotal and carried-forward lines have no name and no identifier.
        Creating identities for them would inflate every headcount in the system,
        and headcount drives applicability for most thresholds in the Codes.
        """
        return bool((self.printed_name or "").strip() or _digits(self.uan))

    def attributes(self) -> dict[str, object | None]:
        return {
            "esic_number": self.esic_number,
            "father_name": self.father_name,
            "designation": self.designation,
            "skill_category": self.skill_category,
            "gender": self.gender,
            "date_of_joining": self.date_of_joining,
            "date_of_exit": self.date_of_exit,
            "is_contract_worker": self.is_contract_worker,
        }


@dataclass
class ResolvedIdentity:
    """The outcome of resolving one printed row."""

    identity: WorkerIdentity
    created: bool
    confidence: float
    reason: str
    needs_review: bool = False
    decided_by: str = "model"
    """``uan``, ``model``, or ``new``. Recorded so a reviewer can see whether a
    link rests on a national identifier or on a judgement."""


# ------------------------------------------------------------------- resolver
@dataclass
class IdentityResolver:
    """Resolves printed worker rows to persistent identities.

    Holds an index for one establishment so a long register does not re-query per
    row, and so an identity created earlier in the same run is immediately
    available as a candidate for later rows.
    """

    session: Session
    establishment_id: str
    client: LlmClient
    budget: BudgetTracker

    _identities: list[WorkerIdentity] = field(default_factory=list, init=False)
    _keys: dict[str, str] = field(default_factory=dict, init=False)
    _by_uan: dict[str, WorkerIdentity] = field(default_factory=dict, init=False)
    _loaded: bool = field(default=False, init=False)

    model_calls: int = field(default=0, init=False)
    review_count: int = field(default=0, init=False)
    warnings: list[str] = field(default_factory=list, init=False)

    # ------------------------------------------------------------------ index
    def _load(self) -> None:
        if self._loaded:
            return
        rows = (
            self.session.execute(
                select(WorkerIdentity).where(
                    WorkerIdentity.establishment_id == self.establishment_id
                )
            )
            .scalars()
            .all()
        )
        for identity in rows:
            self._index(identity)
        self._loaded = True

    def _index(self, identity: WorkerIdentity) -> None:
        self._identities.append(identity)
        # Index every spelling ever seen, not just the display name. A worker
        # first recorded as "R. Kumar" must still be findable when a later
        # document prints "Rajesh Kumar".
        variants = [identity.display_name, *(identity.name_variants or [])]
        self._keys[identity.id] = " | ".join(
            dict.fromkeys(shortlist_key(v) for v in variants if v)
        )
        if identity.uan:
            uan = _digits(identity.uan)
            if uan:
                self._by_uan[uan] = identity

    # --------------------------------------------------------------- resolve
    async def resolve_roster(
        self, entries: list[RosterEntry]
    ) -> list[ResolvedIdentity | None]:
        """Resolve a whole roster, returning one result per entry, in order.

        None for entries that are not people. Order is preserved so callers can
        zip results back onto their rows.
        """
        self._load()
        results: list[ResolvedIdentity | None] = [None] * len(entries)

        pending: list[int] = []

        # Pass one: UAN. Certain, free, and it also seeds the candidate pool for
        # the model pass with confirmed identities.
        for index, entry in enumerate(entries):
            if not entry.is_resolvable:
                continue

            uan = _digits(entry.uan)
            if uan and uan in self._by_uan:
                identity = self._by_uan[uan]
                self._absorb(identity, entry, uan)
                results[index] = ResolvedIdentity(
                    identity=identity,
                    created=False,
                    confidence=1.0,
                    reason=f"same Universal Account Number ({uan[:4]}XXXXXXXX)",
                    decided_by="uan",
                )
            else:
                pending.append(index)

        # Pass two: the model, on everything else.
        for start in range(0, len(pending), ROSTER_BATCH):
            batch = pending[start : start + ROSTER_BATCH]
            await self._resolve_batch(entries, batch, results)

        return results

    async def resolve_one(self, entry: RosterEntry) -> ResolvedIdentity | None:
        """Convenience wrapper for a single row, e.g. a wage slip."""
        return (await self.resolve_roster([entry]))[0]

    # ------------------------------------------------------------- internals
    async def _resolve_batch(
        self,
        entries: list[RosterEntry],
        indices: list[int],
        results: list[ResolvedIdentity | None],
    ) -> None:
        batch = [entries[i] for i in indices]
        candidates = self._shortlist(batch)
        decisions = await self._ask_model(batch, candidates)
        by_id = {identity.id: identity for identity in candidates}

        for position, index in enumerate(indices):
            entry = entries[index]
            decision = decisions.get(position) or {}

            confidence = float(decision.get("confidence") or 0.0)
            matched_id = decision.get("matched_worker_id")
            reason = str(decision.get("reason") or "").strip()
            canonical = decision.get("canonical_name")

            # The model may say this printed name is the same person as an
            # earlier printed name in the same batch — registers really do list a
            # worker twice. Follow that link to whatever the earlier row resolved
            # to, so both rows land on one identity.
            same_as = decision.get("same_as_printed_index")
            if matched_id is None and isinstance(same_as, int):
                sibling_index = indices[same_as] if 0 <= same_as < len(indices) else None
                sibling = results[sibling_index] if sibling_index is not None else None
                if sibling is not None and confidence >= MODEL_ACCEPT_CONFIDENCE:
                    self._absorb(sibling.identity, entry, _digits(entry.uan))
                    results[index] = ResolvedIdentity(
                        identity=sibling.identity,
                        created=False,
                        confidence=round(confidence, 3),
                        reason=reason or "same person as an earlier row in this document",
                        needs_review=confidence < 0.9,
                    )
                    continue

            identity = by_id.get(str(matched_id)) if matched_id else None

            if identity is not None:
                # A conflicting UAN overrides the model. Not a matter of
                # confidence: two different national identifiers are two people.
                entry_uan = _digits(entry.uan)
                existing_uan = _digits(identity.uan)
                if entry_uan and existing_uan and entry_uan != existing_uan:
                    self.warnings.append(
                        f"model matched {entry.printed_name!r} to "
                        f"{identity.display_name!r}, but their UANs differ; "
                        "treated as different people"
                    )
                    identity = None

            if identity is not None and confidence >= MODEL_ACCEPT_CONFIDENCE:
                self._absorb(identity, entry, _digits(entry.uan), canonical=canonical)
                needs_review = confidence < 0.9
                if needs_review:
                    self.review_count += 1
                results[index] = ResolvedIdentity(
                    identity=identity,
                    created=False,
                    confidence=round(confidence, 3),
                    reason=reason or "model judged these the same person",
                    needs_review=needs_review,
                )
                continue

            # Nothing confident. Create, and be honest about why.
            created = self._create(entry, canonical=canonical)
            had_candidates = bool(candidates)
            if identity is not None:
                note = (
                    f"model suggested {identity.display_name!r} at "
                    f"{confidence:.0%}, below the {MODEL_ACCEPT_CONFIDENCE:.0%} "
                    "threshold for linking"
                )
            elif reason:
                note = reason
            elif had_candidates:
                note = "no known worker matched"
            else:
                note = "first worker recorded for this establishment"

            if identity is not None or had_candidates:
                self.review_count += 1

            results[index] = ResolvedIdentity(
                identity=created,
                created=True,
                confidence=round(confidence, 3) if identity is not None else 1.0,
                reason=note,
                needs_review=identity is not None,
                decided_by="new",
            )

    def _shortlist(self, batch: list[RosterEntry]) -> list[WorkerIdentity]:
        """Choose which known workers to show the model.

        Purely a prompt-size measure. When the establishment has few identities
        on file they are all shown and no similarity scoring happens at all.
        """
        if not self._identities:
            return []
        if len(self._identities) <= MAX_CANDIDATES_SHOWN:
            return list(self._identities)

        choices = {
            identity.id: self._keys.get(identity.id, "")
            for identity in self._identities
            if self._keys.get(identity.id)
        }
        if not choices:
            return list(self._identities[:MAX_CANDIDATES_SHOWN])

        by_id = {identity.id: identity for identity in self._identities}
        chosen: dict[str, WorkerIdentity] = {}

        for entry in batch:
            key = shortlist_key(entry.printed_name)
            if not key:
                continue
            for _text, _score, identity_id in process.extract(
                key,
                choices,
                scorer=fuzz.token_set_ratio,
                limit=8,
                score_cutoff=SHORTLIST_FLOOR,
            ):
                identity = by_id.get(identity_id)
                if identity is not None:
                    chosen[identity_id] = identity
            if len(chosen) >= MAX_CANDIDATES_SHOWN:
                break

        return list(chosen.values())[:MAX_CANDIDATES_SHOWN]

    async def _ask_model(
        self, batch: list[RosterEntry], candidates: list[WorkerIdentity]
    ) -> dict[int, dict]:
        printed_lines = []
        for index, entry in enumerate(batch):
            bits = [f"[{index}] {entry.printed_name or '(no name)'}"]
            if entry.father_name:
                bits.append(f"father/husband: {entry.father_name}")
            if entry.employee_code:
                bits.append(f"employee code: {entry.employee_code}")
            if entry.uan:
                bits.append(f"UAN: {entry.uan}")
            if entry.designation:
                bits.append(f"designation: {entry.designation}")
            if entry.date_of_joining:
                bits.append(f"joined: {entry.date_of_joining.isoformat()}")
            if entry.source_document:
                bits.append(f"from: {entry.source_document}")
            printed_lines.append("  ".join(bits))

        if candidates:
            candidate_lines = []
            for identity in candidates:
                bits = [f"id={identity.id}", f"name={identity.display_name!r}"]
                if identity.father_name:
                    bits.append(f"father={identity.father_name!r}")
                    # The form this worker would appear as in an EPF or ESIC
                    # filing. Spelling it out removes the guesswork that was
                    # causing the same person to be split in two.
                    bits.append(
                        "would_appear_in_epf_as="
                        f"{f'{identity.display_name} {identity.father_name}'.upper()!r}"
                    )
                if identity.uan:
                    bits.append(f"UAN={identity.uan}")
                if identity.designation:
                    bits.append(f"designation={identity.designation!r}")
                variants = [
                    v for v in (identity.name_variants or []) if v != identity.display_name
                ]
                if variants:
                    bits.append(f"also written as {variants[:5]}")
                candidate_lines.append("- " + "  ".join(bits))
            candidate_block = "\n".join(candidate_lines)
        else:
            candidate_block = (
                "(none — no workers are on file for this establishment yet, so "
                "every printed name is a new worker)"
            )

        prompt = (
            "These are worker rows printed in an Indian statutory labour "
            "register. Decide, for each printed name, whether it is one of the "
            "workers already on file.\n\n"
            "The same worker is written differently in different filings. "
            "Initials expand and contract. Patronymics and s/o forms come and "
            "go. Honorifics appear and disappear. Transliteration varies between "
            "clerks, so the same person may be Mohammed, Mohammad or Mohd, and "
            "the same surname may be Chaudhary, Chaudhari or Choudhary.\n\n"
            "One convention matters more than any other. Provident fund and "
            "insurance filings very often print a worker's own name immediately "
            "followed by the father's name, in capitals, with no 'S/O' and nothing "
            "to mark where one ends and the other begins. So 'PRAKASH NAIR DEVI "
            "DAS' in an EPF return is the same man as 'Prakash Nair S/O Devi Das' "
            "in the wage register and 'P. Nair' on the muster roll. Where the "
            "leading words of a printed name match a known worker's own name and "
            "the trailing words match that worker's father's name, it is the same "
            "person. Each candidate below is shown with the exact form it would "
            "take under this convention, so compare against that directly.\n\n"
            "Be equally careful the other way. A gender suffix makes a different "
            "person: Kumar and Kumari are not the same. Two workers who share a "
            "father are usually siblings, not one person — compare their own names "
            "before linking them. A shared given name is "
            "not a match when the surnames or the fathers' names differ. "
            "Establishments genuinely employ several workers with the same name, "
            "often relatives, and merging them destroys the record.\n\n"
            "Use every signal you are given, not only the name: father's or "
            "husband's name, employee code, UAN, designation and date of "
            "joining. Where an employee code is present on both sides and "
            "differs, that is strong evidence of different people.\n\n"
            "Judge the printed names together, not one at a time. If two of them "
            "compete for the same worker on file, decide which one it is and say "
            "so. If two printed rows are the same person, link the later one to "
            "the earlier with same_as_printed_index.\n\n"
            f"PRINTED NAMES:\n" + "\n".join(printed_lines) + "\n\n"
            f"WORKERS ALREADY ON FILE:\n{candidate_block}\n\n"
            "Answer for every printed name, in order. A new worker is a normal "
            f"answer: give a null match. Below {MODEL_ACCEPT_CONFIDENCE:.0%} "
            "confidence no link is made and the row is held for a human, which "
            "is the correct outcome when you are not sure."
        )

        try:
            response = await self.client.complete(
                system=(
                    "You resolve worker identities across Indian statutory "
                    "labour records. Your matches decide whether an employer is "
                    "accused of concealing workers from the provident fund, so "
                    "be conservative and always state your reasoning."
                ),
                parts=[text_part(prompt)],
                budget=self.budget,
                json_schema=ROSTER_RESOLUTION_SCHEMA,
                schema_name="roster_resolution",
                max_tokens=8000,
            )
        except LlmError as exc:
            # Identity resolution is load-bearing: the provident fund coverage
            # check is entirely a matching result. Continuing without it would
            # create a fresh worker for every row and then accuse the employer of
            # concealing all of them. Fail the document instead.
            raise IdentityResolutionFailed(
                f"worker identities could not be resolved: {exc}"
            ) from exc

        self.model_calls += 1
        payload = response.parsed or {}

        for warning in payload.get("warnings") or []:
            text = str(warning).strip()
            if text and text not in self.warnings:
                self.warnings.append(text)

        decisions: dict[int, dict] = {}
        for entry in payload.get("resolutions") or []:
            index = entry.get("printed_index")
            if isinstance(index, int) and 0 <= index < len(batch):
                decisions[index] = entry

        missing = len(batch) - len(decisions)
        if missing > 0:
            # Silently dropped rows would become unmatched, and unmatched rows
            # become new workers, which inflates headcount. Say so loudly.
            self.warnings.append(
                f"{missing} of {len(batch)} printed names were not answered by "
                "the matcher and were treated as new workers"
            )

        return decisions

    # -------------------------------------------------------------- mutation
    def _create(
        self, entry: RosterEntry, *, canonical: str | None = None
    ) -> WorkerIdentity:
        display = (canonical or entry.printed_name or f"UAN {_digits(entry.uan)}").strip()
        identity = WorkerIdentity(
            establishment_id=self.establishment_id,
            display_name=display[:255],
            name_variants=(
                [entry.printed_name.strip()] if entry.printed_name else []
            ),
            uan=_digits(entry.uan),
            esic_number=_as_text(entry.esic_number),
            father_name=_as_text(entry.father_name),
            skill_category=entry.skill_category,
            designation=_as_text(entry.designation),
            gender=_as_text(entry.gender),
            date_of_joining=entry.date_of_joining,
            date_of_exit=entry.date_of_exit,
            is_contract_worker=entry.is_contract_worker,
            match_confidence=1.0,
            match_reason="new identity",
        )
        self.session.add(identity)
        self.session.flush()
        self._index(identity)
        return identity

    def _absorb(
        self,
        identity: WorkerIdentity,
        entry: RosterEntry,
        uan: str | None,
        *,
        canonical: str | None = None,
    ) -> None:
        """Enrich an existing identity from a newly seen row.

        Only fills blanks. A later document must not overwrite an identifier read
        from an earlier one: there is no basis for preferring it, and flip-flopping
        identifiers would make matching unstable between runs, which would make
        findings unstable too.
        """
        if entry.printed_name:
            cleaned = entry.printed_name.strip()
            variants = list(identity.name_variants or [])
            if cleaned and cleaned not in variants:
                variants.append(cleaned)
                identity.name_variants = variants[:20]

        # Adopt a fuller spelling as the display name when the model offers one.
        if canonical:
            better = canonical.strip()
            if better and len(better) > len(identity.display_name or ""):
                identity.display_name = better[:255]

        if uan and not identity.uan:
            identity.uan = uan
            self._by_uan[uan] = identity

        for attribute, value in entry.attributes().items():
            if attribute == "is_contract_worker":
                continue
            if value is not None and getattr(identity, attribute, None) is None:
                setattr(
                    identity,
                    attribute,
                    _as_text(value) if isinstance(value, str) else value,
                )

        # Contract status is sticky: once any document shows a worker as contract
        # labour they stay flagged, because that is what makes the contractor
        # licensing checks apply.
        if entry.is_contract_worker:
            identity.is_contract_worker = True

        # Keep the shortlist index in step with the new variants.
        self._keys[identity.id] = " | ".join(
            dict.fromkeys(
                shortlist_key(v)
                for v in [identity.display_name, *(identity.name_variants or [])]
                if v
            )
        )


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:255] or None


def reconcile_by_uan(session: Session, establishment_id: str) -> int:
    """Merge identities that share a Universal Account Number.

    Fixes a problem caused purely by upload order. A wage register carries no UAN
    column, so the identities it creates have none. If the EPF filing arrives
    before the employee register, the matcher has no identifier to match on and
    must judge on names alone — and where it hesitates, it creates a second record
    for a worker already on file. Once the employee register lands and supplies the
    UANs, the duplication becomes visible and provable.

    Merging on a shared UAN is not a heuristic. It is a national identifier issued
    for exactly this purpose, so two records carrying the same one are the same
    person by definition. Nothing here merges on name similarity.

    Returns the number of identities removed. Runs after all documents for a period
    are in, because that is the first moment the evidence is complete.
    """
    identities = (
        session.execute(
            select(WorkerIdentity).where(
                WorkerIdentity.establishment_id == establishment_id
            )
        )
        .scalars()
        .all()
    )

    by_uan: dict[str, list[WorkerIdentity]] = {}
    for identity in identities:
        uan = _digits(identity.uan)
        if uan:
            by_uan.setdefault(uan, []).append(identity)

    merged = 0

    for uan, group in by_uan.items():
        if len(group) < 2:
            continue

        # Keep the record with the most evidence attached to it, so the surviving
        # identity is the best-described one rather than an arbitrary pick.
        group.sort(
            key=lambda i: (
                len(i.name_variants or []),
                1 if i.date_of_joining else 0,
                1 if i.father_name else 0,
                len(i.display_name or ""),
            ),
            reverse=True,
        )
        keeper, duplicates = group[0], group[1:]

        for duplicate in duplicates:
            # Repoint every extracted row at the surviving identity before the
            # duplicate is removed. Missing one would orphan a wage row and quietly
            # drop a worker out of every coverage check.
            for model in (WageLine, AttendanceRecord, ContributionLine):
                for row in (
                    session.execute(
                        select(model).where(model.worker_identity_id == duplicate.id)
                    )
                    .scalars()
                    .all()
                ):
                    row.worker_identity_id = keeper.id

            variants = list(keeper.name_variants or [])
            for variant in [duplicate.display_name, *(duplicate.name_variants or [])]:
                if variant and variant not in variants:
                    variants.append(variant)
            keeper.name_variants = variants[:20]

            for attribute in (
                "esic_number",
                "father_name",
                "designation",
                "gender",
                "skill_category",
                "date_of_joining",
                "date_of_exit",
            ):
                if getattr(keeper, attribute, None) is None:
                    value = getattr(duplicate, attribute, None)
                    if value is not None:
                        setattr(keeper, attribute, value)

            if duplicate.is_contract_worker:
                keeper.is_contract_worker = True

            session.delete(duplicate)
            merged += 1

        keeper.match_reason = (
            f"merged {len(duplicates)} duplicate record(s) sharing UAN "
            f"{uan[:4]}XXXXXXXX"
        )
        keeper.match_confidence = 1.0
        keeper.match_reviewed = True

    if merged:
        session.flush()
        logger.info(
            "identities merged on shared UAN",
            extra={"establishment_id": establishment_id, "merged": merged},
        )

    return merged


def worker_key(identity: WorkerIdentity) -> str:
    """The key cross-document reconciliation rules compare on.

    Always an identity id. There is deliberately no name-based alternative: a
    coverage check that compared raw printed names would report every
    transliteration difference as a concealed worker, which is the exact false
    accusation this module exists to prevent.
    """
    return identity.id
