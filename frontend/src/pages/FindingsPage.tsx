import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  AlertOctagon,
  ChevronRight,
  FileCheck,
  Info,
  Scale,
  Users,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { count, dateTime, jsonValue, humanise, paise, period } from "@/lib/format";
import {
  CODE_SHORT_LABELS,
  FINDING_STATUS_LABELS,
  WAGE_RATE_SOURCE_LABELS,
  type FindingCounts,
  type FindingDetail,
  type FindingStatus,
  type FindingSummary,
  type LabourCode,
  type Severity,
} from "@/lib/types";
import { EvidenceViewer } from "@/components/EvidenceViewer";
import {
  Badge,
  FindingStatusBadge,
  KindBadge,
  SeverityBadge,
  UnverifiedRuleBadge,
} from "@/components/ui/Badge";
import {
  Caution,
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "@/components/ui/State";

/** Findings screen.
 *
 *  Two things this layout insists on.
 *
 *  Advisory signals are separated from cited breaches. A statistical observation
 *  and a breach of section 18(3) look nothing alike in law, and putting them in
 *  one undifferentiated list would let an inspector act on the wrong one.
 *
 *  Nothing is presented without its evidence. Selecting a finding opens the
 *  scanned page with the cell highlighted, because a finding an employer cannot
 *  check is a finding they can simply deny.
 */

const SEVERITIES: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
const CODES: LabourCode[] = [
  "WAGES",
  "SOCIAL_SECURITY",
  "OSH",
  "INDUSTRIAL_RELATIONS",
];

export function FindingsPage() {
  const [searchParams] = useSearchParams();
  const establishmentId = searchParams.get("establishment_id");

  const [severity, setSeverity] = useState<Severity | "">("");
  const [code, setCode] = useState<LabourCode | "">("");
  const [showAdvisory, setShowAdvisory] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const params = new URLSearchParams({ limit: "150", open_only: "true" });
  if (establishmentId) params.set("establishment_id", establishmentId);
  if (severity) params.set("severity", severity);
  if (code) params.set("code", code);
  if (!showAdvisory) params.set("scored_only", "true");

  const findings = useQuery({
    queryKey: ["findings", establishmentId, severity, code, showAdvisory],
    queryFn: () => api.get<FindingSummary[]>(`/findings?${params.toString()}`),
  });

  const countsParams = new URLSearchParams({ open_only: "true" });
  if (establishmentId) countsParams.set("establishment_id", establishmentId);

  const counts = useQuery({
    queryKey: ["finding-counts", establishmentId],
    queryFn: () => api.get<FindingCounts>(`/findings/counts?${countsParams.toString()}`),
  });

  const rows = findings.data ?? [];
  const summary = counts.data;

  return (
    <div className="space-y-10">
      <header className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2.5 rounded-full border border-rose-200 bg-rose-50 px-4 py-1.5 text-sm font-bold text-rose-800">
            <AlertOctagon className="h-4 w-4" />
            Compliance findings
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950 sm:text-5xl">
            Findings
          </h1>
          <p className="mt-2 max-w-3xl text-base text-slate-700 sm:text-lg">
            Each finding cites the statutory provision it rests on and links to the
            exact cell on the scanned page it was read from.
          </p>
        </div>
      </header>

      {/* Summary */}
      {summary && summary.total > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryCard
            label="Cited breaches"
            value={count(summary.scored_total)}
            hint="Affect the compliance score"
            tone="warn"
          />
          <SummaryCard
            label="Advisory signals"
            value={count(summary.advisory_total)}
            hint="Never scored, never enforced"
            tone="calm"
          />
          <SummaryCard
            label="Amount at stake"
            value={paise(summary.total_exposure_paise)}
            hint="Where it could be quantified"
            tone="calm"
          />
          <SummaryCard
            label="Unverified thresholds"
            value={count(summary.unverified_rule_total)}
            hint="Not yet confirmed against primary text"
            tone={summary.unverified_rule_total > 0 ? "warn" : "calm"}
          />
        </div>
      )}

      {summary && summary.unverified_rule_total > 0 && (
        <Caution title="Some thresholds are not yet confirmed">
          {summary.unverified_rule_total} of these findings rest on a threshold read
          from a secondary source rather than the primary statutory text. They are
          flagged individually, weighted lightly in scoring, and should not be
          enforced without checking the notified Rules.
        </Caution>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <FilterGroup
          label="Severity"
          value={severity}
          onChange={(value) => setSeverity(value as Severity | "")}
          options={SEVERITIES.map((item) => ({ value: item, label: item }))}
        />
        <FilterGroup
          label="Code"
          value={code}
          onChange={(value) => setCode(value as LabourCode | "")}
          options={CODES.map((item) => ({
            value: item,
            label: CODE_SHORT_LABELS[item],
          }))}
        />

        <label className="ml-auto flex cursor-pointer items-center gap-2.5 rounded-full border border-slate-300 bg-white/90 px-4 py-2 text-sm font-bold text-slate-700">
          <input
            type="checkbox"
            checked={showAdvisory}
            onChange={(event) => setShowAdvisory(event.target.checked)}
            className="h-4 w-4 cursor-pointer rounded border-slate-400 text-sky-600"
          />
          Include advisory signals
        </label>
      </div>

      {/* List */}
      <div className="overflow-hidden rounded-3xl border border-sky-200/90 bg-white/95 shadow-sm backdrop-blur-xl">
        {findings.isPending && <SkeletonRows rows={6} columns={5} />}

        {findings.isError && (
          <ErrorState
            error={findings.error}
            context="the findings list"
            onRetry={() => void findings.refetch()}
          />
        )}

        {findings.isSuccess && rows.length === 0 && (
          <EmptyState
            icon={FileCheck}
            tone="good"
            title={
              severity || code
                ? "Nothing matches this filter"
                : "No open findings"
            }
            description={
              severity || code
                ? "Clear the filters to see everything currently open."
                : "No breaches are currently open against the documents assessed. Submit filings for a period to have them checked against the Labour Codes."
            }
          />
        )}

        {findings.isSuccess && rows.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {rows.map((finding) => (
              <li key={finding.id}>
                <button
                  type="button"
                  onClick={() => setOpenId(finding.id)}
                  className="flex w-full cursor-pointer items-start gap-4 px-6 py-5 text-left transition-colors hover:bg-sky-50/50"
                >
                  <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={finding.severity} />
                      <KindBadge kind={finding.kind} />
                      {finding.code && (
                        <Badge tone="info">{CODE_SHORT_LABELS[finding.code]}</Badge>
                      )}
                      {!finding.rule_verified && <UnverifiedRuleBadge />}
                      {finding.possible_false_positive && (
                        <Badge
                          tone="medium"
                          title="Automated review flagged this as possibly incorrect. It has not been removed — an inspector decides."
                        >
                          Possibly incorrect
                        </Badge>
                      )}
                    </div>

                    <p className="text-base font-bold text-slate-900">
                      {finding.title}
                    </p>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
                      <span className="inline-flex items-center gap-1.5 font-semibold">
                        <Scale aria-hidden="true" className="h-3.5 w-3.5" />
                        {finding.citation}
                      </span>
                      {finding.establishment_name && (
                        <span>{finding.establishment_name}</span>
                      )}
                      {finding.period_start && (
                        <span>{period(finding.period_start, finding.period_end)}</span>
                      )}
                      {finding.affected_worker_count !== null && (
                        <span className="inline-flex items-center gap-1.5">
                          <Users aria-hidden="true" className="h-3.5 w-3.5" />
                          {count(finding.affected_worker_count)} worker
                          {finding.affected_worker_count === 1 ? "" : "s"}
                        </span>
                      )}
                      {finding.exposure_paise !== null && (
                        <span className="font-bold text-slate-800">
                          {paise(finding.exposure_paise)} at stake
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-3">
                    <FindingStatusBadge status={finding.status} />
                    <ChevronRight className="h-4 w-4 text-slate-400" />
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {openId && (
        <FindingDrawer findingId={openId} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  tone: "calm" | "warn";
}) {
  return (
    <div
      className={[
        "rounded-3xl border p-5 shadow-sm backdrop-blur-xl",
        tone === "warn"
          ? "border-amber-300 bg-amber-50/80"
          : "border-slate-200 bg-white/90",
      ].join(" ")}
    >
      <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <p className="mt-1 text-2xl font-extrabold text-slate-900">{value}</p>
      <p className="mt-0.5 text-xs text-slate-600">{hint}</p>
    </div>
  );
}

function FilterGroup({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white/90 py-1.5 pl-4 pr-2 text-sm">
      <span className="font-bold text-slate-600">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="cursor-pointer appearance-none rounded-full bg-transparent py-1 pr-2 font-bold text-slate-900 focus:outline-none"
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Finding detail with evidence.
 *
 *  Status changes are role-gated by the backend: an employer may acknowledge or
 *  dispute, only an inspector may resolve, waive or dismiss. The UI mirrors that
 *  rather than offering buttons that will be refused.
 */
function FindingDrawer({
  findingId,
  onClose,
}: {
  findingId: string;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [selectedEvidence, setSelectedEvidence] = useState(0);
  const [reason, setReason] = useState("");

  const detail = useQuery({
    queryKey: ["finding", findingId],
    queryFn: () => api.get<FindingDetail>(`/findings/${findingId}`),
  });

  const changeStatus = useMutation({
    mutationFn: (status: FindingStatus) =>
      api.post<FindingDetail>(`/findings/${findingId}/status`, {
        status,
        reason: reason.trim() || null,
      }),
    onSuccess: () => {
      setReason("");
      void queryClient.invalidateQueries({ queryKey: ["finding", findingId] });
      void queryClient.invalidateQueries({ queryKey: ["findings"] });
      void queryClient.invalidateQueries({ queryKey: ["finding-counts"] });
    },
  });

  const finding = detail.data;
  const evidence = finding?.evidence ?? [];
  const current = evidence[selectedEvidence];

  const isEmployer = user?.role === "EMPLOYER";
  const canClose = user?.role === "INSPECTOR" || user?.role === "ADMIN";

  return (
    <div className="fixed inset-0 z-[60] flex justify-end">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-slate-900/40 backdrop-blur-sm"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Finding detail"
        className="relative flex h-full w-full max-w-3xl flex-col border-l border-slate-200 bg-white shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
          <div className="min-w-0">
            <p className="text-lg font-bold leading-tight text-slate-900">
              {finding?.title ?? "Finding"}
            </p>
            {finding && (
              <p className="mt-1 font-mono text-xs text-slate-500">
                {finding.rule_id} · {finding.rule_pack_version}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="cursor-pointer rounded-full p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
          {detail.isPending && <SkeletonRows rows={6} columns={2} />}
          {detail.isError && (
            <ErrorState error={detail.error} context="this finding" />
          )}

          {finding && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={finding.severity} />
                <KindBadge kind={finding.kind} />
                <FindingStatusBadge status={finding.status} />
                {!finding.rule_verified && <UnverifiedRuleBadge />}
              </div>

              {/* An advisory signal must say what it is not, prominently. */}
              {finding.kind === "ANOMALY" && (
                <div className="rounded-2xl border border-sky-200 bg-sky-50/80 p-4 text-sm leading-relaxed text-sky-950">
                  <p className="flex items-center gap-2 font-bold">
                    <Info aria-hidden="true" className="h-4 w-4" />
                    Advisory only
                  </p>
                  <p className="mt-1">
                    This is a statistical or pattern observation, not a breach of
                    law. It carries no statutory citation, does not affect the
                    compliance score, and cannot be enforced. It is here to tell an
                    inspector where to look.
                  </p>
                </div>
              )}

              <section className="space-y-2">
                <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-700">
                  <Scale className="h-4 w-4" />
                  Statutory basis
                </h3>
                <p className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm font-bold text-slate-900">
                  {finding.citation}
                </p>
              </section>

              <section className="space-y-2">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                  What was found
                </h3>
                <p className="text-sm leading-relaxed text-slate-800">
                  {finding.message}
                </p>
              </section>

              {/* Observed against expected. The pair is what makes the finding
                  arguable rather than a bare assertion. */}
              {(Object.keys(finding.observed).length > 0 ||
                Object.keys(finding.expected).length > 0) && (
                <section className="grid gap-3 sm:grid-cols-2">
                  <KeyValues
                    title="Observed"
                    tone="warn"
                    values={finding.observed}
                  />
                  <KeyValues
                    title="Required"
                    tone="calm"
                    values={finding.expected}
                  />
                </section>
              )}

              {finding.remediation && (
                <section className="space-y-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-emerald-800">
                    What to do
                  </h3>
                  <p className="rounded-2xl border border-emerald-200 bg-emerald-50/80 px-4 py-3 text-sm leading-relaxed text-emerald-950">
                    {finding.remediation}
                  </p>
                </section>
              )}

              {/* Plain-language explanation from the automated review. Marked as
                  non-authoritative: the citation and the observed/expected pair
                  are what carry weight. */}
              {finding.explanation && (
                <section className="space-y-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                    In plain terms
                  </h3>
                  <p className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-700">
                    {finding.explanation}
                  </p>
                  <p className="text-xs text-slate-500">
                    Written by automated review to aid understanding. The statutory
                    citation above is what governs.
                  </p>
                </section>
              )}

              {finding.possible_false_positive && finding.false_positive_reason && (
                <Caution title="Automated review flagged this as possibly incorrect">
                  {finding.false_positive_reason}
                  <p className="mt-1.5 text-xs">
                    The finding has not been removed. An inspector decides whether
                    it stands.
                  </p>
                </Caution>
              )}

              {finding.wage_rate_source && (
                <Caution
                  title={`Wage rate source: ${WAGE_RATE_SOURCE_LABELS[finding.wage_rate_source]}`}
                >
                  {finding.wage_rate_source === "REFERENCE"
                    ? "This finding was computed against a secondary reference table, not an official state notification. Confirm the applicable notified rate before acting on it."
                    : "This finding was computed against an official state notification."}
                </Caution>
              )}

              {/* Evidence */}
              <section className="space-y-3">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                  Evidence
                </h3>

                {evidence.length === 0 && (
                  <p className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
                    This finding was raised from establishment-level facts rather
                    than a specific cell, so there is no page to show.
                  </p>
                )}

                {evidence.length > 1 && (
                  <div className="flex flex-wrap gap-2">
                    {evidence.map((item, index) => (
                      <button
                        key={index}
                        type="button"
                        onClick={() => setSelectedEvidence(index)}
                        aria-pressed={selectedEvidence === index}
                        className={[
                          "cursor-pointer rounded-full border px-3.5 py-1.5 text-xs font-bold transition-colors",
                          selectedEvidence === index
                            ? "border-slate-900 bg-slate-900 text-white"
                            : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
                        ].join(" ")}
                      >
                        {item.row_reference ??
                          (item.page_number ? `Page ${item.page_number}` : `Item ${index + 1}`)}
                      </button>
                    ))}
                  </div>
                )}

                {current && (
                  <EvidenceViewer evidence={current} siblings={evidence} />
                )}
              </section>

              {/* Provenance */}
              <section className="space-y-2">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                  Provenance
                </h3>
                <dl className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 text-sm">
                  <Row label="Rule" value={finding.rule_id} mono />
                  <Row label="Rule pack" value={finding.rule_pack_version} mono />
                  <Row label="Jurisdiction" value={finding.jurisdiction ?? "—"} />
                  <Row
                    label="Extraction confidence"
                    value={
                      finding.extraction_confidence === null
                        ? "not measured"
                        : `${Math.round(finding.extraction_confidence * 100)}%`
                    }
                  />
                  <Row label="Raised" value={dateTime(finding.created_at)} />
                  {finding.due_on && (
                    <Row label="Response due" value={dateTime(finding.due_on)} />
                  )}
                  {finding.status_changed_at && (
                    <Row
                      label={`Marked ${FINDING_STATUS_LABELS[finding.status].toLowerCase()}`}
                      value={dateTime(finding.status_changed_at)}
                    />
                  )}
                </dl>
                {finding.status_reason && (
                  <p className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-700">
                    <span className="font-bold">Reason recorded: </span>
                    {finding.status_reason}
                  </p>
                )}
              </section>
            </>
          )}
        </div>

        {/* Actions */}
        {finding && user && finding.kind !== "ANOMALY" && (
          <footer className="space-y-3 border-t border-slate-200 bg-slate-50/80 px-6 py-4">
            {(canClose || isEmployer) && (
              <textarea
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={2}
                placeholder={
                  canClose
                    ? "Reason — required to resolve, waive or dismiss"
                    : "Optional note for the inspector"
                }
                className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-600 focus:outline-none"
              />
            )}

            <div className="flex flex-wrap items-center gap-2">
              {isEmployer && (
                <>
                  <ActionButton
                    onClick={() => changeStatus.mutate("ACKNOWLEDGED")}
                    pending={changeStatus.isPending}
                    tone="primary"
                  >
                    Acknowledge
                  </ActionButton>
                  <ActionButton
                    onClick={() => changeStatus.mutate("DISPUTED")}
                    pending={changeStatus.isPending}
                    tone="secondary"
                  >
                    Dispute
                  </ActionButton>
                </>
              )}

              {canClose && (
                <>
                  <ActionButton
                    onClick={() => changeStatus.mutate("RESOLVED")}
                    pending={changeStatus.isPending}
                    disabled={reason.trim().length < 10}
                    tone="primary"
                  >
                    Resolve
                  </ActionButton>
                  <ActionButton
                    onClick={() => changeStatus.mutate("WAIVED")}
                    pending={changeStatus.isPending}
                    disabled={reason.trim().length < 10}
                    tone="secondary"
                  >
                    Waive
                  </ActionButton>
                  <ActionButton
                    onClick={() => changeStatus.mutate("FALSE_POSITIVE")}
                    pending={changeStatus.isPending}
                    disabled={reason.trim().length < 10}
                    tone="secondary"
                  >
                    Dismiss as incorrect
                  </ActionButton>
                </>
              )}
            </div>

            {canClose && reason.trim().length > 0 && reason.trim().length < 10 && (
              <p className="text-xs font-semibold text-amber-800">
                A reason of at least 10 characters is required — these decisions
                remove the finding from the compliance score and are auditable.
              </p>
            )}

            {changeStatus.isError && (
              <p className="text-xs font-semibold text-rose-700">
                {changeStatus.error instanceof Error
                  ? changeStatus.error.message
                  : "The status could not be changed."}
              </p>
            )}
          </footer>
        )}
      </aside>
    </div>
  );
}

function ActionButton({
  onClick,
  children,
  pending,
  disabled,
  tone,
}: {
  onClick: () => void;
  children: React.ReactNode;
  pending: boolean;
  disabled?: boolean;
  tone: "primary" | "secondary";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending || disabled}
      className={[
        "cursor-pointer rounded-full px-5 py-2.5 text-sm font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        tone === "primary"
          ? "bg-slate-900 text-white hover:bg-slate-800"
          : "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function KeyValues({
  title,
  values,
  tone,
}: {
  title: string;
  values: Record<string, unknown>;
  tone: "warn" | "calm";
}) {
  if (Object.keys(values).length === 0) return null;

  return (
    <div
      className={[
        "rounded-2xl border p-4",
        tone === "warn"
          ? "border-rose-200 bg-rose-50/70"
          : "border-emerald-200 bg-emerald-50/70",
      ].join(" ")}
    >
      <p
        className={[
          "text-xs font-bold uppercase tracking-wider",
          tone === "warn" ? "text-rose-900" : "text-emerald-900",
        ].join(" ")}
      >
        {title}
      </p>
      <dl className="mt-2 space-y-1.5 text-sm">
        {Object.entries(values).map(([key, value]) => (
          <div key={key} className="flex items-baseline justify-between gap-3">
            <dt className="text-slate-600">{humanise(key)}</dt>
            <dd className="text-right font-bold text-slate-900">
              {jsonValue(key, value)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 px-4 py-2.5">
      <dt className="text-xs font-semibold text-slate-600">{label}</dt>
      <dd
        className={[
          "text-right font-bold text-slate-900",
          mono ? "font-mono text-xs" : "text-sm",
        ].join(" ")}
      >
        {value}
      </dd>
    </div>
  );
}
