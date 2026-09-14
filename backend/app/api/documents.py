"""Document upload, status and evidence endpoints."""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from starlette.concurrency import run_in_threadpool

from app.deps import Access, CurrentUser, DbSession, client_ip, require_roles
from app.models.document import Document, DocumentPage, Job
from app.models.enums import (
    AuditAction,
    DocumentStatus,
    DocumentType,
    ExtractionMode,
    Role,
    SchemaSource,
)
from app.models.establishment import Establishment
from app.models.extraction import ExtractedField
from app.services import audit as audit_service
from app.services import jobs as job_service
from app.services import upload_guard
from app.services.storage import get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# ------------------------------------------------------------------- schemas
class DocumentSummary(BaseModel):
    id: str
    original_filename: str
    doc_type: DocumentType
    doc_type_confidence: float | None
    status: DocumentStatus
    extraction_mode: ExtractionMode | None
    schema_source: SchemaSource | None
    establishment_id: str | None
    establishment_name: str | None
    period_start: date | None
    period_end: date | None
    page_count: int
    byte_size: int
    has_text_layer: bool
    review_reason_count: int
    contains_redacted_pii: bool
    uploaded_at: str
    processed_at: str | None

    @property
    def needs_attention(self) -> bool:
        return self.status in {
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.NEEDS_BINDING,
            DocumentStatus.FAILED,
            DocumentStatus.REJECTED,
        }


class PageSummary(BaseModel):
    page_number: int
    extraction_mode: ExtractionMode | None
    has_image: bool
    has_coordinates: bool
    image_width: int | None
    image_height: int | None
    ocr_provider: str | None
    ocr_failed_reason: str | None
    text_preview: str | None


class ExtractedFieldOut(BaseModel):
    name: str
    value_text: str | None
    value_number: int | None
    value_date: date | None
    source_page: int | None
    source_bbox: list[float] | None
    agreement: str | None
    needs_review: bool


class DocumentDetail(DocumentSummary):
    review_reasons: list[str]
    rejection_reason: str | None
    pages: list[PageSummary]
    fields: list[ExtractedFieldOut]
    row_counts: dict[str, int]
    latest_job: dict[str, Any] | None


class UploadResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    message: str
    supersedes_document_id: str | None = None


class BindRequest(BaseModel):
    establishment_id: str
    period_start: date
    period_end: date
    doc_type: DocumentType | None = None
    reason: str = Field(min_length=3, max_length=512)


# -------------------------------------------------------------------- upload
@router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(Role.EMPLOYER, Role.INSPECTOR, Role.ADMIN))],
)
async def upload_document(
    session: DbSession,
    user: CurrentUser,
    ip: Annotated[str | None, Depends(client_ip)],
    file: Annotated[UploadFile, File(description="PDF, image, or structured text")],
    establishment_id: Annotated[str | None, Form()] = None,
) -> UploadResponse:
    """Accept a document and queue it for reading.

    Returns 202 rather than waiting. OCR and model calls over a fifty-page muster
    roll take minutes, and an HTTP request that blocks for minutes will be killed
    by a proxy long before it finishes.
    """
    store = get_store()

    # Written to storage first so validation can inspect real bytes. Sniffing type
    # from a filename is how a parser exploit gets reached, and page count cannot
    # be checked without opening the file.
    stored = await run_in_threadpool(
        store.put_stream,
        file.file,
        prefix="uploads",
        suffix=_suffix(file.filename),
    )

    try:
        inspection = await run_in_threadpool(
            upload_guard.inspect,
            store._path(stored.key),  # noqa: SLF001  the guard needs a real path
            original_filename=file.filename or "upload",
            byte_size=stored.byte_size,
        )
    except upload_guard.UploadRejected as exc:
        document = Document(
            organisation_id=user.organisation_id,
            uploaded_by_id=user.id,
            original_filename=(file.filename or "upload")[:512],
            content_sha256=stored.sha256,
            byte_size=stored.byte_size,
            detected_mime="application/octet-stream",
            storage_key=stored.key,
            status=DocumentStatus.REJECTED,
            rejection_reason=f"{exc.code.value}: {exc.message}",
        )
        session.add(document)
        session.flush()

        audit_service.record(
            session,
            action=AuditAction.DOCUMENT_REJECTED,
            subject_type="document",
            subject_id=document.id,
            actor_id=user.id,
            actor_role=str(user.role),
            actor_ip=ip,
            detail={"code": exc.code.value, "reason": exc.message},
        )
        session.commit()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code.value, "message": exc.message},
        ) from exc

    # An earlier upload of identical bytes is recorded as provenance and nothing
    # more. Reusing its extraction would carry forward whatever was wrong with it,
    # and a re-upload almost always means the earlier read was wrong or the file
    # has been corrected.
    previous = session.execute(
        select(Document)
        .where(
            Document.organisation_id == user.organisation_id,
            Document.content_sha256 == stored.sha256,
            Document.status != DocumentStatus.REJECTED,
        )
        .order_by(desc(Document.created_at))
        .limit(1)
    ).scalar_one_or_none()

    bound_establishment_id: str | None = None
    if establishment_id:
        establishment = session.get(Establishment, establishment_id)
        if establishment is None:
            raise HTTPException(status_code=404, detail="establishment not found")
        if establishment.organisation_id != user.organisation_id and user.role is not Role.ADMIN:
            # 404 rather than 403: confirming existence would leak which
            # establishments belong to other employers.
            raise HTTPException(status_code=404, detail="establishment not found")
        bound_establishment_id = establishment.id

    document = Document(
        organisation_id=user.organisation_id,
        establishment_id=bound_establishment_id,
        uploaded_by_id=user.id,
        original_filename=(file.filename or "upload")[:512],
        content_sha256=stored.sha256,
        byte_size=stored.byte_size,
        detected_mime=inspection.mime_type,
        storage_key=stored.key,
        page_count=inspection.page_count,
        has_text_layer=inspection.has_text_layer,
        status=DocumentStatus.RECEIVED,
        supersedes_document_id=previous.id if previous else None,
    )
    session.add(document)
    session.flush()

    audit_service.record(
        session,
        action=AuditAction.DOCUMENT_UPLOADED,
        subject_type="document",
        subject_id=document.id,
        actor_id=user.id,
        actor_role=str(user.role),
        actor_ip=ip,
        establishment_id=bound_establishment_id,
        detail={
            "filename": document.original_filename,
            "mime": inspection.mime_type,
            "bytes": stored.byte_size,
            "pages": inspection.page_count,
            "has_text_layer": inspection.has_text_layer,
            "supersedes": previous.id if previous else None,
        },
    )
    job_service.enqueue_document(session, document.id)
    session.commit()

    message = "Received. The document is queued and will be read in order."

    return UploadResponse(
        document_id=document.id,
        status=document.status,
        message=message,
        supersedes_document_id=previous.id if previous else None,
    )


def _suffix(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ".bin"
    return "." + filename.rsplit(".", 1)[-1].lower()[:8]


# ---------------------------------------------------------------------- list
@router.get("", response_model=list[DocumentSummary])
def list_documents(
    session: DbSession,
    user: CurrentUser,
    access: Access,
    establishment_id: Annotated[str | None, Query()] = None,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    doc_type: Annotated[DocumentType | None, Query()] = None,
    needs_attention: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentSummary]:
    query = select(Document).order_by(desc(Document.created_at))

    if user.role is Role.EMPLOYER:
        query = query.where(Document.organisation_id == user.organisation_id)
    elif user.role in {Role.INSPECTOR, Role.ANALYST}:
        # An empty jurisdiction list means no scope, therefore no rows. Treating
        # empty as "everything" would give a half-provisioned account national
        # reach.
        scoped = _establishment_ids_in_scope(session, user)
        if not scoped:
            return []
        query = query.where(Document.establishment_id.in_(scoped))

    if establishment_id:
        establishment = session.get(Establishment, establishment_id)
        if establishment is None:
            raise HTTPException(status_code=404, detail="establishment not found")
        access.assert_can_access(establishment)
        query = query.where(Document.establishment_id == establishment_id)

    if status_filter:
        query = query.where(Document.status == status_filter)
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    if needs_attention:
        query = query.where(
            Document.status.in_(
                [
                    DocumentStatus.NEEDS_REVIEW,
                    DocumentStatus.NEEDS_BINDING,
                    DocumentStatus.FAILED,
                ]
            )
        )

    documents = list(
        session.execute(query.limit(limit).offset(offset)).scalars().all()
    )
    names = _establishment_names(session, documents)
    return [_summary(d, names) for d in documents]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: str,
    session: DbSession,
    user: CurrentUser,
    access: Access,
    ip: Annotated[str | None, Depends(client_ip)],
) -> DocumentDetail:
    document = _load(session, document_id, user, access)

    pages = (
        session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document.id)
            .order_by(DocumentPage.page_number)
        )
        .scalars()
        .all()
    )
    fields = (
        session.execute(
            select(ExtractedField)
            .where(ExtractedField.document_id == document.id)
            .order_by(ExtractedField.name)
        )
        .scalars()
        .all()
    )
    job = session.execute(
        select(Job)
        .where(Job.subject_type == "document", Job.subject_id == document.id)
        .order_by(desc(Job.created_at))
        .limit(1)
    ).scalar_one_or_none()

    # Reading a document means reading worker records, which DPDP requires to be
    # logged with a purpose rather than merely permitted.
    audit_service.record(
        session,
        action=AuditAction.DOCUMENT_ACCESSED,
        subject_type="document",
        subject_id=document.id,
        actor_id=user.id,
        actor_role=str(user.role),
        actor_ip=ip,
        establishment_id=document.establishment_id,
        purpose="compliance review",
    )
    session.commit()

    names = _establishment_names(session, [document])
    summary = _summary(document, names)

    return DocumentDetail(
        **summary.model_dump(),
        review_reasons=list(document.review_reasons or []),
        rejection_reason=document.rejection_reason,
        pages=[
            PageSummary(
                page_number=p.page_number,
                extraction_mode=p.extraction_mode,
                has_image=bool(p.image_key),
                has_coordinates=bool(p.ocr_tokens),
                image_width=p.image_width,
                image_height=p.image_height,
                ocr_provider=p.ocr_provider,
                ocr_failed_reason=p.ocr_failed_reason,
                text_preview=(p.ocr_text or "")[:400] or None,
            )
            for p in pages
        ],
        fields=[
            ExtractedFieldOut(
                name=f.name,
                value_text=f.value_text,
                value_number=f.value_number,
                value_date=f.value_date,
                source_page=f.source_page,
                source_bbox=f.source_bbox,
                agreement=f.agreement,
                needs_review=f.needs_review,
            )
            for f in fields
        ],
        row_counts=_row_counts(session, document.id),
        latest_job=(
            {
                "id": job.id,
                "status": str(job.status),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "error": job.error,
                "detail": job.detail,
            }
            if job
            else None
        ),
    )


@router.get("/{document_id}/pages/{page_number}/image")
def get_page_image(
    document_id: str,
    page_number: int,
    session: DbSession,
    user: CurrentUser,
    access: Access,
) -> Response:
    """Serve a page image for the evidence viewer.

    Streamed through the API rather than exposed as a static URL, so access stays
    subject to the same establishment scoping as everything else. A page image is
    a worker's pay record.
    """
    document = _load(session, document_id, user, access)

    page = session.execute(
        select(DocumentPage).where(
            DocumentPage.document_id == document.id,
            DocumentPage.page_number == page_number,
        )
    ).scalar_one_or_none()

    if page is None or not page.image_key:
        raise HTTPException(status_code=404, detail="page image not available")

    store = get_store()
    if not store.exists(page.image_key):
        raise HTTPException(status_code=404, detail="page image not available")

    return Response(
        content=store.read(page.image_key),
        media_type="image/jpeg",
        headers={
            # Private: these are worker pay records and must not sit in a shared
            # proxy cache.
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/{document_id}/pages/{page_number}/tokens")
def get_page_tokens(
    document_id: str,
    page_number: int,
    session: DbSession,
    user: CurrentUser,
    access: Access,
) -> dict[str, Any]:
    """OCR word boxes for a page, for overlaying evidence on the scan."""
    document = _load(session, document_id, user, access)

    page = session.execute(
        select(DocumentPage).where(
            DocumentPage.document_id == document.id,
            DocumentPage.page_number == page_number,
        )
    ).scalar_one_or_none()

    if page is None:
        raise HTTPException(status_code=404, detail="page not found")

    return {
        "page_number": page.page_number,
        "width": page.image_width,
        "height": page.image_height,
        "extraction_mode": str(page.extraction_mode) if page.extraction_mode else None,
        "tokens": list(page.ocr_tokens or []),
        "note": (
            None
            if page.ocr_tokens
            else "this page was read without positional data, so evidence can only "
            "be shown at page level"
        ),
    }


# ------------------------------------------------------------------- actions
@router.post("/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
def reprocess_document(
    document_id: str,
    session: DbSession,
    user: CurrentUser,
    access: Access,
) -> dict[str, str]:
    """Read a document again from its stored bytes.

    Everything previously extracted from it is discarded first. That is the point:
    reprocessing happens because the earlier read was wrong, and merging a
    corrected read with a bad one leaves rows nobody can tell apart.
    """
    document = _load(session, document_id, user, access)

    if document.status is DocumentStatus.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this document was rejected at upload and has nothing to reprocess",
        )
    if job_service.has_active_document_job(session, document.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this document is already queued or being read",
        )

    document.status = DocumentStatus.RECEIVED
    document.review_reasons = []
    document.rejection_reason = None
    document.processed_at = None
    job_service.enqueue_document(session, document.id)
    session.commit()

    return {"document_id": document.id, "status": "queued"}


@router.post(
    "/{document_id}/bind",
    response_model=DocumentSummary,
    dependencies=[Depends(require_roles(Role.EMPLOYER, Role.INSPECTOR, Role.ADMIN))],
)
def bind_document(
    document_id: str,
    payload: BindRequest,
    session: DbSession,
    user: CurrentUser,
    access: Access,
    ip: Annotated[str | None, Depends(client_ip)],
) -> DocumentSummary:
    """Attach a document to an establishment and period by hand.

    The manual path for documents the automated binder declined to place. It
    declining is a feature: a wage register attached to the wrong employer
    produces findings against a business that never filed it.
    """
    document = _load(session, document_id, user, access)

    establishment = session.get(Establishment, payload.establishment_id)
    if establishment is None:
        raise HTTPException(status_code=404, detail="establishment not found")
    access.assert_can_access(establishment)

    if payload.period_end < payload.period_start:
        raise HTTPException(
            status_code=422, detail="the period ends before it begins"
        )

    document.establishment_id = establishment.id
    document.period_start = payload.period_start
    document.period_end = payload.period_end
    if payload.doc_type is not None:
        document.doc_type = payload.doc_type
        document.doc_type_confidence = 1.0
    document.status = DocumentStatus.RECEIVED
    document.review_reasons = []

    audit_service.record(
        session,
        action=AuditAction.EXTRACTION_CORRECTED,
        subject_type="document",
        subject_id=document.id,
        actor_id=user.id,
        actor_role=str(user.role),
        actor_ip=ip,
        establishment_id=establishment.id,
        detail={
            "action": "manual_binding",
            "establishment_id": establishment.id,
            "period_start": payload.period_start.isoformat(),
            "period_end": payload.period_end.isoformat(),
            "doc_type": str(payload.doc_type) if payload.doc_type else None,
            "reason": payload.reason,
        },
    )
    job_service.enqueue_document(session, document.id)
    session.commit()

    names = _establishment_names(session, [document])
    return _summary(document, names)


# -------------------------------------------------------------------- helpers
def _load(
    session: DbSession, document_id: str, user: CurrentUser, access: Access
) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")

    if user.role is Role.EMPLOYER:
        if document.organisation_id != user.organisation_id:
            raise HTTPException(status_code=404, detail="document not found")
        return document

    if user.role is Role.ADMIN:
        return document

    # Inspectors and analysts are scoped by jurisdiction, which is a property of
    # the establishment. An unbound document has no jurisdiction yet, so it is not
    # theirs to see.
    if document.establishment_id is None:
        raise HTTPException(status_code=404, detail="document not found")

    establishment = session.get(Establishment, document.establishment_id)
    if establishment is None:
        raise HTTPException(status_code=404, detail="document not found")
    access.assert_can_access(establishment)
    return document


def _establishment_ids_in_scope(session: DbSession, user: CurrentUser) -> list[str]:
    jurisdictions = set(user.jurisdictions or [])
    if not jurisdictions:
        return []
    state_codes = [j.split("/", 1)[1] for j in jurisdictions if "/" in j]
    if not state_codes:
        return []
    return list(
        session.execute(
            select(Establishment.id).where(Establishment.state_code.in_(state_codes))
        )
        .scalars()
        .all()
    )


def _establishment_names(
    session: DbSession, documents: list[Document]
) -> dict[str, str]:
    ids = {d.establishment_id for d in documents if d.establishment_id}
    if not ids:
        return {}
    return dict(
        session.execute(
            select(Establishment.id, Establishment.name).where(
                Establishment.id.in_(ids)
            )
        ).all()
    )


def _summary(document: Document, names: dict[str, str]) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        original_filename=document.original_filename,
        doc_type=document.doc_type,
        doc_type_confidence=document.doc_type_confidence,
        status=document.status,
        extraction_mode=document.extraction_mode,
        schema_source=document.schema_source,
        establishment_id=document.establishment_id,
        establishment_name=(
            names.get(document.establishment_id) if document.establishment_id else None
        ),
        period_start=document.period_start,
        period_end=document.period_end,
        page_count=document.page_count,
        byte_size=document.byte_size,
        has_text_layer=document.has_text_layer,
        review_reason_count=len(document.review_reasons or []),
        contains_redacted_pii=document.contains_redacted_pii,
        uploaded_at=document.created_at.isoformat() if document.created_at else "",
        processed_at=document.processed_at.isoformat() if document.processed_at else None,
    )


def _row_counts(session: DbSession, document_id: str) -> dict[str, int]:
    from sqlalchemy import func

    from app.models.extraction import (
        AttendanceRecord,
        ContributionLine,
        IncidentRecord,
        ProseAssertion,
        WageLine,
    )

    counts: dict[str, int] = {}
    for label, model in (
        ("wage_lines", WageLine),
        ("attendance_records", AttendanceRecord),
        ("contribution_lines", ContributionLine),
        ("incidents", IncidentRecord),
        ("prose_assertions", ProseAssertion),
    ):
        counts[label] = int(
            session.execute(
                select(func.count())
                .select_from(model)
                .where(model.document_id == document_id)
            ).scalar_one()
        )
    return counts
