"""Domain enumerations.

These are stored as strings, not integers. A database row that reads
``severity='HIGH'`` is auditable by a labour officer reading raw SQL; a row
reading ``severity=3`` is not.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Who a user is, which decides what they can see and do."""

    EMPLOYER = "EMPLOYER"
    """Uploads documents for their own establishments, sees their own findings."""

    INSPECTOR = "INSPECTOR"
    """Inspector-cum-Facilitator. Reads assigned jurisdiction, overrides findings."""

    ADMIN = "ADMIN"
    """Manages rule packs, thresholds, users."""

    ANALYST = "ANALYST"
    """Read-only aggregate dashboards. No access to individual worker records."""


class LabourCode(StrEnum):
    """The four Codes. Used to group rules and score sub-totals."""

    WAGES = "WAGES"
    INDUSTRIAL_RELATIONS = "INDUSTRIAL_RELATIONS"
    SOCIAL_SECURITY = "SOCIAL_SECURITY"
    OSH = "OSH"


class Severity(StrEnum):
    """How serious a finding is. Drives weighting in the scorecard."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class FindingKind(StrEnum):
    """Which of the four PS5 check categories produced this finding.

    Kept distinct because they carry different evidentiary weight. A
    non-compliance cites a statutory section; an anomaly is only a hint.
    """

    MISSING_FIELD = "MISSING_FIELD"
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    DISCREPANCY = "DISCREPANCY"
    NON_COMPLIANCE = "NON_COMPLIANCE"
    ANOMALY = "ANOMALY"
    """Advisory only. Never scored, never presented as a legal conclusion."""


class FindingStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"
    WAIVED = "WAIVED"
    """Set aside by an inspector with a recorded reason."""

    FALSE_POSITIVE = "FALSE_POSITIVE"


class RiskBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SkillCategory(StrEnum):
    """Minimum wage categories as published in state notifications."""

    UNSKILLED = "UNSKILLED"
    SEMI_SKILLED = "SEMI_SKILLED"
    SKILLED = "SKILLED"
    HIGHLY_SKILLED = "HIGHLY_SKILLED"


class WageRateSource(StrEnum):
    """Provenance of a minimum wage figure.

    The distinction is legally material: a finding raised against a reference
    table must not be presented with the same authority as one raised against
    an official state notification.
    """

    NOTIFIED = "NOTIFIED"
    """Transcribed from an official state government notification."""

    REFERENCE = "REFERENCE"
    """From a secondary aggregated table. Indicative only."""


class DocumentType(StrEnum):
    """The document universe an inspection touches."""

    EMPLOYEE_REGISTER = "EMPLOYEE_REGISTER"
    WAGE_REGISTER = "WAGE_REGISTER"
    MUSTER_ROLL = "MUSTER_ROLL"
    WAGE_SLIP = "WAGE_SLIP"
    OVERTIME_REGISTER = "OVERTIME_REGISTER"
    DEDUCTION_REGISTER = "DEDUCTION_REGISTER"
    EPF_ECR = "EPF_ECR"
    ESIC_CHALLAN = "ESIC_CHALLAN"
    APPOINTMENT_LETTER = "APPOINTMENT_LETTER"
    ESTABLISHMENT_REGISTRATION = "ESTABLISHMENT_REGISTRATION"
    CONTRACTOR_LICENCE = "CONTRACTOR_LICENCE"
    BOCW_CESS_RECEIPT = "BOCW_CESS_RECEIPT"
    ACCIDENT_REGISTER = "ACCIDENT_REGISTER"
    HEALTH_CHECKUP_RECORD = "HEALTH_CHECKUP_RECORD"
    WELFARE_FACILITY_RECORD = "WELFARE_FACILITY_RECORD"
    STANDING_ORDERS = "STANDING_ORDERS"
    GRIEVANCE_COMMITTEE_RECORD = "GRIEVANCE_COMMITTEE_RECORD"
    LEAVE_REGISTER = "LEAVE_REGISTER"
    ANNUAL_RETURN = "ANNUAL_RETURN"
    UNKNOWN = "UNKNOWN"
    """Classification could not decide. Routed to human binding, never guessed."""


class DocumentStatus(StrEnum):
    """Document lifecycle. Transitions are enforced in code and audited."""

    RECEIVED = "RECEIVED"
    REJECTED = "REJECTED"
    NORMALISED = "NORMALISED"
    CLASSIFIED = "CLASSIFIED"
    NEEDS_BINDING = "NEEDS_BINDING"
    """Establishment or period could not be determined from the document."""

    EXTRACTED = "EXTRACTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    """A safety check failed or sources disagreed. Awaiting a human."""

    VERIFIED = "VERIFIED"
    EVALUATED = "EVALUATED"
    FAILED = "FAILED"


class ExtractionMode(StrEnum):
    """Which reading path produced a document's data.

    Recorded per document because it determines evidence quality: only modes A
    and B yield cell-level coordinates.
    """

    NATIVE_PDF = "NATIVE_PDF"
    """Mode A. Text layer read directly. No OCR, no model, exact."""

    OCR_PLUS_VISION = "OCR_PLUS_VISION"
    """Mode B. OCR text and page image sent to the model together. Default."""

    VISION_ONLY = "VISION_ONLY"
    """Mode C. OCR unavailable. Page-level evidence only."""


class SchemaSource(StrEnum):
    """Whether an extraction schema follows an official prescribed form."""

    PRESCRIBED = "PRESCRIBED"
    """Matches a form scheduled under the Rules."""

    INFERRED = "INFERRED"
    """Built from what the Act requires plus common real-world layouts."""


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class AuditAction(StrEnum):
    """Actions written to the hash-chained audit log."""

    USER_LOGIN = "USER_LOGIN"
    USER_LOGIN_FAILED = "USER_LOGIN_FAILED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_ACCESSED = "DOCUMENT_ACCESSED"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED"
    EXTRACTION_CORRECTED = "EXTRACTION_CORRECTED"
    FINDING_CREATED = "FINDING_CREATED"
    FINDING_STATUS_CHANGED = "FINDING_STATUS_CHANGED"
    FINDING_OVERRIDDEN = "FINDING_OVERRIDDEN"
    SCORE_COMPUTED = "SCORE_COMPUTED"
    ALERT_DISPATCHED = "ALERT_DISPATCHED"
    RULE_PACK_PUBLISHED = "RULE_PACK_PUBLISHED"
    WORKER_RECORD_READ = "WORKER_RECORD_READ"
    """Logged with purpose, for DPDP purpose-limitation compliance."""
