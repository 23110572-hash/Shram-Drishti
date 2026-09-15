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
from app.models.enums import DocumentStatus, DocumentType, JobStatus
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


#: Documents whose dates describe the wage period being assessed. Certificates,
#: appointment letters and standing orders carry joining or validity dates
#: instead, so including them would stretch one month into several years.
PERIOD_BEARING = {
    DocumentType.WAGE_REGISTER,
    DocumentType.WAGE_SLIP,
    DocumentType.MUSTER_ROLL,
    DocumentType.LEAVE_REGISTER,
    DocumentType.OVERTIME_REGISTER,
    DocumentType.DEDUCTION_REGISTER,
    DocumentType.EPF_ECR,
    DocumentType.ESIC_CHALLAN,
    DocumentType.EMPLOYEE_REGISTER,
}


def _assessment_period(documents: list[Document]) -> tuple[date | None, date | None]:
    """The wage period the uploaded payroll records actually cover.

    Grouped rather than spanned. Taking the earliest start and latest end across
    every document produced a multi-year "wage period", which then reported a
    compliant employer for a wage period longer than one month.
    """
    groups: dict[tuple[date, date], int] = {}
    for document in documents:
        if document.period_start is None:
            continue
        if document.doc_type not in PERIOD_BEARING:
            continue
        key = (document.period_start, document.period_end or document.period_start)
        groups[key] = groups.get(key, 0) + 1

    if not groups:
        dated = [doc for doc in documents if doc.period_start is not None]
        if not dated:
            return None, None
        latest = max(dated, key=lambda doc: doc.period_start)
        return latest.period_start, latest.period_end or latest.period_start

    # Most corroborated period first, then the most recent of any tie.
    best = sorted(groups.items(), key=lambda item: (item[1], item[0][1]), reverse=True)[0]
    return best[0][0], best[0][1]


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

    period_start, period_end = _assessment_period(usable)
    if period_start is None or period_end is None:
        batch.completed_at = utcnow()
        return None

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
