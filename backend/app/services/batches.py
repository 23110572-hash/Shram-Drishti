"""Durable establishment upload-batch orchestration.

A batch is sealed only after the browser has submitted every selected file.  The
last extraction to finish releases one establishment evaluation, preventing a
partial score while later files are still arriving.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, Job, UploadBatch, UploadBatchDocument
from app.models.enums import DocumentStatus, JobStatus
from app.models.base import utcnow

EXTRACTION_TERMINAL = {
    DocumentStatus.REJECTED,
    DocumentStatus.NEEDS_BINDING,
    DocumentStatus.EXTRACTED,
    DocumentStatus.NEEDS_REVIEW,
    DocumentStatus.VERIFIED,
    DocumentStatus.EVALUATED,
    DocumentStatus.SUPERSEDED,
    DocumentStatus.FAILED,
}
USABLE = {
    DocumentStatus.EXTRACTED,
    DocumentStatus.NEEDS_REVIEW,
    DocumentStatus.VERIFIED,
    DocumentStatus.EVALUATED,
}


def batch_documents(session: Session, batch_id: str) -> list[Document]:
    return list(
        session.execute(
            select(Document)
            .join(UploadBatchDocument, UploadBatchDocument.document_id == Document.id)
            .where(UploadBatchDocument.batch_id == batch_id)
            .order_by(UploadBatchDocument.ordinal, Document.created_at)
        )
        .scalars()
        .all()
    )


def evaluation_jobs(session: Session, batch: UploadBatch) -> list[Job]:
    jobs = list(
        session.execute(
            select(Job)
            .where(
                Job.kind == "evaluate_establishment",
                Job.subject_type == "establishment",
                Job.subject_id == batch.establishment_id,
            )
            .order_by(Job.created_at)
        )
        .scalars()
        .all()
    )
    return [job for job in jobs if (job.detail or {}).get("batch_id") == batch.id]


def maybe_release_batch(session: Session, batch_id: str) -> Job | None:
    """Release exactly one evaluation after a sealed batch fully extracts."""
    batch = session.execute(
        select(UploadBatch).where(UploadBatch.id == batch_id).with_for_update()
    ).scalar_one_or_none()
    if batch is None or batch.sealed_at is None:
        return None

    documents = batch_documents(session, batch.id)
    if not documents or any(doc.status not in EXTRACTION_TERMINAL for doc in documents):
        return None

    existing = evaluation_jobs(session, batch)
    if existing:
        return existing[-1]

    usable = [
        doc
        for doc in documents
        if doc.status in USABLE and doc.period_start is not None
    ]
    if not usable:
        batch.completed_at = utcnow()
        return None

    starts = [doc.period_start for doc in usable if doc.period_start is not None]
    ends = [doc.period_end or doc.period_start for doc in usable if doc.period_start is not None]
    period_start: date = min(starts)
    period_end: date = max(end for end in ends if end is not None)

    from app.services.jobs import enqueue_evaluation

    job = enqueue_evaluation(
        session,
        batch.establishment_id,
        period_start=period_start,
        period_end=period_end,
        actor_id=batch.uploaded_by_id,
    )
    job.detail = {**(job.detail or {}), "batch_id": batch.id}
    session.flush()
    return job


def mark_batch_complete(session: Session, batch_id: str | None) -> None:
    if not batch_id:
        return
    batch = session.get(UploadBatch, batch_id)
    if batch is not None and batch.completed_at is None:
        batch.completed_at = utcnow()
        session.flush()


def batch_id_for_document(session: Session, document_id: str) -> str | None:
    return session.execute(
        select(UploadBatchDocument.batch_id).where(
            UploadBatchDocument.document_id == document_id
        )
    ).scalar_one_or_none()
