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
    "ProseAssertion",
    "RefreshToken",
    "Registration",
    "Scorecard",
    "User",
    "WageLine",
    "WorkerIdentity",
]
