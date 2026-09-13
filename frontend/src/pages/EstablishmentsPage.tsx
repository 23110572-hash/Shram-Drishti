import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Building2,
  CalendarRange,
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
  WAGE_RATE_SOURCE_LABELS,
  type EstablishmentDetail,
  type EstablishmentSummary,
  type LabourCode,
  type ScorecardOut,
} from "@/lib/types";
import { Badge, RiskBadge } from "@/components/ui/Badge";
import {
  Caution,
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "@/components/ui/State";

/** Establishments: the unit everything else hangs off.
 *
 *  Compliance is assessed per establishment and per period, not per document, so
 *  this is where a score, its evidence completeness and the thresholds that apply
 *  are shown together.
 */

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
          <p className="mt-2 max-w-3xl text-base text-slate-700 sm:text-lg">
            Each establishment carries its own compliance position, evidence
            completeness and the statutory thresholds that apply to it.
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
        {establishments.isPending && <SkeletonRows rows={5} columns={6} />}

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
                  <th scope="col" className="px-6 py-4 font-bold">Evidence</th>
                  <th scope="col" className="px-6 py-4 font-bold">Open findings</th>
                  <th scope="col" className="px-6 py-4 font-bold">Last assessed</th>
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
                        {row.state_code}
                        {row.district && ` · ${row.district}`}
                        {row.lin && ` · LIN ${row.lin}`}
                      </p>
                    </td>

                    <td className="px-6 py-4">
                      <span className="font-bold text-slate-800">
                        {count(row.worker_count)}
                      </span>
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
                      {row.data_completeness === null ? (
                        <span className="text-slate-400">—</span>
                      ) : (
                        <CompletenessBar value={row.data_completeness} />
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
      void queryClient.invalidateQueries({ queryKey: ["findings"] });
    },
  });

  const establishment = detail.data;
  const scorecard = establishment?.latest_scorecard;

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
                {establishment.jurisdiction_code}
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
              {/* Score */}
              {scorecard ? (
                <section className="space-y-3 rounded-3xl border border-slate-200 bg-slate-50/70 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                        Compliance score
                      </p>
                      <p className="text-4xl font-extrabold text-slate-900">
                        {scorecard.overall_score.toFixed(0)}
                        <span className="text-lg font-bold text-slate-400"> / 100</span>
                      </p>
                    </div>
                    <div className="space-y-2 text-right">
                      <RiskBadge band={scorecard.risk_band} />
                      <p className="text-xs text-slate-500">
                        {period(scorecard.period_start, scorecard.period_end)}
                      </p>
                    </div>
                  </div>

                  {/* Why the number is what it is, when missing evidence rather
                      than conduct set it. Placed above the per-Code breakdown so a
                      capped Code is explained before it is read. */}
                  {scorecard.evidence_note && (
                    <Caution title="Part of this score reflects missing evidence">
                      {scorecard.evidence_note}
                    </Caution>
                  )}

                  {!scorecard.evidence_sufficient && (
                    <Caution title="This score rests on incomplete evidence">
                      {scorecard.documents_received} of{" "}
                      {scorecard.documents_expected} expected document types were
                      received. A low finding count here does not indicate
                      compliance — most checks could not be run at all.
                    </Caution>
                  )}

                  {/* The model's qualitative reading, kept visually distinct from
                      the score because it did not contribute to it. */}
                  {scorecard.review_summary && (
                    <div className="rounded-2xl border border-sky-200 bg-sky-50/70 p-4 text-sm leading-relaxed text-sky-950">
                      <p className="flex flex-wrap items-center gap-2 font-bold">
                        Reading of the records
                        {scorecard.records_quality && (
                          <Badge tone="info">
                            {scorecard.records_quality.replace(/_/g, " ")}
                          </Badge>
                        )}
                      </p>
                      <p className="mt-1">{scorecard.review_summary}</p>
                      <p className="mt-2 text-xs text-sky-900/80">
                        This is an automated reading offered for context. It did not
                        affect the score above.
                      </p>
                    </div>
                  )}

                  <div className="grid gap-2 sm:grid-cols-2">
                    {(Object.keys(CODE_SHORT_LABELS) as LabourCode[]).map((code) => (
                      <div
                        key={code}
                        className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-2.5"
                      >
                        <span className="text-sm font-semibold text-slate-700">
                          {CODE_SHORT_LABELS[code]}
                        </span>
                        <span className="font-mono text-sm font-extrabold text-slate-900">
                          {(scorecard.code_scores[code] ?? 0).toFixed(0)}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3">
                    <Metric
                      label="Evidence assessable"
                      value={percent(scorecard.data_completeness)}
                    />
                    <Metric
                      label="Open findings"
                      value={count(scorecard.open_finding_count)}
                    />
                    <Metric
                      label="Advisory signals"
                      value={count(scorecard.anomaly_count)}
                    />
                  </div>

                  {scorecard.recommended_inspection_months !== null && (
                    <p className="flex items-center gap-2 text-xs font-semibold text-slate-600">
                      <CalendarRange aria-hidden="true" className="h-4 w-4" />
                      Suggested inspection interval:{" "}
                      {scorecard.recommended_inspection_months} months
                      {scorecard.recommended_inspection_priority !== null &&
                        ` · priority ${scorecard.recommended_inspection_priority}/100`}
                    </p>
                  )}
                </section>
              ) : (
                <Caution title="Never assessed">
                  No compliance assessment has been run for this establishment. That
                  is not a clean record — it is an unknown one, and it raises the
                  case for a physical inspection.
                </Caution>
              )}

              {/* Run an assessment */}
              <section className="space-y-3 rounded-3xl border border-sky-200 bg-sky-50/60 p-5">
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

              {/* Score history */}
              {history.data && history.data.length > 1 && (
                <section className="space-y-2">
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
