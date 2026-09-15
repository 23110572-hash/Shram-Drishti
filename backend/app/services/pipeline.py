"""Serialized document extraction and establishment evaluation.

Requests create durable QUEUED rows; ``app.services.jobs`` runs these entry points
one at a time. Keeping scheduling outside FastAPI responses prevents concurrent
PDF/OCR/model work from exhausting the web process and lets interrupted work be
resumed after a restart.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session_factory
from app.models.base import utcnow
from app.models.document import Document, DocumentPage, Job
from app.models.enums import (
    AuditAction,
    DocumentStatus,
    DocumentType,
    ExtractionMode,
    FindingKind,
    FindingStatus,
    JobStatus,
    RuleBasis,
    Severity,
)
from app.models.establishment import Establishment, Registration
from app.models.extraction import (
    AttendanceRecord,
    ContributionLine,
    ExtractedField,
    IncidentRecord,
    ProseAssertion,
    WageLine,
)
from app.models.finding import Finding, FindingEvidence
from app.services import alerts as alert_service
from app.services import anomaly as anomaly_service
from app.services import audit as audit_service
from app.services import facts as facts_service
from app.services import scorecard as score_service
from app.services.analyst import Analyst, DocumentBrief, FindingBrief
from app.services.binding import DocumentBinder, DocumentHeaderBrief
from app.services.extraction import (
    DocumentExtractor,
    ExtractionResult,
    PageInput,
    Record,
)
from app.services import identity as identity_service
from app.services.identity import (
    IdentityResolutionFailed,
    IdentityResolver,
    RosterEntry,
)
from app.services.llm import BudgetTracker, LlmError, get_llm_client
from app.services.ocr import OcrError, OcrFailure, get_ocr_provider
from app.services.rule_engine import RuleEngine
from app.services.storage import get_store

logger = logging.getLogger(__name__)

# Languages requested from OCR. Devanagari alongside Latin because registers in
# the Hindi belt mix scripts within a single page, often within a single cell.
OCR_LANGUAGES = ["eng", "hin"]

# Pages OCR'd per document. A 500-page muster roll would exhaust a free-tier
# daily quota on one upload and starve every other establishment that day.
MAX_OCR_PAGES = 25


class PipelineError(Exception):
    pass


# ------------------------------------------------------------------- job rows
def _load_job(
    session: Session,
    job_id: str,
    *,
    kind: str,
    subject_type: str,
    subject_id: str,
) -> Job:
    job = session.get(Job, job_id)
    if (
        job is None
        or job.kind != kind
        or job.subject_type != subject_type
        or job.subject_id != subject_id
    ):
        raise PipelineError(f"queue job {job_id} does not match {kind} {subject_id}")
    if job.status != JobStatus.RUNNING:
        raise PipelineError(f"queue job {job_id} is not running")
    return job


def _finish_job(
    session: Session, job: Job, *, error: str | None = None, **detail: Any
) -> None:
    job.status = JobStatus.FAILED if error else JobStatus.SUCCEEDED
    job.finished_at = utcnow()
    job.error = error
    job.detail = {**(job.detail or {}), **detail}
    session.flush()


def _set_job_progress(job_id: str, progress: int, stage: str, **detail: Any) -> None:
    """Persist visible progress without committing the extraction transaction."""
    with get_session_factory()() as progress_session:
        job = progress_session.get(Job, job_id)
        if job is None or job.status != JobStatus.RUNNING:
            return
        job.detail = {
            **(job.detail or {}),
            "progress": max(0, min(100, progress)),
            "stage": stage,
            **detail,
        }
        progress_session.commit()


def _set_document_progress(document_id: str, progress: int, stage: str) -> None:
    with get_session_factory()() as progress_session:
        job = progress_session.execute(
            select(Job)
            .where(
                Job.kind == "process_document",
                Job.subject_type == "document",
                Job.subject_id == document_id,
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if job is None:
            return
        job.detail = {
            **(job.detail or {}),
            "progress": max(0, min(100, progress)),
            "stage": stage,
        }
        progress_session.commit()


# =============================================================================
# Document reading
# =============================================================================
def process_document(job_id: str, document_id: str) -> None:
    """Read one queued document end to end."""
    try:
        asyncio.run(_process_document(job_id, document_id))
    except Exception as exc:  # last guard for failures before the normal handler
        logger.exception(
            "document processing failed",
            extra={"document_id": document_id, "job_id": job_id},
        )
        try:
            _fail_document(None, document_id, job_id, f"unexpected error: {exc}")
        except Exception:
            logger.exception("could not record document failure", extra={"job_id": job_id})


async def _process_document(job_id: str, document_id: str) -> None:
    settings = get_settings()
    factory = get_session_factory()

    with factory() as session:
        job = _load_job(
            session,
            job_id,
            kind="process_document",
            subject_type="document",
            subject_id=document_id,
        )
        document = session.get(Document, document_id)
        if document is None:
            _finish_job(session, job, error="document no longer exists")
            session.commit()
            return

        _set_job_progress(job.id, 5, "Preparing document")
        budget = BudgetTracker(limit_usd=settings.llm_budget_per_doc_usd)

        try:
            client = get_llm_client()
            if client.capabilities is None:
                # Verify the configured model once before spending OCR budget.
                # This pipeline sends text only, but still requires structured
                # output support for deterministic record schemas.
                await client.load_capabilities()

            pages = await _prepare_pages(session, document, job.id)
            session.commit()
            _set_job_progress(job.id, 62, "Reading documents")

            pdf_source_url: str | None = None
            if document.detected_mime == "application/pdf":
                capabilities = client.capabilities
                if capabilities is None or not capabilities.accepts_file:
                    raise PipelineError(
                        f"configured model {client.model} does not accept native PDF files"
                    )
                pdf_source_url = get_store().presigned_get_url(
                    document.storage_key,
                    expires_in=settings.s3_presigned_url_ttl_seconds,
                    response_content_type="application/pdf",
                )

            extractor = DocumentExtractor(client)
            classification = await extractor.classify(
                pages,
                budget,
                pdf_url=pdf_source_url,
                filename=document.original_filename,
            )
            document.doc_type = classification.doc_type
            document.doc_type_confidence = classification.confidence
            document.contains_redacted_pii = classification.contains_worker_identifiers
            document.status = DocumentStatus.CLASSIFIED
            _set_job_progress(job.id, 68, "Matching workplace and period")

            if classification.looks_like_multiple_documents:
                _add_review(
                    document,
                    "this file appears to contain several different documents; "
                    "split it and upload each separately",
                )

            if not classification.is_confident:
                document.status = DocumentStatus.NEEDS_BINDING
                _add_review(
                    document,
                    f"document type could not be determined "
                    f"({classification.confidence:.0%} confidence): "
                    f"{classification.reasoning or 'no reason given'}",
                )
                _finish_job(
                    session,
                    job,
                    unclassified=True,
                    confidence=classification.confidence,
                    cost_usd=round(budget.spent_usd, 6),
                    progress=100,
                    stage="Needs document details",
                )
                from app.services import batches as batch_service

                batch_id = batch_service.batch_id_for_document(session, document.id)
                if batch_id:
                    batch_service.maybe_release_batch(session, batch_id)
                session.commit()
                return

            binder = DocumentBinder(client, budget)
            binding = await binder.bind(
                session,
                organisation_id=document.organisation_id,
                header=_header_brief(document, classification, pages),
                uploaded_at=document.created_at.date() if document.created_at else None,
            )

            if binding.period_start and binding.period_end:
                document.period_start = binding.period_start
                document.period_end = binding.period_end
            elif classification.header.period_start:
                document.period_start = classification.header.period_start
                document.period_end = (
                    classification.header.period_end or classification.header.period_start
                )

            # A workplace chosen by the uploader is authoritative. The binder may
            # still read the reporting period, but it must not overwrite or reject
            # an explicit selection.
            if document.establishment_id is None:
                if not binding.is_bound:
                    document.status = DocumentStatus.NEEDS_BINDING
                    _add_review(
                        document,
                        binding.failed_reason
                        or binding.reason
                        or "the establishment this document belongs to could not be determined",
                    )
                    _finish_job(
                        session,
                        job,
                        unbound=True,
                        cost_usd=round(budget.spent_usd, 6),
                        progress=100,
                        stage="Choose a workplace",
                    )
                    from app.services import batches as batch_service

                    batch_id = batch_service.batch_id_for_document(session, document.id)
                    if batch_id:
                        batch_service.maybe_release_batch(session, batch_id)
                    session.commit()
                    return

                document.establishment_id = binding.establishment_id

            _set_job_progress(job.id, 72, "Checking the information")
            result = await extractor.extract(
                doc_type=classification.doc_type,
                pages=pages,
                budget=budget,
                pdf_url=pdf_source_url,
                filename=document.original_filename,
            )
            result.header.merge(classification.header)

            document.extraction_mode = result.mode
            document.schema_source = result.schema_source

            await _store_records(session, document, result, client, budget)
            _set_job_progress(job.id, 85, "Saving extracted records")

            for reason in result.review_reasons:
                _add_review(document, reason)

            document.status = (
                DocumentStatus.NEEDS_REVIEW
                if document.review_reasons
                else DocumentStatus.EXTRACTED
            )
            document.processed_at = utcnow()

            audit_service.record(
                session,
                action=AuditAction.DOCUMENT_ACCESSED,
                subject_type="document",
                subject_id=document.id,
                establishment_id=document.establishment_id,
                purpose="automated extraction for compliance assessment",
                detail={
                    "doc_type": str(document.doc_type),
                    "extraction_mode": str(result.mode),
                    "rows_extracted": result.row_count,
                    "llm_cost_usd": round(budget.spent_usd, 6),
                    "llm_calls": budget.calls,
                    "review_reasons": len(document.review_reasons),
                },
            )

            _finish_job(
                session,
                job,
                doc_type=str(document.doc_type),
                rows=result.row_count,
                mode=str(result.mode),
                cost_usd=round(budget.spent_usd, 6),
                llm_calls=budget.calls,
                review_reasons=len(document.review_reasons),
                progress=90,
                stage="Waiting for assessment",
            )

            # A sealed upload batch is the assessment barrier. Initial batched
            # documents never release an evaluation independently.
            from app.services import batches as batch_service

            batch_id = batch_service.batch_id_for_document(session, document.id)
            if batch_id:
                batch_service.maybe_release_batch(session, batch_id)
            elif document.establishment_id and document.period_start:
                from app.services.jobs import enqueue_evaluation

                enqueue_evaluation(
                    session,
                    document.establishment_id,
                    period_start=document.period_start,
                    period_end=document.period_end or document.period_start,
                )
            session.commit()

        except (LlmError, OcrError, IdentityResolutionFailed, PipelineError) as exc:
            session.rollback()
            _fail_document(session, document_id, job.id, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            logger.exception("unexpected failure reading document", extra={"document_id": document_id})
            _fail_document(session, document_id, job.id, f"unexpected error: {exc}")
            return


def _fail_document(_session: Session | None, document_id: str, job_id: str, error: str) -> None:
    """Mark a document failed in a fresh transaction."""
    with get_session_factory()() as fresh:
        document = fresh.get(Document, document_id)
        if document is not None:
            document.status = DocumentStatus.FAILED
            document.rejection_reason = error[:512]
        job = fresh.get(Job, job_id)
        if job is not None:
            _finish_job(
                fresh,
                job,
                error=error[:2000],
                progress=100,
                stage="Processing failed",
            )
        from app.services import batches as batch_service

        batch_id = batch_service.batch_id_for_document(fresh, document_id)
        if batch_id:
            batch_service.maybe_release_batch(fresh, batch_id)
        fresh.commit()
    logger.error("document failed", extra={"document_id": document_id, "error": error})


# --------------------------------------------------------------- page reading
async def _prepare_pages(
    session: Session, document: Document, job_id: str
) -> list[PageInput]:
    """Send the private original to OCR.space and build text-only page inputs.

    Render never downloads or rasterises PDFs and never keeps page images in
    memory. OCR.space fetches a short-lived Supabase URL directly, then only the
    returned text and word coordinates are passed to the LLM.
    """
    store = get_store()
    settings = get_settings()

    if document.detected_mime == "text/plain":
        raw = store.read(document.storage_key)
        text = raw.decode("utf-8", errors="replace")
        page_input = PageInput(page_number=1, native_text=text)
        _upsert_page(
            session,
            document,
            page_number=1,
            mode=page_input.mode,
            image_key=None,
            image_width=None,
            image_height=None,
            image_dpi=None,
            image_byte_size=None,
            ocr_provider=None,
            ocr_engine=None,
            ocr_text=None,
            ocr_markdown=None,
            ocr_tokens=[],
            ocr_failed_reason=None,
        )
        document.page_count = 1
        document.status = DocumentStatus.NORMALISED
        _set_job_progress(job_id, 60, "Text prepared", pages_completed=1, pages_total=1)
        return [page_input]

    page_total = max(1, min(document.page_count, MAX_OCR_PAGES))
    _set_job_progress(
        job_id,
        10,
        "OCR service is reading the document",
        pages_completed=0,
        pages_total=page_total,
    )

    source_url = store.presigned_get_url(
        document.storage_key,
        expires_in=settings.s3_presigned_url_ttl_seconds,
        response_content_type=document.detected_mime,
    )
    provider = get_ocr_provider()
    ocr_pages = await provider.recognise_url(
        source_url,
        mime_type=document.detected_mime,
        languages=OCR_LANGUAGES,
        expected_pages=page_total,
        want_tables=True,
    )

    if not any(page.text.strip() or page.tokens for page in ocr_pages):
        raise OcrError(OcrFailure.EMPTY_RESULT, "OCR found no text in this document")

    inputs: list[PageInput] = []
    for page_number, ocr in enumerate(ocr_pages, start=1):
        tokens = [token.as_dict() for token in ocr.tokens]
        page_input = PageInput(
            page_number=page_number,
            ocr_text=ocr.text,
            ocr_markdown=ocr.markdown,
            ocr_tokens=tokens,
        )
        inputs.append(page_input)

        _upsert_page(
            session,
            document,
            page_number=page_number,
            mode=page_input.mode,
            image_key=None,
            image_width=None,
            image_height=None,
            image_dpi=None,
            image_byte_size=None,
            ocr_provider=ocr.provider,
            ocr_engine=ocr.engine,
            ocr_text=ocr.text,
            ocr_markdown=ocr.markdown,
            ocr_tokens=tokens,
            ocr_failed_reason=None,
        )
        logger.info(
            "OCR page prepared",
            extra={
                "document_id": document.id,
                "page": page_number,
                "mode": str(page_input.mode),
                "ocr_words": len(tokens),
            },
        )

    document.page_count = len(inputs)
    document.status = DocumentStatus.NORMALISED
    _set_job_progress(
        job_id,
        60,
        "Document text ready",
        pages_completed=len(inputs),
        pages_total=len(inputs),
    )
    return inputs


def _upsert_page(
    session: Session, document: Document, *, page_number: int, mode: ExtractionMode, **fields: Any
) -> DocumentPage:
    """Create or replace a page row.

    Replaced rather than skipped, because re-uploading a corrected file must
    reprocess from scratch. Carrying forward an earlier OCR result is exactly the
    stale-data problem re-upload exists to fix.
    """
    existing = session.execute(
        select(DocumentPage).where(
            DocumentPage.document_id == document.id,
            DocumentPage.page_number == page_number,
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = DocumentPage(
            document_id=document.id, page_number=page_number, extraction_mode=mode
        )
        session.add(existing)
    else:
        existing.extraction_mode = mode

    for key, value in fields.items():
        setattr(existing, key, value)

    session.flush()
    return existing


def _header_brief(
    document: Document, classification: Any, pages: list[PageInput]
) -> DocumentHeaderBrief:
    header = classification.header
    return DocumentHeaderBrief(
        establishment_name=header.establishment_name,
        lin=header.lin,
        registration_number=header.registration_number,
        address=header.address,
        state=header.state,
        period_start=header.period_start,
        period_end=header.period_end,
        wage_period_basis=header.wage_period_basis,
        doc_type=str(classification.doc_type),
        filename=document.original_filename,
        first_page_text=pages[0].best_text if pages else None,
    )


# ----------------------------------------------------------------- persistence
async def _store_records(
    session: Session,
    document: Document,
    result: ExtractionResult,
    client: Any,
    budget: BudgetTracker,
) -> None:
    """Write extracted records, resolving worker identities as they go."""
    establishment_id = document.establishment_id
    if establishment_id is None:
        raise PipelineError("cannot store records for an unbound document")

    # Clear anything from a previous read of this document, and from any earlier
    # document covering the same ground. Re-upload means the earlier read was wrong
    # or the file has been corrected, so both have to go: merging them would leave
    # a mixture of corrected and stale rows with no way to tell them apart, and
    # would double every headcount the reconciliation rules depend on.
    _clear_previous(session, document.id)
    _supersede_earlier(session, document)

    _store_header_fields(session, document, result)

    resolver = IdentityResolver(
        session=session,
        establishment_id=establishment_id,
        client=client,
        budget=budget,
    )

    period_start = document.period_start
    period_end = document.period_end

    if result.wage_rows:
        await _store_wage_rows(
            session, document, result, resolver, period_start, period_end
        )
    if result.employee_rows:
        await _store_employee_rows(session, document, result, resolver)
    if result.attendance_rows:
        await _store_attendance_rows(
            session, document, result, resolver, period_start, period_end
        )
    if result.contribution_rows:
        await _store_contribution_rows(
            session, document, result, resolver, period_start, period_end
        )
    if result.incident_rows:
        _store_incident_rows(session, document, result, establishment_id)
    if result.registration_records:
        _store_registrations(session, document, result, establishment_id)
    if result.prose_facts:
        _store_prose(session, document, result, establishment_id)

    for warning in resolver.warnings:
        _add_review(document, f"worker matching: {warning}")

    if resolver.review_count:
        _add_review(
            document,
            f"{resolver.review_count} worker name(s) could not be matched with "
            "confidence and were recorded as new workers pending review",
        )


_EXTRACTED_MODELS = (
    WageLine,
    AttendanceRecord,
    ContributionLine,
    IncidentRecord,
    ProseAssertion,
    ExtractedField,
)


def _clear_previous(session: Session, document_id: str) -> None:
    for model in _EXTRACTED_MODELS:
        for row in (
            session.execute(select(model).where(model.document_id == document_id))
            .scalars()
            .all()
        ):
            session.delete(row)
    session.flush()


def _supersede_earlier(session: Session, document: Document) -> None:
    """Retire earlier documents covering the same type, establishment and period.

    An employer who re-files a corrected March wage register expects it to replace
    the old one. Without this, both sets of rows survive and every aggregate
    doubles: twenty-four workers become forty-eight, headcount reconciliation
    reports a fabricated discrepancy, and per-worker findings appear twice.

    The superseded document row is kept — the audit trail must show what was filed
    and when — but its extracted data is removed so it no longer feeds evaluation.
    """
    if document.establishment_id is None or document.period_start is None:
        return

    earlier = (
        session.execute(
            select(Document).where(
                Document.establishment_id == document.establishment_id,
                Document.doc_type == document.doc_type,
                Document.period_start == document.period_start,
                Document.period_end == document.period_end,
                Document.id != document.id,
                or_(
                    Document.created_at < document.created_at,
                    and_(
                        Document.created_at == document.created_at,
                        Document.id < document.id,
                    ),
                ),
                Document.status.notin_(
                    [DocumentStatus.REJECTED, DocumentStatus.FAILED]
                ),
            )
        )
        .scalars()
        .all()
    )

    for stale in earlier:
        _clear_previous(session, stale.id)
        stale.status = DocumentStatus.SUPERSEDED
        stale.rejection_reason = (
            f"superseded by {document.original_filename} filed later for the same "
            "period"
        )
        _add_review(
            stale,
            "this filing was replaced by a later one for the same period; its data "
            "has been withdrawn from assessment",
        )

        audit_service.record(
            session,
            action=AuditAction.DOCUMENT_REJECTED,
            subject_type="document",
            subject_id=stale.id,
            establishment_id=stale.establishment_id,
            detail={
                "reason": "superseded",
                "superseded_by": document.id,
                "doc_type": str(document.doc_type),
                "period_start": document.period_start.isoformat(),
            },
        )

    if earlier:
        document.supersedes_document_id = earlier[-1].id
        logger.info(
            "superseded earlier filings",
            extra={
                "document_id": document.id,
                "superseded": len(earlier),
                "doc_type": str(document.doc_type),
            },
        )

    session.flush()


def _store_header_fields(
    session: Session, document: Document, result: ExtractionResult
) -> None:
    header = result.header
    values: dict[str, Any] = {
        "establishment_name": header.establishment_name,
        "lin": header.lin,
        "registration_number": header.registration_number,
        "address": header.address,
        "state": header.state,
        "wage_period_basis": header.wage_period_basis,
    }

    for name, value in values.items():
        if value is None:
            continue
        session.add(
            ExtractedField(
                document_id=document.id,
                name=name,
                value_text=str(value)[:2000],
                source_page=1,
                agreement="model_only",
            )
        )

    for name, value in (
        ("period_start", header.period_start),
        ("period_end", header.period_end),
    ):
        if value is not None:
            session.add(
                ExtractedField(
                    document_id=document.id,
                    name=name,
                    value_date=value,
                    source_page=1,
                    agreement="model_only",
                )
            )

    for key, value in (result.printed_totals or {}).items():
        session.add(
            ExtractedField(
                document_id=document.id,
                name=f"printed_total_{key}",
                value_text=str(value)[:2000] if value is not None else None,
                source_page=1,
                agreement="model_only",
            )
        )

    if result.source_counts:
        session.add(
            ExtractedField(
                document_id=document.id,
                name="dual_source_counts",
                value_text=__import__("json").dumps(result.source_counts)[:2000],
                agreement="agreed" if not result.disagreements else "disagreed",
                needs_review=bool(result.disagreements),
            )
        )
    for index, disagreement in enumerate(result.disagreements[:20], start=1):
        session.add(
            ExtractedField(
                document_id=document.id,
                name=f"source_disagreement_{index}",
                value_text=__import__("json").dumps(disagreement, ensure_ascii=False)[:2000],
                source_page=disagreement.get("page"),
                agreement="disagreed",
                needs_review=True,
            )
        )

    session.flush()


def _roster_entry(record: Record, document: Document) -> RosterEntry:
    values = record.values
    return RosterEntry(
        printed_name=values.get("worker_name_as_printed"),
        uan=values.get("uan"),
        esic_number=values.get("esic_number"),
        father_name=values.get("father_name"),
        employee_code=values.get("employee_code"),
        designation=values.get("designation"),
        skill_category=values.get("skill_category"),
        gender=values.get("gender"),
        date_of_joining=values.get("date_of_joining"),
        date_of_exit=values.get("date_of_exit"),
        is_contract_worker=bool(values.get("is_contract_worker")),
        source_document=f"{document.doc_type.value} ({document.original_filename})",
    )


def _apply_match(identity: Any, resolved: Any) -> None:
    identity.match_confidence = resolved.confidence
    identity.match_reason = resolved.reason[:512] if resolved.reason else None
    if resolved.needs_review:
        identity.match_reviewed = False


async def _store_wage_rows(
    session: Session,
    document: Document,
    result: ExtractionResult,
    resolver: IdentityResolver,
    period_start: date | None,
    period_end: date | None,
) -> None:
    entries = [_roster_entry(record, document) for record in result.wage_rows]
    resolutions = await resolver.resolve_roster(entries)

    for record, resolved in zip(result.wage_rows, resolutions, strict=True):
        values = record.values

        if resolved is None:
            # No name and no identifier: a subtotal or carried-forward line, not
            # a worker. Storing it would corrupt every headcount.
            continue

        _apply_match(resolved.identity, resolved)

        session.add(
            WageLine(
                document_id=document.id,
                establishment_id=document.establishment_id,
                worker_identity_id=resolved.identity.id,
                worker_name_as_printed=(values.get("worker_name_as_printed") or "")[:255],
                row_number=values.get("row_number"),
                period_start=period_start,
                period_end=period_end,
                days_paid=values.get("days_paid"),
                days_present=values.get("days_present"),
                overtime_hours=values.get("overtime_hours"),
                normal_hours_per_day=values.get("normal_hours_per_day"),
                basic_paise=values.get("basic_paise"),
                da_paise=values.get("da_paise"),
                other_allowances_paise=values.get("other_allowances_paise"),
                gross_paise=values.get("gross_paise"),
                overtime_paise=values.get("overtime_paise"),
                overtime_rate_paise=values.get("overtime_rate_paise"),
                deductions_paise=values.get("deductions_paise"),
                pf_deduction_paise=values.get("pf_deduction_paise"),
                esi_deduction_paise=values.get("esi_deduction_paise"),
                advance_recovery_paise=values.get("advance_recovery_paise"),
                net_paid_paise=values.get("net_paid_paise"),
                paid_on=values.get("paid_on"),
                skill_category=values.get("skill_category"),
                provenance=record.provenance,
                # Carried onto the row itself, not just the document. The rule
                # engine has to know which individual rows it may judge on.
                needs_review=record.needs_review,
                review_reasons=list(record.review_reasons[:8]),
            )
        )

        for reason in record.review_reasons:
            _add_review(document, reason)

    session.flush()


async def _store_employee_rows(
    session: Session,
    document: Document,
    result: ExtractionResult,
    resolver: IdentityResolver,
) -> None:
    entries = [_roster_entry(record, document) for record in result.employee_rows]
    resolutions = await resolver.resolve_roster(entries)

    for record, resolved in zip(result.employee_rows, resolutions, strict=True):
        if resolved is None:
            continue
        _apply_match(resolved.identity, resolved)
        for reason in record.review_reasons:
            _add_review(document, reason)

    session.flush()


async def _store_attendance_rows(
    session: Session,
    document: Document,
    result: ExtractionResult,
    resolver: IdentityResolver,
    period_start: date | None,
    period_end: date | None,
) -> None:
    entries = [_roster_entry(record, document) for record in result.attendance_rows]
    resolutions = await resolver.resolve_roster(entries)

    for record, resolved in zip(result.attendance_rows, resolutions, strict=True):
        if resolved is None:
            continue

        values = record.values
        _apply_match(resolved.identity, resolved)

        session.add(
            AttendanceRecord(
                document_id=document.id,
                establishment_id=document.establishment_id,
                worker_identity_id=resolved.identity.id,
                worker_name_as_printed=(values.get("worker_name_as_printed") or "")[:255],
                period_start=period_start,
                period_end=period_end,
                days_present=values.get("days_present"),
                days_absent=values.get("days_absent"),
                weekly_offs_given=values.get("weekly_offs_given"),
                total_hours=values.get("total_hours"),
                overtime_hours=values.get("overtime_hours"),
                max_daily_hours=values.get("max_daily_hours"),
                max_weekly_hours=values.get("max_weekly_hours"),
                longest_consecutive_days=values.get("longest_consecutive_days"),
                provenance=record.provenance,
                needs_review=record.needs_review,
                review_reasons=list(record.review_reasons[:8]),
            )
        )

        for reason in record.review_reasons:
            _add_review(document, reason)

    session.flush()


async def _store_contribution_rows(
    session: Session,
    document: Document,
    result: ExtractionResult,
    resolver: IdentityResolver,
    period_start: date | None,
    period_end: date | None,
) -> None:
    entries = [_roster_entry(record, document) for record in result.contribution_rows]
    resolutions = await resolver.resolve_roster(entries)

    scheme = result.scheme or (
        "EPF" if document.doc_type is DocumentType.EPF_ECR else "ESIC"
    )

    for record, resolved in zip(result.contribution_rows, resolutions, strict=True):
        if resolved is None:
            continue

        values = record.values
        _apply_match(resolved.identity, resolved)

        session.add(
            ContributionLine(
                document_id=document.id,
                establishment_id=document.establishment_id,
                worker_identity_id=resolved.identity.id,
                scheme=scheme,
                worker_name_as_printed=(values.get("worker_name_as_printed") or "")[:255],
                uan=values.get("uan"),
                member_id=values.get("member_id"),
                period_start=period_start,
                period_end=period_end,
                wage_base_paise=values.get("wage_base_paise"),
                employee_share_paise=values.get("employee_share_paise"),
                employer_share_paise=values.get("employer_share_paise"),
                ncp_days=values.get("ncp_days"),
                deposited_on=result.deposited_on,
                challan_number=result.challan_number,
                provenance=record.provenance,
                needs_review=record.needs_review,
                review_reasons=list(record.review_reasons[:8]),
            )
        )

        for reason in record.review_reasons:
            _add_review(document, reason)

    session.flush()


def _store_incident_rows(
    session: Session,
    document: Document,
    result: ExtractionResult,
    establishment_id: str,
) -> None:
    for record in result.incident_rows:
        values = record.values
        session.add(
            IncidentRecord(
                document_id=document.id,
                establishment_id=establishment_id,
                occurred_on=values.get("occurred_on"),
                description=values.get("description"),
                severity=values.get("severity"),
                workers_affected=values.get("workers_affected"),
                notified_on=values.get("notified_on"),
                notification_reference=values.get("notification_reference"),
                provenance=record.provenance,
            )
        )
        for reason in record.review_reasons:
            _add_review(document, reason)
    session.flush()


def _store_registrations(
    session: Session,
    document: Document,
    result: ExtractionResult,
    establishment_id: str,
) -> None:
    """Upsert registrations read off a certificate.

    Keyed on kind and number so re-uploading a renewed certificate updates the
    validity window rather than accumulating a row per upload, which would make
    "is this licence current" unanswerable.
    """
    for record in result.registration_records:
        values = record.values
        number = values.get("number")
        kind = (values.get("kind") or "ESTABLISHMENT_REGISTRATION").upper()

        if not number:
            for reason in record.review_reasons:
                _add_review(document, reason)
            continue

        existing = session.execute(
            select(Registration).where(
                Registration.establishment_id == establishment_id,
                Registration.kind == kind,
                Registration.number == number,
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                Registration(
                    establishment_id=establishment_id,
                    kind=kind[:64],
                    number=str(number)[:64],
                    issuing_authority=values.get("issuing_authority"),
                    valid_from=values.get("valid_from"),
                    valid_to=values.get("valid_to"),
                )
            )
        else:
            existing.issuing_authority = (
                values.get("issuing_authority") or existing.issuing_authority
            )
            existing.valid_from = values.get("valid_from") or existing.valid_from
            existing.valid_to = values.get("valid_to") or existing.valid_to

        for reason in record.review_reasons:
            _add_review(document, reason)

    session.flush()


def _store_prose(
    session: Session,
    document: Document,
    result: ExtractionResult,
    establishment_id: str,
) -> None:
    for record in result.prose_facts:
        values = record.values
        key = values.get("key")
        if not key:
            continue

        session.add(
            ProseAssertion(
                document_id=document.id,
                establishment_id=establishment_id,
                key=str(key)[:96],
                present=bool(values.get("present")),
                value_text=values.get("value_text"),
                quote=values.get("quote"),
                source_page=values.get("source_page"),
                confidence=values.get("confidence"),
            )
        )
        for reason in record.review_reasons:
            _add_review(document, reason)

    session.flush()


def _add_review(document: Document, reason: str) -> None:
    reasons = list(document.review_reasons or [])
    trimmed = reason.strip()[:400]
    if trimmed and trimmed not in reasons:
        reasons.append(trimmed)
        # Capped so one badly scanned document cannot produce a thousand-item
        # list nobody will read.
        document.review_reasons = reasons[:40]


# =============================================================================
# Evaluation
# =============================================================================
def evaluate_establishment(
    job_id: str,
    establishment_id: str,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    actor_id: str | None = None,
) -> None:
    """Evaluate one queued establishment period."""
    try:
        asyncio.run(
            _evaluate_establishment(
                job_id,
                establishment_id,
                period_start=period_start,
                period_end=period_end,
                actor_id=actor_id,
            )
        )
    except Exception:
        logger.exception(
            "evaluation failed",
            extra={"establishment_id": establishment_id, "job_id": job_id},
        )


async def _evaluate_establishment(
    job_id: str,
    establishment_id: str,
    *,
    period_start: date | None,
    period_end: date | None,
    actor_id: str | None,
) -> None:
    settings = get_settings()

    with get_session_factory()() as session:
        job = _load_job(
            session,
            job_id,
            kind="evaluate_establishment",
            subject_type="establishment",
            subject_id=establishment_id,
        )
        establishment = session.get(Establishment, establishment_id)
        if establishment is None:
            _finish_job(session, job, error="establishment no longer exists")
            session.commit()
            return

        try:
            # Merge duplicate worker records before building any facts. Upload order
            # decides how much identifying information the matcher had at the time,
            # so a worker first seen on a wage register with no UAN column can end
            # up recorded twice. By now every document for the period is in, so the
            # UANs are known and the duplication is provable. Left unmerged it
            # inflates every headcount and breaks the coverage checks.
            merged = identity_service.reconcile_by_uan(session, establishment_id)
            if merged:
                logger.info(
                    "reconciled duplicate worker identities before evaluation",
                    extra={"establishment_id": establishment_id, "merged": merged},
                )
                session.flush()

            batch_id = (job.detail or {}).get("batch_id")
            if batch_id:
                from app.services import batches as batch_service

                session.info["assessment_document_ids"] = [
                    document.id
                    for document in batch_service.batch_documents(session, batch_id)
                    if document.status in batch_service.USABLE
                ]

            context = facts_service.build_facts(
                session,
                establishment=establishment,
                period_start=period_start,
                period_end=period_end,
            )
            # Extracted headcounts remain assessment evidence only. OCR/model
            # disagreement must never permanently mutate the establishment profile.
            _set_job_progress(job.id, 92, "Assessing compliance")
            for source_document in context.documents:
                _set_document_progress(source_document.id, 92, "Assessing compliance")

            # 1. Deterministic rules. These, and only these, decide compliance.
            engine = RuleEngine()
            report = engine.evaluate(session, context, actor_id=actor_id)
            session.flush()

            # 2. Statistical signals. Advisory, never scored.
            anomalies = anomaly_service.detect(
                wage_rows=context.rows("wage_register"),
                attendance_rows=context.rows("attendance"),
                epf_rows=context.rows("epf"),
                peer_medians=_peer_medians(session, establishment),
            )
            _store_anomalies(session, context, anomalies)
            session.flush()

            # 3. The model's review. It explains deterministic findings, checks
            #    all linked documents together, and raises advisory leads for
            #    patterns the rules could not anticipate. It never changes a
            #    verdict or scoring severity.
            analyst_notes = await _run_analyst(
                session, establishment, context, report.findings, settings
            )
            session.flush()

            # 4. Score. Statistical and model-only observations are excluded,
            #    so advisory AI output cannot move the deterministic number.
            score = score_service.compute_score(
                session,
                establishment=establishment,
                period_start=period_start,
                period_end=period_end,
                report=report,
            )
            # Counts observed in the uploaded records. Reported beside the result
            # rather than written into the employer's declared profile.
            observed = context.namespaces.get("counts") or {}
            score.computation["observed_counts"] = {
                key: observed.get(key)
                for key in (
                    "register",
                    "wage_register",
                    "epf",
                    "esic",
                    "annual_return",
                    "effective",
                    "effective_peak_12m",
                    "contract",
                )
                if observed.get(key) is not None
            }
            score_available = bool(score.computation.get("score_available"))
            if score_available:
                score_service.persist_score(
                    session,
                    establishment=establishment,
                    period_start=period_start,
                    period_end=period_end,
                    result=score,
                    actor_id=actor_id,
                    review_summary=_combined_analyst_summary(analyst_notes),
                    records_quality=analyst_notes.records_quality,
                )

                # Alerts use only the deterministic findings that contributed to
                # this uploaded-record score.
                contributing_ids = {
                    finding_id
                    for ids in score.computation.get("contributing_findings", {}).values()
                    for finding_id in ids
                }
                current = [
                    finding
                    for finding in _current_findings(
                        session, establishment_id, period_start, period_end
                    )
                    if finding.id in contributing_ids
                ]
                queued = alert_service.build_alerts(
                    session, establishment=establishment, findings=current, score=score
                )
                alert_service.record_alerts(session, queued, actor_id=actor_id)
            else:
                queued = []

            for document in context.documents:
                if document.status in {
                    DocumentStatus.EXTRACTED,
                    DocumentStatus.VERIFIED,
                }:
                    document.status = DocumentStatus.EVALUATED

            _finish_job(
                session,
                job,
                rules_considered=report.rules_considered,
                rules_applied=report.rules_applied,
                violations=len(report.violations),
                unassessable=report.rules_unassessable,
                coverage=report.coverage,
                anomalies=len(anomalies),
                model_observations=analyst_notes.observations_stored,
                severities_adjusted=analyst_notes.severities_adjusted,
                score=score.overall_score if score_available else None,
                score_available=score_available,
                assessed_rules=score.computation.get("assessed_rule_count", 0),
                risk_band=str(score.risk_band) if score_available else None,
                completeness=score.completeness.overall,
                alerts=len(queued),
                errors=report.errors[:10],
                progress=100,
                stage="Complete",
            )
            from app.services import batches as batch_service

            batch_service.mark_batch_complete(
                session, (job.detail or {}).get("batch_id")
            )
            session.commit()
            for source_document in context.documents:
                _set_document_progress(source_document.id, 100, "Complete")

        except Exception as exc:  # noqa: BLE001
            session.rollback()
            with get_session_factory()() as fresh:
                stale = fresh.get(Job, job.id)
                if stale is not None:
                    _finish_job(fresh, stale, error=str(exc)[:2000])
                    from app.services import batches as batch_service

                    batch_service.mark_batch_complete(
                        fresh, (stale.detail or {}).get("batch_id")
                    )
                fresh.commit()
            raise


def _adopt_documented_workforce(
    session: Session,
    *,
    establishment: Establishment,
    context: facts_service.FactContext,
    actor_id: str | None,
) -> None:
    """Raise a zero/stale profile count to the documented workforce lower bound.

    Applicability must not remain at zero after linked registers identify real
    workers. The fact builder takes the maximum across independent sources; this
    persists that conservative lower bound without ever reducing a declared value.
    """
    counts = context.namespaces.get("counts") or {}
    effective = counts.get("effective")
    effective_peak = counts.get("effective_peak_12m")
    if not isinstance(effective, int) or not isinstance(effective_peak, int):
        return

    previous_current = establishment.worker_count
    previous_peak = establishment.worker_count_peak_12m
    establishment.worker_count = max(previous_current, effective)
    establishment.worker_count_peak_12m = max(
        previous_peak, establishment.worker_count, effective_peak
    )
    if (
        establishment.worker_count == previous_current
        and establishment.worker_count_peak_12m == previous_peak
    ):
        return

    audit_service.record(
        session,
        action=AuditAction.ESTABLISHMENT_PROFILE_DERIVED,
        subject_type="establishment",
        subject_id=establishment.id,
        actor_id=actor_id,
        establishment_id=establishment.id,
        purpose="deriving workforce threshold context from linked filings",
        detail={
            "previous_worker_count": previous_current,
            "worker_count": establishment.worker_count,
            "previous_peak_12m": previous_peak,
            "worker_count_peak_12m": establishment.worker_count_peak_12m,
            "source_counts": {
                key: counts.get(key)
                for key in (
                    "register",
                    "wage_register",
                    "epf",
                    "esic",
                    "annual_return",
                )
            },
        },
    )
    session.flush()


@dataclass
class AnalystOutcome:
    """What the model review produced, for the caller to record.

    The review runs before scoring and none of this enters the calculation. It is
    returned rather than only logged so the narrative can be stored next to the
    number instead of buried in the audit trail, where nobody reading a score
    would find it.
    """

    observations_stored: int = 0
    severities_adjusted: int = 0
    overall_assessment: str | None = None
    records_quality: str | None = None
    consistency_notes: str | None = None


def _combined_analyst_summary(outcome: AnalystOutcome) -> str | None:
    parts: list[str] = []
    if outcome.overall_assessment:
        parts.append(outcome.overall_assessment.strip())
    if outcome.consistency_notes:
        parts.append(outcome.consistency_notes.strip())
    return "\n\n".join(part for part in parts if part) or None


async def _run_analyst(
    session: Session,
    establishment: Establishment,
    context: facts_service.FactContext,
    findings: list[Finding],
    settings: Any,
) -> AnalystOutcome:
    """Run the model review and store what it produced.

    Failure here is logged and swallowed. Deterministic rule findings and the
    score remain valid without it: this pass adds explanations, cross-document
    consistency analysis and advisory leads without changing legal outcomes.
    """
    if not context.documents:
        return AnalystOutcome()

    try:
        client = get_llm_client()
        if client.capabilities is None:
            await client.load_capabilities()
    except LlmError as exc:
        logger.warning("analyst unavailable", extra={"error": str(exc)})
        return AnalystOutcome()

    budget = BudgetTracker(limit_usd=settings.llm_budget_per_doc_usd * 2)
    analyst = Analyst(client, budget)

    briefs = _document_briefs(session, context)
    finding_briefs = [_finding_brief(f) for f in findings]
    summary = _establishment_summary(establishment, context)

    try:
        report = await analyst.review(
            establishment_summary=summary,
            documents=briefs,
            findings=finding_briefs,
        )
        cross = await analyst.compare_documents(
            establishment_summary=summary, documents=briefs
        )
    except LlmError as exc:
        logger.warning("analyst review failed", extra={"error": str(exc)})
        return AnalystOutcome()

    # Annotate deterministic findings without changing their legal verdict or
    # scoring severity. The model contributes plain-language explanation,
    # consistency context and false-positive leads; deterministic rules remain
    # the sole authority for the score.
    by_id = {f.id: f for f in findings}
    for assessment in report.assessments:
        finding = by_id.get(assessment.finding_id)
        if finding is None:
            continue

        explanation = (assessment.plain_explanation or "").strip()
        if (
            assessment.severity_opinion is not None
            and assessment.severity_opinion is not finding.severity
        ):
            advisory = (
                "Automated context suggested "
                f"{assessment.severity_opinion.value.lower()} severity; "
                f"the deterministic rule remains {finding.severity.value.lower()}."
            )
            explanation = f"{explanation}\n\n{advisory}" if explanation else advisory
        finding.explanation = explanation or None

        if assessment.is_possible_false_positive:
            finding.possible_false_positive = True
            finding.false_positive_reason = assessment.reason

    adjusted = 0

    observations = [*report.observations, *cross.observations]
    stored = _store_observations(session, context, observations)

    if report.overall_assessment or cross.consistency_notes:
        audit_service.record(
            session,
            action=AuditAction.SCORE_COMPUTED,
            subject_type="establishment",
            subject_id=establishment.id,
            establishment_id=establishment.id,
            purpose="model review of compliance records",
            detail={
                "overall_assessment": (report.overall_assessment or "")[:2000],
                "records_quality": report.records_quality,
                "consistency_notes": (cross.consistency_notes or "")[:2000],
                "observations_stored": stored,
                "severities_adjusted": adjusted,
                "llm_cost_usd": round(budget.spent_usd, 6),
            },
        )

    return AnalystOutcome(
        observations_stored=stored,
        severities_adjusted=adjusted,
        overall_assessment=report.overall_assessment,
        records_quality=report.records_quality,
        consistency_notes=cross.consistency_notes,
    )


def _store_anomalies(
    session: Session,
    context: facts_service.FactContext,
    anomalies: list[anomaly_service.Anomaly],
) -> None:
    """Persist statistical signals as advisory findings."""
    import hashlib

    for anomaly in anomalies:
        key_source = "|".join(
            [
                anomaly.key,
                context.establishment.id,
                context.period_start.isoformat() if context.period_start else "-",
                context.period_end.isoformat() if context.period_end else "-",
            ]
        )
        dedupe = hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:48]

        existing = session.execute(
            select(Finding).where(Finding.dedupe_key == dedupe)
        ).scalar_one_or_none()

        if existing is not None:
            existing.message = anomaly.detail
            existing.observed = anomaly.statistic
            existing.severity = anomaly.severity
            continue

        finding = Finding(
            establishment_id=context.establishment.id,
            # Fixed. An anomaly cannot be stored as anything else, so it can
            # never be picked up by the scorer.
            kind=FindingKind.ANOMALY,
            code=anomaly.code,
            severity=anomaly.severity,
            rule_id=f"ANOMALY.{anomaly.key.upper().replace('.', '_')}",
            rule_pack_version="anomaly@1.0",
            jurisdiction=context.establishment.jurisdiction_code,
            citation="Statistical observation — not a statutory provision",
            # An anomaly compares records against the spread of other records, so
            # it rests on no statutory number at all. It is never scored either
            # way, so this is a label for the reader rather than an input to the
            # arithmetic.
            rule_basis=RuleBasis.RECONCILIATION,
            title=anomaly.title,
            message=anomaly.detail,
            remediation=anomaly.suggested_check,
            observed=anomaly.statistic,
            expected={},
            period_start=context.period_start,
            period_end=context.period_end,
            status=FindingStatus.OPEN,
            dedupe_key=dedupe,
        )
        session.add(finding)

    session.flush()


def _store_observations(
    session: Session,
    context: facts_service.FactContext,
    observations: list[Any],
) -> int:
    """Persist the model's own observations.

    Every one is forced through the same guard: a model-raised item can be a
    discrepancy, a missing field or an anomaly, and never a non-compliance. A
    legal conclusion needs a citation and a reproducible test, and this has
    neither — the citation field says so explicitly rather than borrowing a
    section number to look authoritative.
    """
    import hashlib

    stored = 0
    document_ids = [d.id for d in context.documents]
    known_document_ids = set(document_ids)

    for observation in observations:
        involved_ids = [
            document_id
            for document_id in getattr(observation, "documents_involved", [])
            if document_id in known_document_ids
        ]
        evidence_document_id = involved_ids[0] if len(involved_ids) == 1 else None
        kind = observation.kind
        if kind is FindingKind.NON_COMPLIANCE:
            kind = FindingKind.DISCREPANCY

        key_source = "|".join(
            [
                "model",
                observation.title.lower()[:120],
                context.establishment.id,
                context.period_start.isoformat() if context.period_start else "-",
            ]
        )
        dedupe = hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:48]

        if session.execute(
            select(Finding).where(Finding.dedupe_key == dedupe)
        ).scalar_one_or_none():
            continue

        finding = Finding(
            establishment_id=context.establishment.id,
            kind=kind,
            code=observation.code,
            severity=observation.severity,
            rule_id="MODEL.OBSERVATION",
            rule_pack_version="analyst@1.0",
            jurisdiction=context.establishment.jurisdiction_code,
            citation=(
                "Observation from automated review — no statutory provision is "
                "asserted and this does not affect the compliance score"
            ),
            # Same as an anomaly: derived from the documents themselves, asserts
            # no statutory number, and never scored.
            rule_basis=RuleBasis.RECONCILIATION,
            title=observation.title[:255],
            message=observation.detail,
            remediation=getattr(observation, "suggested_check", None),
            observed={
                "confidence": observation.confidence,
                "affected_workers": observation.affected_workers[:30],
                "evidence_pages": getattr(observation, "evidence_pages", []),
                "documents_involved": getattr(observation, "documents_involved", []),
            },
            expected={},
            period_start=context.period_start,
            period_end=context.period_end,
            extraction_confidence=observation.confidence,
            status=FindingStatus.OPEN,
            dedupe_key=dedupe,
        )

        for page in getattr(observation, "evidence_pages", [])[:6]:
            finding.evidence.append(
                FindingEvidence(
                    document_id=evidence_document_id,
                    page_number=page,
                    note="page identified by automated review",
                )
            )

        session.add(finding)
        stored += 1

    session.flush()
    return stored


# -------------------------------------------------------------------- briefing
def _document_briefs(
    session: Session, context: facts_service.FactContext
) -> list[DocumentBrief]:
    briefs: list[DocumentBrief] = []

    for document in context.documents:
        pages = (
            session.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == document.id)
                .order_by(DocumentPage.page_number)
                .limit(6)
            )
            .scalars()
            .all()
        )
        text = "\n\n".join(
            f"[page {p.page_number}]\n{(p.ocr_markdown or p.ocr_text or '').strip()}"
            for p in pages
            if (p.ocr_markdown or p.ocr_text)
        )

        briefs.append(
            DocumentBrief(
                document_id=document.id,
                doc_type=str(document.doc_type),
                filename=document.original_filename,
                period=(
                    f"{document.period_start} to {document.period_end}"
                    if document.period_start
                    else None
                ),
                extraction_mode=str(document.extraction_mode)
                if document.extraction_mode
                else None,
                row_summary=_row_summary(document, context),
                text=text or None,
                review_reasons=list(document.review_reasons or []),
            )
        )

    return briefs


def _row_summary(document: Document, context: facts_service.FactContext) -> str | None:
    """Render the structured rows for one document as compact text.

    The extracted table is given to the analyst alongside the raw text, so it can
    see both what we read and what the page says. That is what lets it catch a
    column mapped to the wrong field, which is the extraction error most likely to
    generate false findings.
    """
    lines: list[str] = []

    for namespace, label in (
        ("wage_register", "wage rows"),
        ("attendance", "attendance rows"),
        ("epf", "EPF lines"),
        ("esic", "ESIC lines"),
    ):
        rows = context.rows(namespace)
        sources = context.row_sources.get(namespace) or []
        mine = [
            row
            for index, row in enumerate(rows)
            if index < len(sources) and sources[index].get("document_id") == document.id
        ]
        if not mine:
            continue

        lines.append(f"{len(mine)} {label}:")
        for row in mine[:25]:
            parts = [
                f"{key}={_render(value)}"
                for key, value in row.items()
                if value is not None
                and key
                not in {
                    "worker_key",
                    "esic_eligible_worker_key",
                    "worker_display_name",
                }
            ]
            lines.append("  " + "  ".join(parts))
        if len(mine) > 25:
            lines.append(f"  ...and {len(mine) - 25} more rows")

    prose = context.namespaces.get("prose") or {}
    if prose and document.doc_type in {
        DocumentType.APPOINTMENT_LETTER,
        DocumentType.STANDING_ORDERS,
        DocumentType.GRIEVANCE_COMMITTEE_RECORD,
        DocumentType.ANNUAL_RETURN,
        DocumentType.HEALTH_CHECKUP_RECORD,
        DocumentType.WELFARE_FACILITY_RECORD,
    }:
        stated = {
            key: value
            for key, value in prose.items()
            if not key.endswith(("_quote", "_stated"))
        }
        if stated:
            lines.append("stated facts: " + _render(stated))

    return "\n".join(lines) if lines else None


def _render(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}={_render(v)}" for k, v in list(value.items())[:20])
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f"{value:g}"
    return str(value)[:120]


def _finding_brief(finding: Finding) -> FindingBrief:
    return FindingBrief(
        finding_id=finding.id,
        rule_id=finding.rule_id,
        title=finding.title,
        citation=finding.citation,
        message=finding.message,
        kind=str(finding.kind),
        severity=str(finding.severity),
        observed=dict(finding.observed or {}),
        expected=dict(finding.expected or {}),
        evidence=[
            " ".join(
                filter(
                    None,
                    [
                        f"page {e.page_number}" if e.page_number else None,
                        e.field_name,
                        f"= {e.value_shown}" if e.value_shown else None,
                        f"({e.row_reference})" if e.row_reference else None,
                    ],
                )
            )
            for e in finding.evidence
        ],
        awaiting_notification=finding.rule_basis.needs_notified_rules,
    )


def _establishment_summary(
    establishment: Establishment, context: facts_service.FactContext
) -> str:
    counts = context.namespaces.get("counts") or {}
    period = context.namespaces.get("period") or {}
    floor = context.namespaces.get("wage_floor") or {}

    lines = [
        f"{establishment.name} (id {establishment.id})",
        f"State {establishment.state_code}"
        + (f", district {establishment.district}" if establishment.district else ""),
        f"Sector: {establishment.sector or 'not recorded'}",
        f"Declared workers: {establishment.worker_count} "
        f"(12-month peak {establishment.worker_count_peak_12m}, "
        f"women {establishment.women_worker_count}, "
        f"contract {establishment.contract_worker_count})",
        f"Factory: {establishment.is_factory}, "
        f"hazardous process: {establishment.has_hazardous_process}, "
        f"engages contract labour: {establishment.engages_contract_labour}",
        f"Period assessed: {period.get('start')} to {period.get('end')} "
        f"({period.get('days')} days, {period.get('basis')})",
        f"Workers found in: register {counts.get('register')}, "
        f"wage register {counts.get('wage_register')}, "
        f"EPF {counts.get('epf')}, ESIC {counts.get('esic')}",
    ]

    if floor.get("daily_paise"):
        lines.append(
            f"Applicable minimum daily wage: ₹{floor['daily_paise'] / 100:,.2f} "
            f"(source: {floor.get('source')})"
        )
    else:
        lines.append(
            "No minimum wage rate is on file for this state and period, so wage "
            "floor comparisons could not be made."
        )

    return "\n".join(lines)


def _current_findings(
    session: Session,
    establishment_id: str,
    period_start: date | None,
    period_end: date | None,
) -> list[Finding]:
    query = select(Finding).where(Finding.establishment_id == establishment_id)
    if period_start is not None:
        query = query.where(Finding.period_start == period_start)
    if period_end is not None:
        query = query.where(Finding.period_end == period_end)
    return list(session.execute(query).scalars().all())


def _peer_medians(
    session: Session, establishment: Establishment
) -> dict[str, float] | None:
    """Median daily wage across comparable establishments.

    Compared within the same state and industry classification only. Comparing a
    Bihar workshop against a Maharashtra factory would produce a gap that reflects
    geography and trade, not compliance, and an inspector chasing it would find
    nothing.
    """
    if not establishment.nic_code:
        return None

    from sqlalchemy import func

    peer_ids = (
        select(Establishment.id)
        .where(
            Establishment.nic_code == establishment.nic_code,
            Establishment.state_code == establishment.state_code,
            Establishment.id != establishment.id,
        )
        .scalar_subquery()
    )

    rows = (
        session.execute(
            select(
                func.sum(WageLine.basic_paise + func.coalesce(WageLine.da_paise, 0)),
                func.sum(WageLine.days_paid),
            ).where(
                WageLine.establishment_id.in_(peer_ids),
                WageLine.basic_paise.is_not(None),
                WageLine.days_paid.is_not(None),
                WageLine.days_paid > 0,
            )
        )
    ).one_or_none()

    if not rows or rows[0] is None or not rows[1]:
        return None

    return {"daily_wage_paise": float(rows[0]) / float(rows[1])}
