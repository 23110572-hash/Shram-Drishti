"""Uploaded documents, their pages, and background job tracking.

Every upload creates a new document row and is processed from scratch, even if
the same bytes were uploaded before. Reusing a previous result would carry
forward a bad extraction, and an employer re-uploading a file usually means the
earlier one was wrong or has been corrected.

``content_sha256`` is still recorded, but only as provenance — it answers "is
this the same file we saw last month" without changing how the document is
processed.

Pages are first-class rows because the whole pipeline is per-page: the 1 MB OCR
limit is per request, the extraction mode is chosen per page, and evidence
coordinates are page-relative.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)  # noqa: F401  UniqueConstraint used by DocumentPage
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import EnumColumn, IdMixin, JSONColumn, TimestampMixin
from app.models.enums import (
    DocumentStatus,
    DocumentType,
    ExtractionMode,
    JobStatus,
    SchemaSource,
)


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "document"
    __id_prefix__ = "doc"
    __table_args__ = (
        # No uniqueness on content: re-uploading the same file is a legitimate
        # action that must produce a fresh document and a fresh extraction.
        Index("ix_document_establishment_period", "establishment_id", "period_start"),
        Index("ix_document_status", "status"),
        Index("ix_document_org_content", "organisation_id", "content_sha256"),
    )

    # Set when an earlier upload of the same bytes exists, so the UI can say
    # "this replaces a document you uploaded on 3 March" without blocking it.
    supersedes_document_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )

    organisation_id: Mapped[str] = mapped_column(
        ForeignKey("organisation.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Null until binding succeeds. A document whose establishment cannot be
    # determined sits in NEEDS_BINDING rather than being attached to a guess.
    establishment_id: Mapped[str | None] = mapped_column(
        ForeignKey("establishment.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )

    # ------------------------------------------------------------- the bytes
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Sniffed from content, never trusted from the filename extension.
    detected_mime: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)

    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ---------------------------------------------------------- what it is
    status: Mapped[DocumentStatus] = mapped_column(
        EnumColumn(DocumentStatus, 24), default=DocumentStatus.RECEIVED, nullable=False
    )
    doc_type: Mapped[DocumentType] = mapped_column(
        EnumColumn(DocumentType, 48),
        default=DocumentType.UNKNOWN,
        nullable=False,
        index=True,
    )
    doc_type_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    schema_source: Mapped[SchemaSource | None] = mapped_column(
        EnumColumn(SchemaSource, 16), nullable=True
    )
    extraction_mode: Mapped[ExtractionMode | None] = mapped_column(
        EnumColumn(ExtractionMode, 24), nullable=True
    )

    # Reporting period the document covers, e.g. a wage month.
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ------------------------------------------------------------- outcomes
    rejection_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    review_reasons: Mapped[list[str]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )
    contains_redacted_pii: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentPage.page_number",
    )

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            DocumentStatus.REJECTED,
            DocumentStatus.FAILED,
            DocumentStatus.SUPERSEDED,
        }


class DocumentPage(IdMixin, TimestampMixin, Base):
    """One page, with its OCR result and reading provenance."""

    __tablename__ = "document_page"
    __id_prefix__ = "pag"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_page_document_number"),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Rendered image, if this page had to be rasterised for OCR or the model.
    image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_dpi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    extraction_mode: Mapped[ExtractionMode | None] = mapped_column(
        EnumColumn(ExtractionMode, 24), nullable=True
    )

    # ------------------------------------------------------------------ OCR
    ocr_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ocr_engine: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Engine 3 returns tables as Markdown, which is a far better model input
    # than positional text soup, so it is kept separately when available.
    ocr_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Word boxes: [{"text","left","top","width","height","line"}] normalised 0-1.
    # These are what let an inspector see the exact cell on the scan.
    ocr_tokens: Mapped[list[dict]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )
    ocr_failed_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    document: Mapped[Document] = relationship(back_populates="pages")

    @property
    def has_coordinates(self) -> bool:
        """False for Mode C pages, where evidence degrades to page level."""
        return bool(self.ocr_tokens)


class Job(IdMixin, TimestampMixin, Base):
    """Background work tracking.

    Exists because the pipeline runs off the request thread via FastAPI
    BackgroundTasks, which is fire-and-forget. Without a row per job there is no
    way to answer "is my document still processing, or did it fail silently".
    """

    __tablename__ = "job"
    __id_prefix__ = "job"
    __table_args__ = (Index("ix_job_subject", "subject_type", "subject_id"),)

    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(48), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(40), nullable=False)

    status: Mapped[JobStatus] = mapped_column(
        EnumColumn(JobStatus, 16), default=JobStatus.QUEUED, nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict] = mapped_column(JSONColumn, default=dict, nullable=False)
