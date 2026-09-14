"""Database-backed, single-concurrency pipeline worker.

Upload requests only commit QUEUED jobs. One worker claims those jobs from
Postgres and processes them serially, so a batch cannot multiply OCR/PDF/LLM
memory on a small Render instance. A database row lock also prevents a rolling
deployment from running a second worker at the same time.
"""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.models.base import utcnow
from app.models.document import Document, Job
from app.models.enums import DocumentStatus, JobStatus
from app.models.infrastructure import PipelineMutex
from app.services.storage import get_store

logger = logging.getLogger(__name__)

PROCESS_DOCUMENT = "process_document"
EVALUATE_ESTABLISHMENT = "evaluate_establishment"
_KINDS = (PROCESS_DOCUMENT, EVALUATE_ESTABLISHMENT)
_MUTEX_NAME = "document_pipeline"
_POLL_SECONDS = 2.0

_worker: _PipelineWorker | None = None
_worker_guard = threading.Lock()


def has_active_document_job(session: Session, document_id: str) -> bool:
    return session.execute(
        select(Job.id).where(
            Job.kind == PROCESS_DOCUMENT,
            Job.subject_type == "document",
            Job.subject_id == document_id,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        ).limit(1)
    ).scalar_one_or_none() is not None


def enqueue_document(session: Session, document_id: str) -> Job:
    """Create the durable queue row in the caller's transaction."""
    existing = session.execute(
        select(Job).where(
            Job.kind == PROCESS_DOCUMENT,
            Job.subject_type == "document",
            Job.subject_id == document_id,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        ).order_by(Job.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    job = Job(
        kind=PROCESS_DOCUMENT,
        subject_type="document",
        subject_id=document_id,
        status=JobStatus.QUEUED,
        attempts=0,
    )
    session.add(job)
    session.flush()
    wake_worker()
    return job


def enqueue_evaluation(
    session: Session,
    establishment_id: str,
    *,
    period_start: date,
    period_end: date,
    actor_id: str | None = None,
) -> Job:
    """Queue one evaluation per establishment/period, coalescing a document batch."""
    detail = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "actor_id": actor_id,
    }
    queued = session.execute(
        select(Job).where(
            Job.kind == EVALUATE_ESTABLISHMENT,
            Job.subject_type == "establishment",
            Job.subject_id == establishment_id,
            Job.status == JobStatus.QUEUED,
        ).order_by(Job.created_at.desc())
    ).scalars().all()
    for job in queued:
        if (
            (job.detail or {}).get("period_start") == detail["period_start"]
            and (job.detail or {}).get("period_end") == detail["period_end"]
        ):
            if actor_id:
                job.detail = {**(job.detail or {}), "actor_id": actor_id}
            return job

    job = Job(
        kind=EVALUATE_ESTABLISHMENT,
        subject_type="establishment",
        subject_id=establishment_id,
        status=JobStatus.QUEUED,
        attempts=0,
        detail=detail,
    )
    session.add(job)
    session.flush()
    wake_worker()
    return job


def start_worker() -> None:
    global _worker
    with _worker_guard:
        if _worker is not None:
            return
        _worker = _PipelineWorker()
        _worker.start()


def stop_worker() -> None:
    global _worker
    with _worker_guard:
        worker = _worker
        _worker = None
    if worker is not None:
        worker.stop()


def wake_worker() -> None:
    worker = _worker
    if worker is not None:
        worker.wake()


class _PipelineWorker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="pipeline-worker",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()
        logger.info("pipeline worker started", extra={"concurrency": 1})

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=2.0)
        logger.info("pipeline worker stopping")

    def wake(self) -> None:
        self._wake.set()

    def _ensure_mutex_row(self) -> None:
        factory = get_session_factory()
        with factory() as session:
            if session.get(PipelineMutex, _MUTEX_NAME) is not None:
                return
            session.add(PipelineMutex(name=_MUTEX_NAME))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()

    def _run(self) -> None:
        while not self._stop.is_set():
            worked = False
            try:
                self._ensure_mutex_row()
                worked = self._run_one()
            except Exception:
                logger.exception("pipeline worker cycle failed")
            if not worked:
                self._wake.wait(_POLL_SECONDS)
                self._wake.clear()

    def _run_one(self) -> bool:
        factory = get_session_factory()

        # Hold this row lock for the duration of one expensive job. A new Render
        # instance during a rolling deploy skips it instead of processing in
        # parallel. Process death releases the transaction and lock automatically.
        with factory() as lock_session:
            mutex = lock_session.execute(
                select(PipelineMutex)
                .where(PipelineMutex.name == _MUTEX_NAME)
                .with_for_update(skip_locked=True)
            ).scalar_one_or_none()
            if mutex is None:
                lock_session.rollback()
                return False

            self._recover_interrupted()
            claimed = self._claim_next()
            if claimed is None:
                lock_session.commit()
                return False

            job_id, kind, subject_id, detail = claimed
            try:
                self._execute(job_id, kind, subject_id, detail)
            except Exception as exc:  # final guard; pipeline normally records its own failure
                logger.exception("queued pipeline job crashed", extra={"job_id": job_id})
                self._mark_job_failed(job_id, f"unexpected worker error: {exc}")
            finally:
                lock_session.commit()
            return True

    def _recover_interrupted(self) -> None:
        factory = get_session_factory()
        with factory() as session:
            running = session.execute(
                select(Job).where(Job.kind.in_(_KINDS), Job.status == JobStatus.RUNNING)
            ).scalars().all()
            for job in running:
                job.status = JobStatus.QUEUED
                job.started_at = None
                job.finished_at = None
                job.error = None
                job.detail = {
                    **(job.detail or {}),
                    "restart_recoveries": int((job.detail or {}).get("restart_recoveries", 0)) + 1,
                }

            active_document_ids = set(
                session.execute(
                    select(Job.subject_id).where(
                        Job.kind == PROCESS_DOCUMENT,
                        Job.subject_type == "document",
                        Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                    )
                ).scalars().all()
            )
            interrupted = session.execute(
                select(Document).where(
                    Document.status.in_([
                        DocumentStatus.RECEIVED,
                        DocumentStatus.NORMALISED,
                        DocumentStatus.CLASSIFIED,
                    ])
                )
            ).scalars().all()

            store = get_store()
            for document in interrupted:
                if (document.rejection_reason or "").startswith("superseded by"):
                    document.status = DocumentStatus.SUPERSEDED
                    continue

                if not store.exists(document.storage_key):
                    document.status = DocumentStatus.FAILED
                    document.rejection_reason = (
                        "Processing was interrupted before durable storage was enabled. "
                        "Please submit this file again."
                    )
                    for job in session.execute(
                        select(Job).where(
                            Job.kind == PROCESS_DOCUMENT,
                            Job.subject_id == document.id,
                            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                        )
                    ).scalars().all():
                        job.status = JobStatus.FAILED
                        job.finished_at = utcnow()
                        job.error = document.rejection_reason
                    continue

                document.status = DocumentStatus.RECEIVED
                if document.id not in active_document_ids:
                    enqueue_document(session, document.id)

            session.commit()

    def _claim_next(self) -> tuple[str, str, str, dict[str, Any]] | None:
        factory = get_session_factory()
        with factory() as session:
            job = session.execute(
                select(Job)
                .where(Job.kind.in_(_KINDS), Job.status == JobStatus.QUEUED)
                .order_by(
                    case((Job.kind == PROCESS_DOCUMENT, 0), else_=1),
                    Job.created_at,
                    Job.id,
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            ).scalar_one_or_none()
            if job is None:
                session.rollback()
                return None

            job.status = JobStatus.RUNNING
            job.attempts = (job.attempts or 0) + 1
            job.started_at = utcnow()
            job.finished_at = None
            job.error = None
            session.commit()
            return job.id, job.kind, job.subject_id, dict(job.detail or {})

    @staticmethod
    def _execute(job_id: str, kind: str, subject_id: str, detail: dict[str, Any]) -> None:
        from app.services import pipeline

        if kind == PROCESS_DOCUMENT:
            pipeline.process_document(job_id, subject_id)
            return
        if kind == EVALUATE_ESTABLISHMENT:
            pipeline.evaluate_establishment(
                job_id,
                subject_id,
                period_start=date.fromisoformat(detail["period_start"]),
                period_end=date.fromisoformat(detail["period_end"]),
                actor_id=detail.get("actor_id"),
            )
            return
        raise ValueError(f"unsupported job kind: {kind}")

    @staticmethod
    def _mark_job_failed(job_id: str, error: str) -> None:
        with get_session_factory()() as session:
            job = session.get(Job, job_id)
            if job is not None and job.status == JobStatus.RUNNING:
                job.status = JobStatus.FAILED
                job.finished_at = utcnow()
                job.error = error[:2000]
                session.commit()
