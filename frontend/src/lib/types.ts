/** Types mirroring the backend Pydantic schemas.
 *
 *  Hand-written rather than generated from OpenAPI: the surface is small enough
 *  that a code-generation step would cost more than it saves. If these drift
 *  from the backend the typed helpers fail at the call site rather than silently
 *  mis-parsing a response.
 */

export type Role = "EMPLOYER" | "INSPECTOR" | "ADMIN" | "ANALYST";

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";

export type RiskBand = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type LabourCode =
  | "WAGES"
  | "INDUSTRIAL_RELATIONS"
  | "SOCIAL_SECURITY"
  | "OSH";

export type FindingKind =
  | "MISSING_FIELD"
  | "MISSING_DOCUMENT"
  | "DISCREPANCY"
  | "NON_COMPLIANCE"
  | "ANOMALY";

export type FindingStatus =
  | "OPEN"
  | "ACKNOWLEDGED"
  | "DISPUTED"
  | "RESOLVED"
  | "WAIVED"
  | "FALSE_POSITIVE";

export type DocumentStatus =
  | "RECEIVED"
  | "REJECTED"
  | "NORMALISED"
  | "CLASSIFIED"
  | "NEEDS_BINDING"
  | "EXTRACTED"
  | "NEEDS_REVIEW"
  | "VERIFIED"
  | "EVALUATED"
  | "SUPERSEDED"
  | "FAILED";

export type DocumentType =
  | "EMPLOYEE_REGISTER"
  | "WAGE_REGISTER"
  | "MUSTER_ROLL"
  | "WAGE_SLIP"
  | "OVERTIME_REGISTER"
  | "DEDUCTION_REGISTER"
  | "EPF_ECR"
  | "ESIC_CHALLAN"
  | "APPOINTMENT_LETTER"
  | "ESTABLISHMENT_REGISTRATION"
  | "CONTRACTOR_LICENCE"
  | "BOCW_CESS_RECEIPT"
  | "ACCIDENT_REGISTER"
  | "HEALTH_CHECKUP_RECORD"
  | "WELFARE_FACILITY_RECORD"
  | "STANDING_ORDERS"
  | "GRIEVANCE_COMMITTEE_RECORD"
  | "LEAVE_REGISTER"
  | "ANNUAL_RETURN"
  | "UNKNOWN";

export type ExtractionMode =
  | "NATIVE_PDF"
  | "OCR_ONLY"
  | "OCR_PLUS_VISION"
  | "VISION_ONLY";

export type SchemaSource = "PRESCRIBED" | "INFERRED";

export type WageRateSource = "NOTIFIED" | "REFERENCE";

// ---------------------------------------------------------------------- auth
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  organisation_id: string;
  jurisdictions: string[];
}

export interface HealthResponse {
  status: "ok";
  app: string;
  version: string;
  environment: string;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  checks: Record<string, boolean>;
}

// ----------------------------------------------------------------- documents
export interface DocumentSummary {
  id: string;
  original_filename: string;
  doc_type: DocumentType;
  doc_type_confidence: number | null;
  status: DocumentStatus;
  extraction_mode: ExtractionMode | null;
  schema_source: SchemaSource | null;
  establishment_id: string | null;
  establishment_name: string | null;
  period_start: string | null;
  period_end: string | null;
  page_count: number;
  byte_size: number;
  has_text_layer: boolean;
  review_reason_count: number;
  contains_redacted_pii: boolean;
  uploaded_at: string;
  processed_at: string | null;
}

export interface PageSummary {
  page_number: number;
  extraction_mode: ExtractionMode | null;
  has_image: boolean;
  has_coordinates: boolean;
  image_width: number | null;
  image_height: number | null;
  ocr_provider: string | null;
  ocr_failed_reason: string | null;
  text_preview: string | null;
}

export interface ExtractedFieldOut {
  name: string;
  value_text: string | null;
  value_number: number | null;
  value_date: string | null;
  source_page: number | null;
  source_bbox: number[] | null;
  agreement: string | null;
  needs_review: boolean;
}

export interface JobInfo {
  id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  detail: Record<string, unknown>;
}

export interface DocumentDetail extends DocumentSummary {
  review_reasons: string[];
  rejection_reason: string | null;
  pages: PageSummary[];
  fields: ExtractedFieldOut[];
  row_counts: Record<string, number>;
  latest_job: JobInfo | null;
}

export interface UploadResponse {
  document_id: string;
  status: DocumentStatus;
  message: string;
  supersedes_document_id: string | null;
}

export interface PageTokens {
  page_number: number;
  width: number | null;
  height: number | null;
  extraction_mode: string | null;
  tokens: OcrToken[];
  note: string | null;
}

export interface OcrToken {
  text: string;
  left: number;
  top: number;
  width: number;
  height: number;
  line: number;
}

// ------------------------------------------------------------------ findings
export interface EvidenceOut {
  document_id: string | null;
  document_filename: string | null;
  page_number: number | null;
  bbox: number[] | null;
  field_name: string | null;
  value_shown: string | null;
  row_reference: string | null;
  note: string | null;
  is_cell_level: boolean;
}

export interface FindingSummary {
  id: string;
  establishment_id: string;
  establishment_name: string | null;
  kind: FindingKind;
  code: LabourCode | null;
  severity: Severity;
  status: FindingStatus;
  title: string;
  message: string;
  remediation: string | null;
  citation: string;
  rule_id: string;
  rule_basis: RuleBasis;
  /** True only for RULES_PENDING. The other three bases need no caveat. */
  awaiting_notification: boolean;
  /** Why this severity, when context moved it off the rule's declared value. */
  severity_rationale: string | null;
  baseline_severity: Severity | null;
  period_start: string | null;
  period_end: string | null;
  affected_worker_count: number | null;
  exposure_paise: number | null;
  possible_false_positive: boolean;
  due_on: string | null;
  is_scored: boolean;
  created_at: string;
}

export interface FindingDetail extends FindingSummary {
  explanation: string | null;
  false_positive_reason: string | null;
  observed: Record<string, unknown>;
  expected: Record<string, unknown>;
  rule_pack_version: string;
  jurisdiction: string | null;
  wage_rate_source: WageRateSource | null;
  extraction_confidence: number | null;
  status_reason: string | null;
  status_changed_at: string | null;
  evidence: EvidenceOut[];
}

export interface FindingCounts {
  by_severity: Record<string, number>;
  by_kind: Record<string, number>;
  by_status: Record<string, number>;
  by_code: Record<string, number>;
  total: number;
  scored_total: number;
  advisory_total: number;
  awaiting_notification_total: number;
  total_exposure_paise: number;
}

// ------------------------------------------------------------ establishments
export interface EstablishmentSummary {
  id: string;
  name: string;
  lin: string | null;
  state_code: string;
  district: string | null;
  sector: string | null;
  worker_count: number;
  worker_count_peak_12m: number;
  is_active: boolean;
  latest_score: number | null;
  risk_band: RiskBand | null;
  data_completeness: number | null;
  open_finding_count: number;
  critical_finding_count: number;
  inspection_priority: number | null;
  last_evaluated_at: string | null;
}

export interface RegistrationOut {
  id: string;
  kind: string;
  number: string;
  issuing_authority: string | null;
  valid_from: string | null;
  valid_to: string | null;
  is_current: boolean;
}

export interface ContractorOut {
  id: string;
  name: string;
  licence_number: string | null;
  licence_valid_to: string | null;
  licensed_worker_count: number | null;
  deployed_worker_count: number;
  is_over_deployed: boolean;
}

export interface ScorecardOut {
  id: string;
  computed_at: string;
  period_start: string | null;
  period_end: string | null;
  overall_score: number;
  risk_band: RiskBand;
  code_scores: Record<string, number>;
  data_completeness: number;
  documents_expected: number;
  documents_received: number;
  expected_document_types: DocumentType[] | null;
  missing_document_types: DocumentType[] | null;
  findings_by_severity: Record<string, number>;
  open_finding_count: number;
  anomaly_count: number;
  recommended_inspection_priority: number | null;
  recommended_inspection_months: number | null;
  evidence_sufficient: boolean;
  /** Set when part of the score reflects Codes that could not be assessed rather
   *  than anything found against the establishment. */
  evidence_note: string | null;
  /** The model's reading of the records. Never part of the calculation. */
  review_summary: string | null;
  records_quality: string | null;
  computation?: Record<string, unknown> | null;
}

export interface ThresholdInfo {
  applies: boolean;
  threshold?: number;
  basis: string;
  citation: string;
}

export interface MinimumWageInfo {
  state_code: string;
  effective_on: string;
  rates: Record<
    string,
    {
      daily_paise: number;
      daily_rupees: number;
      monthly_paise: number;
      monthly_working_days: number;
      effective_from: string;
    }
  >;
  source: WageRateSource | null;
  source_note: string | null;
  available: boolean;
  caveat: string | null;
}

export interface EstablishmentDetail extends EstablishmentSummary {
  address: string | null;
  wage_zone: string | null;
  nic_code: string | null;
  women_worker_count: number;
  contract_worker_count: number;
  interstate_migrant_count: number;
  is_factory: boolean;
  is_mine: boolean;
  is_plantation: boolean;
  is_construction: boolean;
  has_hazardous_process: boolean;
  engages_contract_labour: boolean;
  has_night_shift: boolean;
  commenced_on: string | null;
  jurisdiction_code: string;
  registrations: RegistrationOut[];
  contractors: ContractorOut[];
  latest_scorecard: ScorecardOut | null;
  document_counts: Record<string, number>;
  applicable_thresholds: Record<string, ThresholdInfo>;
  minimum_wage: MinimumWageInfo;
}

export interface WorklistItem {
  establishment: EstablishmentSummary;
  reason: string;
  priority: number;
}

export interface EstablishmentInput {
  name: string;
  state_code: string;
  lin?: string | null;
  district?: string | null;
  wage_zone?: string | null;
  address?: string | null;
  nic_code?: string | null;
  sector?: string | null;
  worker_count: number;
  worker_count_peak_12m: number;
  women_worker_count: number;
  contract_worker_count: number;
  interstate_migrant_count: number;
  is_factory: boolean;
  is_mine: boolean;
  is_plantation: boolean;
  is_construction: boolean;
  has_hazardous_process: boolean;
  engages_contract_labour: boolean;
  has_night_shift: boolean;
  commenced_on?: string | null;
}

// --------------------------------------------------------------------- rules

/** What a rule's operative number rests on.
 *
 *  Replaces an earlier true/false "verified" flag, which lumped together two
 *  unrelated things: whether a statutory threshold had been confirmed, and
 *  whether the rule could be trusted. A check that a register adds up has no
 *  threshold to confirm, yet the old flag marked it unverified and scoring
 *  discounted it. Only RULES_PENDING is a genuine caveat.
 */
export type RuleBasis =
  | "STATUTE"
  | "RULES_PENDING"
  | "RECONCILIATION"
  | "ARITHMETIC";

export const RULE_BASIS_LABELS: Record<RuleBasis, string> = {
  STATUTE: "Stated in the Act",
  RULES_PENDING: "Awaiting a notification",
  RECONCILIATION: "Compares your documents",
  ARITHMETIC: "Checks the totals add up",
};

export const RULE_BASIS_EXPLANATIONS: Record<RuleBasis, string> = {
  STATUTE:
    "The figure this rule applies is written in the Act itself and is quoted in the source reference.",
  RULES_PENDING:
    "The Act creates this obligation but leaves the figure to be notified by the appropriate Government. That notification has not been obtained, so the figure used here comes from a secondary source. Check the notified Rules before acting on it.",
  RECONCILIATION:
    "This rule compares two of your own documents against each other. It applies no outside figure, so it needs no notification to be sound.",
  ARITHMETIC:
    "This rule checks that the figures within one document add up. It applies no outside figure, so it needs no notification to be sound.",
};

export interface PackOut {
  pack: string;
  version: string;
  jurisdiction: string;
  description: string | null;
  rule_count: number;
  sound_count: number;
  awaiting_notification_count: number;
  is_overlay: boolean;
}

export interface RuleIssueOut {
  rule_id: string;
  pack: string;
  level: "error" | "warning";
  message: string;
}

export interface RulesOverview {
  packs: PackOut[];
  total_rules: number;
  sound_rules: number;
  awaiting_notification: number;
  awaiting_notification_ids: string[];
  by_basis: Record<string, number>;
  by_code: Record<string, number>;
  by_severity: Record<string, number>;
  by_kind: Record<string, number>;
  issues: RuleIssueOut[];
}

export interface FixtureOut {
  name: string;
  should_pass: boolean;
  note: string | null;
}

export interface RuleOut {
  id: string;
  code: LabourCode;
  kind: FindingKind;
  severity: Severity;
  weight: number;
  title: string;
  citation: string;
  source_ref: string;
  basis: RuleBasis;
  awaiting_notification: boolean;
  applicability: string | null;
  requires: string[];
  for_each: string | null;
  expression: string;
  message_en: string;
  message_hi: string | null;
  remediation_en: string | null;
  remediation_hi: string | null;
  pack: string;
  pack_version: string;
  jurisdiction: string;
  fixture_count: number;
  fixtures: FixtureOut[];
}

// -------------------------------------------------------------------- labels
/** Severity and status are never shown as raw enum values, and never
 *  communicated by colour alone — every badge carries its text label. */

export const ROLE_LABELS: Record<Role, string> = {
  EMPLOYER: "Employer",
  INSPECTOR: "Inspector-cum-Facilitator",
  ADMIN: "Administrator",
  ANALYST: "Analyst",
};

export const CODE_LABELS: Record<LabourCode, string> = {
  WAGES: "Code on Wages, 2019",
  INDUSTRIAL_RELATIONS: "Industrial Relations Code, 2020",
  SOCIAL_SECURITY: "Code on Social Security, 2020",
  OSH: "OSH & Working Conditions Code, 2020",
};

export const CODE_SHORT_LABELS: Record<LabourCode, string> = {
  WAGES: "Wages",
  INDUSTRIAL_RELATIONS: "Industrial Relations",
  SOCIAL_SECURITY: "Social Security",
  OSH: "OSH",
};

export const SEVERITY_LABELS: Record<Severity, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  MEDIUM: "Medium",
  LOW: "Low",
  INFO: "Information",
};

export const FINDING_KIND_LABELS: Record<FindingKind, string> = {
  MISSING_FIELD: "Missing field",
  MISSING_DOCUMENT: "Missing document",
  DISCREPANCY: "Discrepancy",
  NON_COMPLIANCE: "Non-compliance",
  ANOMALY: "Advisory signal",
};

export const FINDING_STATUS_LABELS: Record<FindingStatus, string> = {
  OPEN: "Open",
  ACKNOWLEDGED: "Acknowledged",
  DISPUTED: "Disputed",
  RESOLVED: "Resolved",
  WAIVED: "Waived",
  FALSE_POSITIVE: "Dismissed",
};

export const RISK_BAND_LABELS: Record<RiskBand, string> = {
  LOW: "Low risk",
  MEDIUM: "Medium risk",
  HIGH: "High risk",
  CRITICAL: "Critical risk",
};

export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, string> = {
  RECEIVED: "Queued",
  REJECTED: "Rejected",
  NORMALISED: "Pages prepared",
  CLASSIFIED: "Identified",
  NEEDS_BINDING: "Needs establishment",
  EXTRACTED: "Read",
  NEEDS_REVIEW: "Needs review",
  VERIFIED: "Verified",
  EVALUATED: "Assessed",
  SUPERSEDED: "Replaced",
  FAILED: "Failed",
};

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  EMPLOYEE_REGISTER: "Employee register",
  WAGE_REGISTER: "Wage register",
  MUSTER_ROLL: "Muster roll",
  WAGE_SLIP: "Wage slip",
  OVERTIME_REGISTER: "Overtime register",
  DEDUCTION_REGISTER: "Deduction register",
  EPF_ECR: "EPF electronic challan",
  ESIC_CHALLAN: "ESIC challan",
  APPOINTMENT_LETTER: "Appointment letter",
  ESTABLISHMENT_REGISTRATION: "Establishment registration",
  CONTRACTOR_LICENCE: "Contractor licence",
  BOCW_CESS_RECEIPT: "BOCW cess receipt",
  ACCIDENT_REGISTER: "Accident register",
  HEALTH_CHECKUP_RECORD: "Health check-up record",
  WELFARE_FACILITY_RECORD: "Welfare facility record",
  STANDING_ORDERS: "Standing orders",
  GRIEVANCE_COMMITTEE_RECORD: "Grievance committee record",
  LEAVE_REGISTER: "Leave register",
  ANNUAL_RETURN: "Annual return",
  UNKNOWN: "Not yet identified",
};

/** How a document was read. Shown because it determines evidence quality. */
export const EXTRACTION_MODE_LABELS: Record<ExtractionMode, string> = {
  NATIVE_PDF: "Structured text",
  OCR_ONLY: "OCR text with source coordinates",
  OCR_PLUS_VISION: "OCR cross-checked against the page",
  VISION_ONLY: "Page image only — no cell coordinates",
};

export const SCHEMA_SOURCE_LABELS: Record<SchemaSource, string> = {
  PRESCRIBED: "Prescribed form",
  INFERRED: "Inferred layout",
};

/** Provenance of a wage rate. Legally material: a reference figure must not be
 *  presented with the authority of an official notification. */
export const WAGE_RATE_SOURCE_LABELS: Record<WageRateSource, string> = {
  NOTIFIED: "Official state notification",
  REFERENCE: "Secondary reference table",
};

/** Document types an employer is asked to submit, grouped for the upload form.
 *  Only types the backend has an extraction schema for. */
export const UPLOADABLE_DOCUMENT_GROUPS: {
  group: string;
  code: LabourCode;
  types: DocumentType[];
}[] = [
  {
    group: "Wages and attendance",
    code: "WAGES",
    types: [
      "WAGE_REGISTER",
      "WAGE_SLIP",
      "MUSTER_ROLL",
      "OVERTIME_REGISTER",
      "DEDUCTION_REGISTER",
      "LEAVE_REGISTER",
    ],
  },
  {
    group: "Workforce records",
    code: "OSH",
    types: ["EMPLOYEE_REGISTER", "APPOINTMENT_LETTER"],
  },
  {
    group: "Social security",
    code: "SOCIAL_SECURITY",
    types: ["EPF_ECR", "ESIC_CHALLAN", "BOCW_CESS_RECEIPT"],
  },
  {
    group: "Registrations and licences",
    code: "OSH",
    types: ["ESTABLISHMENT_REGISTRATION", "CONTRACTOR_LICENCE"],
  },
  {
    group: "Safety and welfare",
    code: "OSH",
    types: [
      "ACCIDENT_REGISTER",
      "HEALTH_CHECKUP_RECORD",
      "WELFARE_FACILITY_RECORD",
    ],
  },
  {
    group: "Industrial relations",
    code: "INDUSTRIAL_RELATIONS",
    types: ["STANDING_ORDERS", "GRIEVANCE_COMMITTEE_RECORD", "ANNUAL_RETURN"],
  },
];

/** State codes used as jurisdiction keys. Matches the wage rate loader. */
export const STATE_CODES: { code: string; name: string }[] = [
  { code: "AP", name: "Andhra Pradesh" },
  { code: "AR", name: "Arunachal Pradesh" },
  { code: "AS", name: "Assam" },
  { code: "BR", name: "Bihar" },
  { code: "CG", name: "Chhattisgarh" },
  { code: "CH", name: "Chandigarh" },
  { code: "DL", name: "Delhi" },
  { code: "GA", name: "Goa" },
  { code: "GJ", name: "Gujarat" },
  { code: "HP", name: "Himachal Pradesh" },
  { code: "HR", name: "Haryana" },
  { code: "JH", name: "Jharkhand" },
  { code: "JK", name: "Jammu & Kashmir" },
  { code: "KA", name: "Karnataka" },
  { code: "KL", name: "Kerala" },
  { code: "MH", name: "Maharashtra" },
  { code: "ML", name: "Meghalaya" },
  { code: "MN", name: "Manipur" },
  { code: "MP", name: "Madhya Pradesh" },
  { code: "MZ", name: "Mizoram" },
  { code: "NL", name: "Nagaland" },
  { code: "OD", name: "Odisha" },
  { code: "PB", name: "Punjab" },
  { code: "PY", name: "Puducherry" },
  { code: "RJ", name: "Rajasthan" },
  { code: "SK", name: "Sikkim" },
  { code: "TG", name: "Telangana" },
  { code: "TN", name: "Tamil Nadu" },
  { code: "TR", name: "Tripura" },
  { code: "UK", name: "Uttarakhand" },
  { code: "UP", name: "Uttar Pradesh" },
  { code: "WB", name: "West Bengal" },
];
