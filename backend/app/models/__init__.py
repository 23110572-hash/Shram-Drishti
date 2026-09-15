"""Model package.

Every model module must be imported here so Alembic autogenerate and
``Base.metadata.create_all`` see the complete metadata. A model that is not
imported is invisible to migrations, which produces silently missing tables.
"""

from __future__ import annotations

from app.models.audit import AuditEntry
from app.models.document import Document, DocumentPage, Job
from app.models.establishment import (
    Contractor,
    Establishment,
    MinimumWageRate,
    Registration,
)
from app.models.extraction import (
    AttendanceRecord,
    ContributionLine,
    ExtractedField,
    IncidentRecord,
    ProseAssertion,
    WageLine,
    WorkerIdentity,
)
from app.models.finding import Finding, FindingEvidence, Scorecard
from app.models.infrastructure import PipelineMutex
from app.models.user import Organisation, RefreshToken, User

__all__ = [
    "AttendanceRecord",
    "AuditEntry",
    "Contractor",
    "ContributionLine",
    "Document",
    "DocumentPage",
    "Establishment",
    "ExtractedField",
    "Finding",
    "FindingEvidence",
    "IncidentRecord",
    "Job",
    "MinimumWageRate",
    "Organisation",
    "PipelineMutex",
    "ProseAssertion",
    "RefreshToken",
    "Registration",
    "Scorecard",
    "User",
    "WageLine",
    "WorkerIdentity",
]

# Durable upload-batch tables (imported so metadata.create_all sees them).
from app.models.document import UploadBatch, UploadBatchDocument  # noqa: F401,E402
