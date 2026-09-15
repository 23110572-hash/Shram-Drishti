import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Building2,
  CalendarRange,
  CheckCircle2,
  ChevronRight,
  FileSearch,
  Gauge,
  MapPin,
  Play,
  Search,
  Users,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import { count, date, dateTime, paise, percent, period } from "@/lib/format";
import {
  CODE_SHORT_LABELS,
  DOCUMENT_TYPE_LABELS,
  STATE_CODES,
  WAGE_RATE_SOURCE_LABELS,
  type EstablishmentDetail,
  type EstablishmentSummary,
  type FindingSummary,
  type LabourCode,
  type ScorecardOut,
} from "@/lib/types";
import { Badge, RiskBadge, SeverityBadge } from "@/components/ui/Badge";
import {
  Caution,
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "@/components/ui/State";

/** Helper to convert state code (e.g., DL) into full state name (e.g., Delhi) */
function getStateName(code?: string | null): string {
  if (!code) return "";
  const found = STATE_CODES.find(
    (s) => s.code.toUpperCase() === code.trim().toUpperCase(),
  );
  return found ? found.name : code;
}

export function EstablishmentsPage() {
  const [search, setSearch] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  const params = new URLSearchParams({ limit: "100" });
  if (search.trim()) params.set("search", search.trim());

  const establishments = useQuery({
    queryKey: ["establishments", search],
    queryFn: () =>
      api.get<EstablishmentSummary[]>(`/establishments?${params.toString()}`),
  });

  const rows = establishments.data ?? [];

  return (
    <div className="space-y-10">
      <header className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2.5 rounded-full border border-sky-200 bg-sky-50 px-4 py-1.5 text-sm font-bold text-sky-800">
            <Building2 className="h-4 w-4" />
            Registered units
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950 sm:text-5xl">
            Establishments
          </h1>
          <p className="mt-2 text-base text-slate-700 sm:text-lg">
            Track compliance status and statutory obligations across all registered establishments.
          </p>
        </div>

        <label className="relative block w-full md:w-80">
          <span className="sr-only">Search establishments</span>
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-4 top-3.5 h-5 w-5 text-slate-400"
          />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name"
            className="w-full rounded-full border border-slate-300 bg-white/95 py-3 pl-12 pr-4 text-sm font-medium text-slate-900 placeholder:text-slate-400 focus:border-sky-600 focus:outline-none"
          />
        </label>
      </header>

      <div className="overflow-hidden rounded-3xl border border-sky-200/90 bg-white/95 shadow-sm backdrop-blur-xl">
        {establishments.isPending && <SkeletonRows rows={5} columns={5} />}

        {establishments.isError && (
          <ErrorState
            error={establishments.error}
            context="the establishment list"
            onRetry={() => void establishments.refetch()}
          />
        )}

        {establishments.isSuccess && rows.length === 0 && (
          <EmptyState
            icon={Building2}
            title={search ? "No match" : "No establishments on record"}
            description={
              search
                ? "No establishment matches that name within your scope."
                : "Establishments appear here once registered. Documents cannot be assessed until they are attached to one."
            }
          />
        )}

        {establishments.isSuccess && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50/90 text-xs uppercase tracking-wider text-slate-600">
                <tr>
                  <th scope="col" className="px-6 py-4 font-bold">Establishment</th>
                  <th scope="col" className="px-6 py-4 font-bold">Workers</th>
                  <th scope="col" className="px-6 py-4 font-bold">Compliance</th>
                  <th scope="col" className="px-6 py-4 font-bold">Open findings</th>
                  <th scope="col" className="px-6 py-4 font-bold">Compliance Date</th>
                  <th scope="col" className="px-6 py-4"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => setOpenId(row.id)}
                    className="cursor-pointer transition-colors hover:bg-sky-50/50"
                  >
                    <td className="px-6 py-4">
                      <p className="font-bold text-slate-900">{row.name}</p>
                      <p className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500">
                        <MapPin aria-hidden="true" className="h-3 w-3" />
                        {getStateName(row.state_code)}
                        {row.district && ` · ${row.district}`}
                        {row.lin && ` · LIN ${row.lin}`}
                      </p>
                    </td>

                    <td className="px-6 py-4">
                      <span className="font-bold text-slate-800">
                        {count(
                          row.worker_count > 0
                            ? row.worker_count
                            : row.observed_worker_count ?? 0,
                        )}
                      </span>
                      {row.worker_count === 0 && row.observed_worker_count !== null && (
                        <p className="text-xs text-slate-500">from documents</p>
                      )}
                      {row.worker_count_peak_12m > row.worker_count && (
                        <p className="text-xs text-slate-500">
                          peak {count(row.worker_count_peak_12m)}
                        </p>
                      )}
                    </td>

                    <td className="px-6 py-4">
                      {row.risk_band ? (
                        <RiskBadge band={row.risk_band} score={row.latest_score} />
                      ) : (
                        <Badge tone="neutral">Not assessed</Badge>
                      )}
                    </td>

                    <td className="px-6 py-4">
                      <span className="font-bold text-slate-800">
                        {count(row.open_finding_count)}
                      </span>
                      {row.critical_finding_count > 0 && (
                        <p className="text-xs font-bold text-rose-700">
                          {row.critical_finding_count} critical
                        </p>
                      )}
                    </td>

                    <td className="px-6 py-4 text-xs text-slate-500">
                      {row.last_evaluated_at ? date(row.last_evaluated_at) : "never"}
                    </td>

                    <td className="px-6 py-4 text-right">
                      <ChevronRight className="ml-auto h-4 w-4 text-slate-400" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {openId && (
        <EstablishmentDrawer
          establishmentId={openId}
          onClose={() => setOpenId(null)}
        />
      )}
    </div>
  );
}

/** Evidence completeness bar.
 *
 *  Shown beside the score and never merged into it. An establishment that
 *  submitted nothing would otherwise score perfectly, having broken no rule that
 *  could be tested — which would reward non-submission.
 */
export function CompletenessBar({ value }: { value: number }) {
  const thin = value < 60;

  return (
    <div className="w-28">
      <div
        role="meter"
        aria-valuenow={Math.round(value)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Evidence completeness"
        className="h-2 overflow-hidden rounded-full bg-slate-200"
      >
        <div
          className={`h-full rounded-full ${thin ? "bg-amber-500" : "bg-emerald-600"}`}
          style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
        />
      </div>
      <p
        className={`mt-1 text-xs font-bold ${thin ? "text-amber-800" : "text-slate-600"}`}
      >
        {percent(value)}
      </p>
    </div>
  );
}

function EstablishmentDrawer({
  establishmentId,
  onClose,
}: {
  establishmentId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [periodStart, setPeriodStart] = useState(defaultPeriodStart());
  const [periodEnd, setPeriodEnd] = useState(defaultPeriodEnd());

  const detail = useQuery({
    queryKey: ["establishment", establishmentId],
    queryFn: () =>
      api.get<EstablishmentDetail>(`/establishments/${establishmentId}`),
  });

  const history = useQuery({
    queryKey: ["scorecards", establishmentId],
    queryFn: () =>
      api.get<ScorecardOut[]>(`/establishments/${establishmentId}/scorecards?limit=12`),
  });

  const evaluate = useMutation({
    mutationFn: () =>
      api.post<{ status: string }>(`/establishments/${establishmentId}/evaluate`, {
        period_start: periodStart,
        period_end: periodEnd,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["establishment", establishmentId] });
      void queryClient.invalidateQueries({ queryKey: ["scorecards", establishmentId] });
      void queryClient.invalidateQueries({
        queryKey: ["establishment-score-findings", establishmentId],
      });
      void queryClient.invalidateQueries({ queryKey: ["findings"] });
    },
  });

  const establishment = detail.data;
  const scorecard = establishment?.latest_scorecard;
  const findingParams = new URLSearchParams({
    establishment_id: establishmentId,
    open_only: "true",
    scored_only: "true",
    limit: "200",
  });
  if (scorecard?.period_start) {
    findingParams.set("period_start", scorecard.period_start);
  }
  if (scorecard?.period_end) {
    findingParams.set("period_end", scorecard.period_end);
  }

  const findings = useQuery({
    queryKey: [
      "establishment-score-findings",
      establishmentId,
      scorecard?.period_start,
      scorecard?.period_end,
    ],
    queryFn: async () => {
      const all: FindingSummary[] = [];
      let offset = 0;

      while (true) {
        const pageParams = new URLSearchParams(findingParams);
        pageParams.set("offset", String(offset));
        const page = await api.get<FindingSummary[]>(
          `/findings?${pageParams.toString()}`,
        );
        all.push(...page);
        if (page.length < 200) return all;
        offset += page.length;
      }
    },
    enabled: Boolean(scorecard),
  });

  const contributingGroups = (
    scorecard?.computation?.contributing_findings ?? {}
  ) as Record<string, string[]>;
  const contributingFindingIds = new Set(Object.values(contributingGroups).flat());
  const openFindings = (findings.data ?? []).filter(
    (finding) =>
      contributingFindingIds.size === 0 || contributingFindingIds.has(finding.id),
  );
  const missingDocumentTypes = scorecard?.missing_document_types ?? [];
  const missingDocumentSet = new Set(missingDocumentTypes);
  const receivedDocumentTypes =
    scorecard?.present_document_types ??
    (scorecard?.expected_document_types ?? []).filter(
      (docType) => !missingDocumentSet.has(docType),
    );
  const issueCount = findings.data ? openFindings.length : scorecard?.open_finding_count ?? 0;

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
        aria-label="Establishment detail"
        className="relative flex h-full w-full max-w-3xl flex-col border-l border-slate-200 bg-white shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
          <div className="min-w-0">
            <p className="truncate text-lg font-bold text-slate-900">
              {establishment?.name ?? "Establishment"}
            </p>
            {establishment && (
              <p className="mt-1 text-xs text-slate-500">
                {getStateName(establishment.state_code || establishment.jurisdiction_code)}
                {establishment.sector && ` · ${establishment.sector}`}
                {establishment.lin && ` · LIN ${establishment.lin}`}
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
            <ErrorState error={detail.error} context="this establishment" />
          )}

          {establishment && (
            <>
              {/* Plain-language result first; methodology stays optional below. */}
              {scorecard ? (
                <section className="space-y-4 rounded-3xl border border-slate-200 bg-slate-50/70 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="flex min-w-0 items-start gap-3">
                      <div
                        className={[
                          "mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl",
                          issueCount > 0
                            ? "bg-rose-100 text-rose-700"
                            : "bg-emerald-100 text-emerald-700",
                        ].join(" ")}
                      >
                        {issueCount > 0 ? (
                          <AlertTriangle className="h-5 w-5" />
                        ) : (
                          <CheckCircle2 className="h-5 w-5" />
                        )}
                      </div>
                      <div>
                        <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          Uploaded-document compliance result
                        </p>
                        <h2 className="mt-1 text-2xl font-extrabold text-slate-950">
                          {issueCount > 0
                            ? `${issueCount} problem${issueCount === 1 ? "" : "s"} found`
                            : "No verified problems found"}
                        </h2>
                        <p className="mt-1 max-w-xl text-sm leading-relaxed text-slate-600">
                          {issueCount > 0
                            ? "Found by checking your uploaded documents together."
                            : "No verified problem was found by the rules that could be checked from the uploaded documents."}
                        </p>

                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                        Overall result
                      </p>
                      <p className="text-3xl font-extrabold text-slate-900">
                        {scorecard.overall_score.toFixed(0)}
                        <span className="text-base text-slate-500"> out of 100</span>
                      </p>
                      <RiskBadge band={scorecard.risk_band} />
                    </div>
                  </div>

                  <div className="rounded-2xl border border-sky-200 bg-white p-4">
                    <h3 className="font-bold text-slate-950">Documents checked together</h3>
                    <p className="mt-1 text-sm font-semibold text-slate-700">
                      {receivedDocumentTypes.length} document type{receivedDocumentTypes.length === 1 ? "" : "s"} · {scorecard.assessed_rule_count} rule{scorecard.assessed_rule_count === 1 ? "" : "s"} checked
                      {scorecard.observed_worker_count !== null &&
                        ` · ${count(scorecard.observed_worker_count)} workers found in the records`}
                    </p>
                    {receivedDocumentTypes.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {receivedDocumentTypes.map((docType) => (
                          <Badge key={docType} tone="info">
                            {DOCUMENT_TYPE_LABELS[docType]}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-1 text-sm text-slate-700">
                        No usable document was available for this assessment period.
                      </p>
                    )}
                    <p className="mt-2 text-xs leading-relaxed text-slate-600">
                      These are the document types the system linked and checked together for this result.
                    </p>
                  </div>

                  <p className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700">
                    {scorecard.scope_statement}
                  </p>

                  {findings.isPending && issueCount > 0 && (
                    <p className="text-sm text-slate-500">Loading the issues…</p>
                  )}
                  {findings.isError && issueCount > 0 && (
                    <Caution title="Issue details could not be loaded">
                      Open the Findings page below to review the detected problems.
                    </Caution>
                  )}

                  {openFindings.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-sm font-extrabold text-slate-900">
                        Problems found
                      </h3>
                      <ol className="space-y-2">
                        {openFindings.map((finding, index) => (
                          <li
                            key={finding.id}
                            className="flex gap-3 rounded-2xl border border-rose-200 bg-white p-4"
                          >
                            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-100 text-xs font-black text-rose-700">
                              {index + 1}
                            </span>
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <SeverityBadge severity={finding.severity} />
                                <p className="font-bold text-slate-900">{finding.title}</p>
                              </div>
                              <p className="mt-1 text-sm leading-relaxed text-slate-700">
                                {finding.message}
                              </p>
                            </div>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  <div
                    className={[
                      "hidden rounded-2xl border p-4",
                      missingDocumentTypes.length > 0
                        ? "border-amber-200 bg-amber-50"
                        : "border-emerald-200 bg-emerald-50",
                    ].join(" ")}
                  >
                    <h3
                      className={
                        missingDocumentTypes.length > 0
                          ? "font-bold text-amber-950"
                          : "font-bold text-emerald-950"
                      }
                    >
                      {missingDocumentTypes.length > 0
                        ? "Documents not received"
                        : "Required documents received"}
                    </h3>
                    {missingDocumentTypes.length > 0 ? (
                      <>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {missingDocumentTypes.map((docType) => (
                            <Badge key={docType} tone="medium">
                              {DOCUMENT_TYPE_LABELS[docType]}
                            </Badge>
                          ))}
                        </div>
                        <p className="mt-2 text-xs leading-relaxed text-amber-900">
                          Upload these records for the same establishment and period. A missing document means that check could not be completed; it does not by itself prove a violation.
                        </p>
                      </>
                    ) : (
                      <p className="mt-1 text-sm text-emerald-900">
                        All document types required for this establishment were available for this period.
                      </p>
                    )}
                  </div>

                  {scorecard.review_summary && (
                    <div className="rounded-2xl border border-sky-200 bg-sky-50/70 p-4 text-sm leading-relaxed text-sky-950">
                      <p className="font-bold">What the AI noticed across your documents</p>
                      <ul className="mt-2 space-y-1.5">
                        {scorecard.review_summary
                          .split("\n")
                          .map((line) => line.replace(/^[-*\u2022]\s*/, "").trim())
                          .filter((line) => line.length > 0)
                          .map((line, index) => (
                            <li key={index} className="flex gap-2">
                              <span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-600" />
                              <span>{line}</span>
                            </li>
                          ))}
                      </ul>
                      <p className="mt-2 text-xs text-sky-900/80">
                        These are extra observations. The rule checks above decide the official problems and the score.
                      </p>
                    </div>
                  )}

                  <details className="hidden rounded-2xl border border-slate-200 bg-white">
                    <summary className="cursor-pointer px-4 py-3 text-sm font-bold text-slate-800">
                      How this score was calculated
                    </summary>
                    <div className="space-y-3 border-t border-slate-100 p-4">
                      {scorecard.evidence_note && (
                        <p className="text-sm leading-relaxed text-slate-600">
                          {scorecard.evidence_note}
                        </p>
                      )}
                      <div className="grid gap-2 sm:grid-cols-2">
                        {(Object.keys(CODE_SHORT_LABELS) as LabourCode[]).map((code) => (
                          <div
                            key={code}
                            className="flex items-center justify-between rounded-xl border border-slate-200 px-3 py-2"
                          >
                            <span className="text-sm font-semibold text-slate-700">
                              {CODE_SHORT_LABELS[code]}
                            </span>
                            <span className="font-mono text-sm font-extrabold text-slate-900">
                              {scorecard.code_scores[code] === undefined
                                ? "Not assessed"
                                : scorecard.code_scores[code].toFixed(0)}
                            </span>
                          </div>
                        ))}
                      </div>
                      <p className="text-xs font-semibold text-slate-500">
                        Advisory AI/statistical signals: {count(scorecard.anomaly_count)}. These do not affect the score.
                      </p>
                      {scorecard.recommended_inspection_months !== null && (
                        <p className="flex items-center gap-2 text-xs font-semibold text-slate-600">
                          <CalendarRange aria-hidden="true" className="h-4 w-4" />
                          Suggested inspection interval: {scorecard.recommended_inspection_months} months
                          {scorecard.recommended_inspection_priority !== null &&
                            ` · priority ${scorecard.recommended_inspection_priority}/100`}
                        </p>
                      )}
                    </div>
                  </details>
                </section>
              ) : (
                <Caution title="Never assessed">
                  No compliance assessment has been run for this establishment. That
                  is not a clean record — it is an unknown one, and it raises the
                  case for a physical inspection.
                </Caution>
              )}

              {/* Run an assessment */}
              <section className="hidden space-y-3 rounded-3xl border border-sky-200 bg-sky-50/60 p-5">
                <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-sky-900">
                  <Play className="h-4 w-4" />
                  Run an assessment
                </h3>
                <p className="text-xs leading-relaxed text-sky-950">
                  Re-checks every document held for the chosen period against the
                  rule packs, recomputes the score, and notifies the employer and
                  the inspector.
                </p>
                <div className="flex flex-wrap items-end gap-3">
                  <label className="block">
                    <span className="mb-1 block text-xs font-bold text-slate-700">
                      From
                    </span>
                    <input
                      type="date"
                      value={periodStart}
                      onChange={(event) => setPeriodStart(event.target.value)}
                      className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 focus:border-sky-600 focus:outline-none"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs font-bold text-slate-700">
                      To
                    </span>
                    <input
                      type="date"
                      value={periodEnd}
                      onChange={(event) => setPeriodEnd(event.target.value)}
                      className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 focus:border-sky-600 focus:outline-none"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => evaluate.mutate()}
                    disabled={evaluate.isPending || !periodStart || !periodEnd}
                    className="cursor-pointer rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white transition-colors hover:bg-slate-800 disabled:opacity-40"
                  >
                    {evaluate.isPending ? "Queueing…" : "Assess period"}
                  </button>
                </div>
                {evaluate.isSuccess && (
                  <p className="text-xs font-semibold text-emerald-800">
                    Queued. The score and findings will update once it completes.
                  </p>
                )}
                {evaluate.isError && (
                  <p className="text-xs font-semibold text-rose-700">
                    {evaluate.error instanceof Error
                      ? evaluate.error.message
                      : "The assessment could not be queued."}
                  </p>
                )}
              </section>

              <details className="hidden rounded-2xl border border-slate-200 bg-white">
                <summary className="cursor-pointer px-4 py-3 text-sm font-bold text-slate-800">
                  Profile, legal thresholds and wage rates
                </summary>
                <div className="space-y-6 border-t border-slate-100 p-4">
              {/* Profile */}
              <section className="space-y-2">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                  Profile
                </h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Metric
                    label="Workers"
                    value={`${count(establishment.worker_count)} (peak ${count(establishment.worker_count_peak_12m)})`}
                  />
                  <Metric
                    label="Women workers"
                    value={count(establishment.women_worker_count)}
                  />
                  <Metric
                    label="Contract workers"
                    value={count(establishment.contract_worker_count)}
                  />
                  <Metric
                    label="Interstate migrants"
                    value={count(establishment.interstate_migrant_count)}
                  />
                </div>

                <div className="flex flex-wrap gap-2 pt-1">
                  {establishment.is_factory && <Badge tone="info">Factory</Badge>}
                  {establishment.is_mine && <Badge tone="info">Mine</Badge>}
                  {establishment.is_plantation && <Badge tone="info">Plantation</Badge>}
                  {establishment.is_construction && (
                    <Badge tone="info">Construction</Badge>
                  )}
                  {establishment.has_hazardous_process && (
                    <Badge tone="medium">Hazardous process</Badge>
                  )}
                  {establishment.engages_contract_labour && (
                    <Badge tone="medium">Engages contract labour</Badge>
                  )}
                  {establishment.has_night_shift && (
                    <Badge tone="info">Night shift</Badge>
                  )}
                </div>
              </section>

              {/* Thresholds. Shown so an employer can see why a rule applies. */}
              <section className="space-y-2">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                  Statutory obligations that apply
                </h3>
                <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200">
                  {Object.entries(establishment.applicable_thresholds).map(
                    ([key, info]) => (
                      <li
                        key={key}
                        className="flex items-start justify-between gap-4 px-4 py-3"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-bold text-slate-900">
                            {key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())}
                          </p>
                          <p className="mt-0.5 text-xs text-slate-600">
                            {info.threshold !== undefined &&
                              `${info.threshold}+ · `}
                            {info.basis}
                          </p>
                          <p className="mt-0.5 text-xs font-semibold text-slate-500">
                            {info.citation}
                          </p>
                        </div>
                        <Badge tone={info.applies ? "high" : "neutral"}>
                          {info.applies ? "Applies" : "Does not apply"}
                        </Badge>
                      </li>
                    ),
                  )}
                </ul>
              </section>

              {/* Minimum wage */}
              <section className="space-y-2">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                  Applicable minimum wage
                </h3>
                {establishment.minimum_wage.available ? (
                  <>
                    <dl className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 text-sm">
                      {Object.entries(establishment.minimum_wage.rates).map(
                        ([category, rate]) => (
                          <div
                            key={category}
                            className="flex items-baseline justify-between gap-4 px-4 py-2.5"
                          >
                            <dt className="text-xs font-semibold text-slate-600">
                              {category.replace(/_/g, " ").toLowerCase()}
                            </dt>
                            <dd className="text-right">
                              <span className="font-bold text-slate-900">
                                {paise(rate.daily_paise)}
                              </span>
                              <span className="text-xs text-slate-500"> per day</span>
                              <span className="ml-2 text-xs text-slate-500">
                                ({paise(rate.monthly_paise)} over{" "}
                                {rate.monthly_working_days} days)
                              </span>
                            </dd>
                          </div>
                        ),
                      )}
                    </dl>
                    {establishment.minimum_wage.source === "REFERENCE" && (
                      <Caution
                        title={`Source: ${WAGE_RATE_SOURCE_LABELS.REFERENCE}`}
                      >
                        {establishment.minimum_wage.source_note ??
                          "These rates come from a secondary aggregated table, not an official state notification. Confirm the notified rate before acting on a wage-floor finding."}
                      </Caution>
                    )}
                  </>
                ) : (
                  <Caution title="No wage rate on file">
                    {establishment.minimum_wage.caveat}
                  </Caution>
                )}
              </section>

              {/* Registrations */}
              {establishment.registrations.length > 0 && (
                <section className="space-y-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                    Registrations and licences
                  </h3>
                  <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200">
                    {establishment.registrations.map((registration) => (
                      <li
                        key={registration.id}
                        className="flex items-center justify-between gap-4 px-4 py-3"
                      >
                        <div>
                          <p className="text-sm font-bold text-slate-900">
                            {registration.kind.replace(/_/g, " ")}
                          </p>
                          <p className="font-mono text-xs text-slate-500">
                            {registration.number}
                            {registration.valid_to &&
                              ` · valid to ${date(registration.valid_to)}`}
                          </p>
                        </div>
                        <Badge tone={registration.is_current ? "good" : "critical"}>
                          {registration.is_current ? "Current" : "Not current"}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Contractors */}
              {establishment.contractors.length > 0 && (
                <section className="space-y-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                    Contractors engaged
                  </h3>
                  <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200">
                    {establishment.contractors.map((contractor) => (
                      <li
                        key={contractor.id}
                        className="flex items-center justify-between gap-4 px-4 py-3"
                      >
                        <div>
                          <p className="text-sm font-bold text-slate-900">
                            {contractor.name}
                          </p>
                          <p className="text-xs text-slate-500">
                            {contractor.licence_number ?? "no licence number"} ·{" "}
                            {count(contractor.deployed_worker_count)} deployed
                            {contractor.licensed_worker_count !== null &&
                              ` of ${count(contractor.licensed_worker_count)} licensed`}
                          </p>
                        </div>
                        {contractor.is_over_deployed && (
                          <Badge tone="high">Over licensed number</Badge>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
                </div>
              </details>

              {/* Score history */}
              {history.data && history.data.length > 1 && (
                <section className="hidden space-y-2">
                  <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-700">
                    <Gauge className="h-4 w-4" />
                    Score history
                  </h3>
                  <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200">
                    {history.data.map((entry) => (
                      <li
                        key={entry.id}
                        className="flex items-center justify-between gap-4 px-4 py-2.5"
                      >
                        <div>
                          <p className="text-sm font-bold text-slate-900">
                            {period(entry.period_start, entry.period_end)}
                          </p>
                          <p className="text-xs text-slate-500">
                            computed {dateTime(entry.computed_at)}
                          </p>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-sm font-extrabold text-slate-900">
                            {entry.overall_score.toFixed(0)}
                          </span>
                          <RiskBadge band={entry.risk_band} />
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>

        <footer className="flex items-center gap-3 border-t border-slate-200 bg-slate-50/80 px-6 py-4">
          <Link
            to={`/findings?establishment_id=${establishmentId}`}
            className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-slate-800"
          >
            <FileSearch className="h-4 w-4" />
            Findings
          </Link>
          <Link
            to="/documents"
            className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-5 py-2.5 text-sm font-bold text-slate-800 transition-colors hover:bg-slate-50"
          >
            <Users className="h-4 w-4" />
            Documents
          </Link>
        </footer>
      </aside>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <p className="mt-0.5 text-sm font-extrabold text-slate-900">{value}</p>
    </div>
  );
}

/** Defaults to the previous whole month, which is the period an employer is
 *  almost always filing for. */
function defaultPeriodStart(): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() - 1, 1)
    .toISOString()
    .slice(0, 10);
}

function defaultPeriodEnd(): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 0).toISOString().slice(0, 10);
}
