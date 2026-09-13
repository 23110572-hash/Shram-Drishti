import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  ChevronRight,
  FileSearch,
  FolderOpen,
  Layers,
  Link2,
  RefreshCw,
  ScanLine,
  ShieldAlert,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { bytes, dateTime, period, relative } from "@/lib/format";
import {
  DOCUMENT_TYPE_LABELS,
  EXTRACTION_MODE_LABELS,
  SCHEMA_SOURCE_LABELS,
  type DocumentDetail,
  type DocumentStatus,
  type DocumentSummary,
} from "@/lib/types";
import { UploadPanel } from "@/components/UploadPanel";
import {
  Badge,
  DOCUMENT_IN_PROGRESS,
  DocumentStatusBadge,
} from "@/components/ui/Badge";
import {
  Caution,
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "@/components/ui/State";

/** Documents screen: submission, then the state of everything submitted.
 *
 *  The list refreshes on a short interval while any document is still being
 *  read, and stops once everything has settled. Reading a fifty-page register
 *  takes minutes, and an employer staring at a stale "Queued" badge assumes the
 *  system is broken.
 */

interface Filter {
  key: string;
  label: string;
  status?: DocumentStatus | undefined;
  attention?: boolean | undefined;
}

const ALL_FILTER: Filter = { key: "all", label: "All" };

/** Statuses where a person has to do something before the document counts. */
const NEEDS_ATTENTION: DocumentStatus[] = [
  "NEEDS_REVIEW",
  "NEEDS_BINDING",
  "FAILED",
  "REJECTED",
];

/** Group key for documents not yet attached to any workplace. */
const UNATTACHED = "__unattached__";

interface DocumentGroup {
  key: string;
  establishmentId: string | null;
  name: string;
  rows: DocumentSummary[];
  attention: number;
}

const FILTERS: Filter[] = [
  ALL_FILTER,
  { key: "attention", label: "Needs attention", attention: true },
  { key: "assessed", label: "Assessed", status: "EVALUATED" },
  { key: "read", label: "Read", status: "EXTRACTED" },
  { key: "rejected", label: "Rejected", status: "REJECTED" },
];

export function DocumentsPage() {
  const { user } = useAuth();
  const [filter, setFilter] = useState("all");
  const [openId, setOpenId] = useState<string | null>(null);

  const active = FILTERS.find((f) => f.key === filter) ?? ALL_FILTER;

  const params = new URLSearchParams({ limit: "100" });
  if (active.status) params.set("status", active.status);
  if (active.attention) params.set("needs_attention", "true");

  const documents = useQuery({
    queryKey: ["documents", filter],
    queryFn: () => api.get<DocumentSummary[]>(`/documents?${params.toString()}`),
    // Poll only while something is mid-flight. A settled list does not need to
    // hammer the API, and the pipeline is background work with no push channel.
    refetchInterval: (query) => {
      const rows = query.state.data as DocumentSummary[] | undefined;
      const working = rows?.some((row) => DOCUMENT_IN_PROGRESS.includes(row.status));
      return working ? 4000 : false;
    },
  });

  const rows = documents.data ?? [];
  const attention = rows.filter((row) => NEEDS_ATTENTION.includes(row.status));

  // Grouped by workplace rather than shown as one flat list. An employer with ten
  // units reading a single list interleaved by upload time cannot tell whose
  // register is whose, and the establishment column repeating the same name down
  // twenty rows is not a substitute for structure.
  const groups = useMemo(() => {
    const byEstablishment = new Map<string, DocumentGroup>();

    for (const row of rows) {
      const key = row.establishment_id ?? UNATTACHED;
      let group = byEstablishment.get(key);

      if (!group) {
        group = {
          key,
          establishmentId: row.establishment_id,
          name: row.establishment_name ?? "Not yet attached to a workplace",
          rows: [],
          attention: 0,
        };
        byEstablishment.set(key, group);
      }

      group.rows.push(row);
      if (NEEDS_ATTENTION.includes(row.status)) group.attention += 1;
    }

    // Unattached first: those are the ones nothing will happen to until somebody
    // acts. Then alphabetical, so a given workplace is always in the same place.
    return [...byEstablishment.values()].sort((a, b) => {
      if (a.key === UNATTACHED) return -1;
      if (b.key === UNATTACHED) return 1;
      return a.name.localeCompare(b.name);
    });
  }, [rows]);

  return (
    <div className="space-y-10">
      <header className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2.5 rounded-full border border-sky-200 bg-sky-50 px-4 py-1.5 text-sm font-bold text-sky-800">
            <Layers className="h-4 w-4" />
            Filings
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950 sm:text-5xl">
            Documents
          </h1>
          <p className="mt-2 max-w-3xl text-base text-slate-700 sm:text-lg">
            Everything you have submitted, grouped by workplace. Open any document
            to see what was read from it and anything that needs checking.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Stat label="Submitted" value={rows.length} />
          <Stat
            label="Need attention"
            value={attention.length}
            tone={attention.length > 0 ? "warn" : "calm"}
          />
        </div>
      </header>

      {user && <UploadPanel onUploaded={(ids) => setOpenId(ids[0] ?? null)} />}

      {!user && (
        <Caution title="Sign in to submit documents">
          Uploading and reviewing documents requires an account. Open the Profile
          page to sign in.
        </Caution>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setFilter(item.key)}
            aria-pressed={filter === item.key}
            className={[
              "cursor-pointer rounded-full border px-4 py-2 text-sm font-bold transition-colors",
              filter === item.key
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 bg-white/90 text-slate-700 hover:bg-slate-50",
            ].join(" ")}
          >
            {item.label}
          </button>
        ))}

        <button
          type="button"
          onClick={() => void documents.refetch()}
          className="cursor-pointer ml-auto inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white/90 px-4 py-2 text-sm font-bold text-slate-700 transition-colors hover:bg-slate-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${documents.isFetching ? "animate-spin" : ""}`}
          />
          Refresh
        </button>
      </div>

      {/* One section per workplace */}
      {documents.isPending && (
        <div className="overflow-hidden rounded-3xl border border-sky-200/90 bg-white/95 shadow-sm backdrop-blur-xl">
          <SkeletonRows rows={6} columns={6} />
        </div>
      )}

      {documents.isError && (
        <div className="overflow-hidden rounded-3xl border border-sky-200/90 bg-white/95 shadow-sm backdrop-blur-xl">
          <ErrorState
            error={documents.error}
            context="the document list"
            onRetry={() => void documents.refetch()}
          />
        </div>
      )}

      {documents.isSuccess && rows.length === 0 && (
        <div className="overflow-hidden rounded-3xl border border-sky-200/90 bg-white/95 shadow-sm backdrop-blur-xl">
          <EmptyState
            icon={FolderOpen}
            title="Nothing submitted yet"
            description={
              filter === "all"
                ? "Submit a wage register, muster roll or challan above. Each document is identified, read, and checked against the Labour Codes."
                : "No documents match this filter."
            }
          />
        </div>
      )}

      {documents.isSuccess && groups.length > 0 && (
        <div className="space-y-6">
          {groups.map((group) => {
            const unattached = group.key === UNATTACHED;

            return (
              <section
                key={group.key}
                className={[
                  "overflow-hidden rounded-3xl border bg-white/95 shadow-sm backdrop-blur-xl",
                  unattached ? "border-amber-300" : "border-sky-200/90",
                ].join(" ")}
              >
                <header
                  className={[
                    "flex flex-wrap items-center justify-between gap-3 border-b px-6 py-4",
                    unattached
                      ? "border-amber-200 bg-amber-50/80"
                      : "border-slate-200 bg-slate-50/90",
                  ].join(" ")}
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div
                      className={[
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border",
                        unattached
                          ? "border-amber-300 bg-white text-amber-700"
                          : "border-sky-200 bg-white text-sky-700",
                      ].join(" ")}
                    >
                      {unattached ? (
                        <AlertTriangle className="h-4.5 w-4.5" />
                      ) : (
                        <Building2 className="h-4.5 w-4.5" />
                      )}
                    </div>

                    <div className="min-w-0">
                      <h2 className="truncate text-base font-bold text-slate-900">
                        {group.name}
                      </h2>
                      <p className="text-xs text-slate-600">
                        {group.rows.length} document
                        {group.rows.length === 1 ? "" : "s"}
                        {group.attention > 0 && (
                          <span className="font-semibold text-amber-800">
                            {" "}
                            · {group.attention} need
                            {group.attention === 1 ? "s" : ""} attention
                          </span>
                        )}
                      </p>
                    </div>
                  </div>

                  {group.establishmentId && (
                    <a
                      href={`/findings?establishment_id=${group.establishmentId}`}
                      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-300 bg-white px-4 py-1.5 text-xs font-bold text-slate-700 transition-colors hover:bg-slate-50"
                    >
                      <FileSearch className="h-3.5 w-3.5" />
                      Findings
                    </a>
                  )}
                </header>

                {unattached && (
                  <p className="border-b border-amber-200 bg-amber-50/40 px-6 py-3 text-xs leading-relaxed text-amber-950">
                    The workplace name on these documents could not be read clearly
                    enough to attach them. Nothing is assessed until they are
                    attached. Open one to attach it, or upload it again choosing the
                    workplace yourself.
                  </p>
                )}

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-slate-200 text-xs uppercase tracking-wider text-slate-600">
                      <tr>
                        <th scope="col" className="px-6 py-3 font-bold">File</th>
                        <th scope="col" className="px-6 py-3 font-bold">
                          Identified as
                        </th>
                        <th scope="col" className="px-6 py-3 font-bold">Period</th>
                        <th scope="col" className="px-6 py-3 font-bold">State</th>
                        <th scope="col" className="px-6 py-3 font-bold">Submitted</th>
                        <th scope="col" className="px-6 py-3">
                          <span className="sr-only">Open</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {group.rows.map((row) => (
                        <tr
                          key={row.id}
                          onClick={() => setOpenId(row.id)}
                          className="cursor-pointer transition-colors hover:bg-sky-50/50"
                        >
                          <td className="px-6 py-4">
                            <p className="font-bold text-slate-900">
                              {row.original_filename}
                            </p>
                            <p className="mt-0.5 font-mono text-xs text-slate-500">
                              {bytes(row.byte_size)} · {row.page_count} page
                              {row.page_count === 1 ? "" : "s"}
                            </p>
                          </td>

                          <td className="px-6 py-4">
                            <span className="font-semibold text-slate-800">
                              {DOCUMENT_TYPE_LABELS[row.doc_type]}
                            </span>
                            {row.doc_type_confidence !== null &&
                              row.doc_type !== "UNKNOWN" && (
                                <p className="mt-0.5 text-xs text-slate-500">
                                  {Math.round(row.doc_type_confidence * 100)}%
                                  confidence
                                </p>
                              )}
                          </td>

                          <td className="px-6 py-4 text-slate-700">
                            {row.period_start
                              ? period(row.period_start, row.period_end)
                              : "—"}
                          </td>

                          <td className="px-6 py-4">
                            <div className="flex flex-col items-start gap-1.5">
                              <DocumentStatusBadge status={row.status} />
                              {row.review_reason_count > 0 && (
                                <span className="text-xs font-semibold text-amber-800">
                                  {row.review_reason_count} point
                                  {row.review_reason_count === 1 ? "" : "s"} to check
                                </span>
                              )}
                            </div>
                          </td>

                          <td className="px-6 py-4 text-xs text-slate-500">
                            {relative(row.uploaded_at)}
                          </td>

                          <td className="px-6 py-4 text-right">
                            <ChevronRight className="ml-auto h-4 w-4 text-slate-400" />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}
        </div>
      )}

      {openId && (
        <DocumentDrawer documentId={openId} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "calm",
}: {
  label: string;
  value: number;
  tone?: "calm" | "warn";
}) {
  return (
    <div
      className={[
        "rounded-3xl border px-6 py-3.5 text-center shadow-sm",
        tone === "warn"
          ? "border-amber-300 bg-amber-50/90"
          : "border-slate-200 bg-white/85",
      ].join(" ")}
    >
      <span className="block text-xs font-bold uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span className="text-xl font-extrabold text-slate-900">{value}</span>
    </div>
  );
}

/** Detail drawer.
 *
 *  Polls while the document is mid-pipeline so an employer watching an upload
 *  sees it progress from queued to identified to read, rather than having to
 *  reload and guess.
 */
function DocumentDrawer({
  documentId,
  onClose,
}: {
  documentId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();

  const detail = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.get<DocumentDetail>(`/documents/${documentId}`),
    refetchInterval: (query) => {
      const data = query.state.data as DocumentDetail | undefined;
      return data && DOCUMENT_IN_PROGRESS.includes(data.status) ? 3500 : false;
    },
  });

  const reprocess = useMutation({
    mutationFn: () => api.post<{ status: string }>(`/documents/${documentId}/reprocess`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const document = detail.data;

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
        aria-label="Document detail"
        className="relative flex h-full w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
          <div className="min-w-0">
            <p className="truncate text-lg font-bold text-slate-900">
              {document?.original_filename ?? "Document"}
            </p>
            {document && (
              <p className="mt-1 text-xs text-slate-500">
                Submitted {dateTime(document.uploaded_at)}
                {document.processed_at && ` · read ${relative(document.processed_at)}`}
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
          {detail.isPending && <SkeletonRows rows={5} columns={2} />}
          {detail.isError && (
            <ErrorState error={detail.error} context="this document" />
          )}

          {document && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <DocumentStatusBadge status={document.status} />
                <Badge tone="neutral">
                  {DOCUMENT_TYPE_LABELS[document.doc_type]}
                </Badge>
                {document.extraction_mode && (
                  <Badge
                    tone={
                      document.extraction_mode === "NATIVE_PDF"
                        ? "good"
                        : document.extraction_mode === "OCR_PLUS_VISION"
                          ? "low"
                          : "medium"
                    }
                  >
                    <ScanLine aria-hidden="true" className="h-3 w-3" />
                    {EXTRACTION_MODE_LABELS[document.extraction_mode]}
                  </Badge>
                )}
                {document.schema_source && (
                  <Badge tone="info">
                    {SCHEMA_SOURCE_LABELS[document.schema_source]}
                  </Badge>
                )}
                {document.contains_redacted_pii && (
                  <Badge tone="medium">
                    <ShieldAlert aria-hidden="true" className="h-3 w-3" />
                    Contains worker identifiers
                  </Badge>
                )}
              </div>

              {document.status === "REJECTED" && document.rejection_reason && (
                <Caution title="Rejected at upload">
                  {document.rejection_reason}
                </Caution>
              )}

              {document.status === "FAILED" && document.rejection_reason && (
                <Caution title="Reading failed">
                  {document.rejection_reason}
                </Caution>
              )}

              {document.status === "NEEDS_BINDING" && (
                <Caution title="Not attached to an establishment">
                  This document could not be matched to an establishment or period
                  with enough confidence to attach it automatically. It was left
                  unattached rather than guessed at, because a register attached to
                  the wrong employer produces findings against a business that
                  never filed it.
                </Caution>
              )}

              {/* Facts */}
              <section className="grid gap-3 sm:grid-cols-2">
                <Field label="Establishment">
                  {document.establishment_name ?? "Not attached"}
                </Field>
                <Field label="Period covered">
                  {document.period_start
                    ? period(document.period_start, document.period_end)
                    : "Not determined"}
                </Field>
                <Field label="Pages">{document.page_count}</Field>
                <Field label="Size">{bytes(document.byte_size)}</Field>
              </section>

              {/* What was extracted */}
              {Object.values(document.row_counts).some((count) => count > 0) && (
                <section className="space-y-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                    Records read
                  </h3>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {Object.entries(document.row_counts)
                      .filter(([, count]) => count > 0)
                      .map(([key, count]) => (
                        <div
                          key={key}
                          className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3"
                        >
                          <p className="text-xl font-extrabold text-slate-900">{count}</p>
                          <p className="text-xs font-semibold text-slate-600">
                            {key.replace(/_/g, " ")}
                          </p>
                        </div>
                      ))}
                  </div>
                </section>
              )}

              {/* Points to check. Named plainly: these are the reasons a human is
                  being asked to look, not a generic warning. */}
              {document.review_reasons.length > 0 && (
                <section className="space-y-2">
                  <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-amber-800">
                    <AlertTriangle className="h-4 w-4" />
                    {document.review_reasons.length} point
                    {document.review_reasons.length === 1 ? "" : "s"} to check
                  </h3>
                  <ul className="space-y-2">
                    {document.review_reasons.map((reason, index) => (
                      <li
                        key={index}
                        className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm leading-relaxed text-amber-950"
                      >
                        {reason}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Header fields */}
              {document.fields.length > 0 && (
                <section className="space-y-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                    Read from the header
                  </h3>
                  <dl className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200">
                    {document.fields.map((field) => (
                      <div
                        key={field.name}
                        className="flex items-baseline justify-between gap-4 px-4 py-2.5"
                      >
                        <dt className="text-xs font-semibold text-slate-600">
                          {field.name.replace(/_/g, " ")}
                        </dt>
                        <dd className="text-right text-sm font-bold text-slate-900">
                          {field.value_text ?? field.value_date ?? field.value_number ?? "—"}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </section>
              )}

              {/* Pages */}
              {document.pages.length > 0 && (
                <section className="space-y-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                    Pages
                  </h3>
                  <ul className="space-y-2">
                    {document.pages.map((page) => (
                      <li
                        key={page.page_number}
                        className="rounded-2xl border border-slate-200 px-4 py-3"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-sm font-bold text-slate-800">
                            Page {page.page_number}
                          </span>
                          <div className="flex items-center gap-2">
                            {page.has_coordinates ? (
                              <Badge tone="good">Cell coordinates available</Badge>
                            ) : (
                              <Badge tone="medium">No cell coordinates</Badge>
                            )}
                            {page.ocr_provider && (
                              <Badge tone="info">{page.ocr_provider}</Badge>
                            )}
                          </div>
                        </div>
                        {page.ocr_failed_reason && (
                          <p className="mt-1.5 text-xs leading-relaxed text-amber-800">
                            OCR did not succeed on this page ({page.ocr_failed_reason}).
                            It was read from the image alone, so evidence from it is
                            page-level.
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Job trace */}
              {document.latest_job && (
                <section className="space-y-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                    Processing
                  </h3>
                  <div className="space-y-2 rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-3 text-xs">
                    <p className="font-semibold text-slate-700">
                      {document.latest_job.status}
                      {document.latest_job.finished_at &&
                        ` · finished ${relative(document.latest_job.finished_at)}`}
                    </p>
                    {document.latest_job.error && (
                      <p className="font-semibold text-rose-700">
                        {document.latest_job.error}
                      </p>
                    )}
                    {Object.keys(document.latest_job.detail ?? {}).length > 0 && (
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px] text-slate-600">
                        {Object.entries(document.latest_job.detail).map(([key, value]) => (
                          <div key={key} className="flex justify-between gap-2">
                            <dt className="truncate">{key}</dt>
                            <dd className="font-bold text-slate-800">
                              {Array.isArray(value)
                                ? value.length
                                : String(value ?? "—")}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </div>
                </section>
              )}
            </>
          )}
        </div>

        <footer className="flex items-center gap-3 border-t border-slate-200 bg-slate-50/80 px-6 py-4">
          <button
            type="button"
            onClick={() => reprocess.mutate()}
            disabled={reprocess.isPending || document?.status === "REJECTED"}
            className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-slate-800 disabled:opacity-40"
          >
            <RefreshCw
              className={`h-4 w-4 ${reprocess.isPending ? "animate-spin" : ""}`}
            />
            Read again
          </button>

          {document?.establishment_id && (
            <a
              href={`/findings?establishment_id=${document.establishment_id}`}
              className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-5 py-2.5 text-sm font-bold text-slate-800 transition-colors hover:bg-slate-50"
            >
              <FileSearch className="h-4 w-4" />
              Findings
            </a>
          )}

          {reprocess.isSuccess && (
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
              <Link2 className="h-3.5 w-3.5" />
              Queued. Everything read from it previously has been discarded.
            </span>
          )}
        </footer>
      </aside>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-3">
      <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <p className="mt-0.5 text-sm font-bold text-slate-900">{children}</p>
    </div>
  );
}
