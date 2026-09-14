import type { ReactNode } from "react";

import {
  DOCUMENT_STATUS_LABELS,
  FINDING_KIND_LABELS,
  FINDING_STATUS_LABELS,
  RISK_BAND_LABELS,
  SEVERITY_LABELS,
  type DocumentStatus,
  type FindingKind,
  type FindingStatus,
  type RiskBand,
  type Severity,
} from "@/lib/types";

/** Status badges.
 *
 *  Every badge carries its text label. Severity is never communicated by colour
 *  alone: a colour-blind inspector, a greyscale printout of an inspection report,
 *  and a screen reader all have to convey the same thing.
 */

type Tone =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "info"
  | "good"
  | "neutral"
  | "pending";

const TONES: Record<Tone, string> = {
  critical: "bg-rose-50 text-rose-900 border-rose-300",
  high: "bg-orange-50 text-orange-900 border-orange-300",
  medium: "bg-amber-50 text-amber-900 border-amber-300",
  low: "bg-sky-50 text-sky-900 border-sky-300",
  info: "bg-slate-50 text-slate-700 border-slate-300",
  good: "bg-emerald-50 text-emerald-900 border-emerald-300",
  neutral: "bg-slate-100 text-slate-700 border-slate-300",
  pending: "bg-indigo-50 text-indigo-900 border-indigo-300",
};

interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  /** Small leading dot. Decorative only, hidden from assistive technology. */
  dot?: boolean;
  title?: string;
}

export function Badge({
  tone = "neutral",
  children,
  className = "",
  dot = false,
  title,
}: BadgeProps) {
  return (
    <span
      title={title}
      className={[
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5",
        "text-xs font-bold whitespace-nowrap",
        TONES[tone],
        className,
      ].join(" ")}
    >
      {dot && (
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 rounded-full bg-current opacity-70"
        />
      )}
      {children}
    </span>
  );
}

const SEVERITY_TONES: Record<Severity, Tone> = {
  CRITICAL: "critical",
  HIGH: "high",
  MEDIUM: "medium",
  LOW: "low",
  INFO: "info",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge tone={SEVERITY_TONES[severity]} dot>
      {SEVERITY_LABELS[severity]}
    </Badge>
  );
}

const RISK_TONES: Record<RiskBand, Tone> = {
  LOW: "good",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
};

export function RiskBadge({
  band,
  score,
}: {
  band: RiskBand;
  score?: number | null;
}) {
  return (
    <Badge tone={RISK_TONES[band]} dot>
      {RISK_BAND_LABELS[band]}
      {score !== null && score !== undefined && (
        <span className="font-mono font-black">{score.toFixed(0)}</span>
      )}
    </Badge>
  );
}

const FINDING_STATUS_TONES: Record<FindingStatus, Tone> = {
  OPEN: "high",
  ACKNOWLEDGED: "pending",
  DISPUTED: "medium",
  RESOLVED: "good",
  WAIVED: "neutral",
  FALSE_POSITIVE: "neutral",
};

export function FindingStatusBadge({ status }: { status: FindingStatus }) {
  return (
    <Badge tone={FINDING_STATUS_TONES[status]}>
      {FINDING_STATUS_LABELS[status]}
    </Badge>
  );
}

const KIND_TONES: Record<FindingKind, Tone> = {
  NON_COMPLIANCE: "critical",
  DISCREPANCY: "high",
  MISSING_DOCUMENT: "medium",
  MISSING_FIELD: "medium",
  // Advisory signals are deliberately muted. They are never scored and cannot be
  // enforced, so they must not compete visually with a cited breach.
  ANOMALY: "info",
};

export function KindBadge({ kind }: { kind: FindingKind }) {
  return <Badge tone={KIND_TONES[kind]}>{FINDING_KIND_LABELS[kind]}</Badge>;
}

const DOC_STATUS_TONES: Record<DocumentStatus, Tone> = {
  RECEIVED: "pending",
  REJECTED: "critical",
  NORMALISED: "pending",
  CLASSIFIED: "pending",
  NEEDS_BINDING: "medium",
  EXTRACTED: "good",
  NEEDS_REVIEW: "medium",
  VERIFIED: "good",
  EVALUATED: "good",
  SUPERSEDED: "neutral",
  FAILED: "critical",
};

/** Statuses where work is still in progress, so the row should keep polling. */
export const DOCUMENT_IN_PROGRESS: DocumentStatus[] = [
  "RECEIVED",
  "NORMALISED",
  "CLASSIFIED",
];

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const inProgress = DOCUMENT_IN_PROGRESS.includes(status);
  return (
    <Badge tone={DOC_STATUS_TONES[status]}>
      {inProgress && (
        <span
          aria-hidden="true"
          className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {DOCUMENT_STATUS_LABELS[status]}
    </Badge>
  );
}

/** Flags a finding whose figure the Act leaves to a government notification that
 *  has not been obtained. Shown prominently on purpose: nobody should enforce on
 *  it as it stands.
 *
 *  Deliberately the only basis that gets a badge. Marking the other three would
 *  put a warning on rules that were never in doubt, and a warning that appears
 *  everywhere is read nowhere. */
export function AwaitingNotificationBadge() {
  return (
    <Badge
      tone="medium"
      title="The Act creates this obligation but leaves the figure to be notified by the appropriate Government, and that notification has not been obtained. The figure used comes from a secondary source, so this is shown for information and weighted lightly in scoring."
    >
      Awaiting notification
    </Badge>
  );
}

/** Shown when context moved a finding's severity off the value its rule declared.
 *  The reason is the point: a severity nobody can account for is worse than a
 *  fixed one. */
export function AssessedSeverityBadge({
  from,
  reason,
}: {
  from: string | null;
  reason: string | null;
}) {
  if (!reason) return null;

  return (
    <Badge
      tone="info"
      title={
        from
          ? `The rule for this breach declares ${from}. It was recorded differently because: ${reason}`
          : reason
      }
    >
      Severity set in context
    </Badge>
  );
}
