import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  FileText,
  Loader2,
  Lock,
  RefreshCw,
  ShieldAlert,
  UploadCloud,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { UploadPanel } from "@/components/UploadPanel";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { bytes } from "@/lib/format";
import {
  DOCUMENT_STATUS_LABELS,
  DOCUMENT_TYPE_LABELS,
  type DocumentDetail,
  type DocumentStatus,
} from "@/lib/types";

const ACTIVE_UPLOADS_KEY = "shram-drishti-active-uploads";

const TERMINAL = new Set<DocumentStatus>([
  "REJECTED",
  "NEEDS_BINDING",
  "NEEDS_REVIEW",
  "EVALUATED",
  "FAILED",
  "SUPERSEDED",
]);

const FALLBACK_PROGRESS: Record<DocumentStatus, number> = {
  RECEIVED: 5,
  REJECTED: 100,
  NORMALISED: 60,
  CLASSIFIED: 68,
  NEEDS_BINDING: 100,
  EXTRACTED: 90,
  NEEDS_REVIEW: 100,
  VERIFIED: 94,
  EVALUATED: 100,
  SUPERSEDED: 100,
  FAILED: 100,
};

function restoredUploadIds(): string[] {
  try {
    const value = JSON.parse(sessionStorage.getItem(ACTIVE_UPLOADS_KEY) ?? "[]");
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

export function DocumentsPage() {
  const { user } = useAuth();
  const [activeIds, setActiveIds] = useState<string[]>(restoredUploadIds);

  useEffect(() => {
    sessionStorage.setItem(ACTIVE_UPLOADS_KEY, JSON.stringify(activeIds));
  }, [activeIds]);

  if (!user) {
    return (
      <div className="mx-auto max-w-5xl py-12">
        <div className="rounded-3xl border border-amber-200 bg-white/95 p-10 text-center shadow-xl">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-amber-100 text-amber-700">
            <Lock className="h-8 w-8" />
          </div>
          <h1 className="mt-5 text-3xl font-black text-slate-950">Document upload</h1>
          <p className="mx-auto mt-2 max-w-xl text-slate-600">
            Sign in before submitting workplace records. Uploaded files and their
            extracted employee data remain private to your organisation.
          </p>
          <Link
            to="/profile"
            state={{ from: "/documents" }}
            className="mt-7 inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-7 py-3.5 font-bold text-white shadow-lg hover:bg-slate-800"
          >
            <Lock className="h-4 w-4" />
            Sign in
          </Link>
        </div>
      </div>
    );
  }

  function addUploads(ids: string[]) {
    setActiveIds((current) => [...new Set([...ids, ...current])]);
  }

  function dismiss(id: string) {
    setActiveIds((current) => current.filter((item) => item !== id));
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-3 border-b border-sky-100/80 pb-6">
        <div className="inline-flex w-fit items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-4 py-1.5 text-sm font-bold text-sky-800">
          <UploadCloud className="h-4 w-4" />
          Secure document intake
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-950 sm:text-5xl">
          Upload documents
        </h1>
        <p className="max-w-3xl text-base text-slate-700 sm:text-lg">
          Submit scans or registers and follow every file from upload through OCR,
          extraction, and assessment. This page shows only your current uploads.
        </p>
      </header>

      <UploadPanel onUploaded={addUploads} />

      <section className="space-y-4" aria-labelledby="processing-title">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 id="processing-title" className="text-xl font-extrabold text-slate-950">
              Processing progress
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Progress comes from the backend stages, not from a timer.
            </p>
          </div>
          {activeIds.length > 0 && (
            <span className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-bold text-sky-800">
              {activeIds.length} current
            </span>
          )}
        </div>

        {activeIds.length === 0 ? (
          <div className="rounded-3xl border-2 border-dashed border-slate-300 bg-white/70 p-10 text-center">
            <FileText className="mx-auto h-10 w-10 text-slate-400" />
            <p className="mt-3 font-bold text-slate-800">No current uploads</p>
            <p className="mt-1 text-sm text-slate-500">
              Choose files above. Each accepted file will appear here immediately.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {activeIds.map((id) => (
              <DocumentProgressCard key={id} documentId={id} onDismiss={() => dismiss(id)} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function DocumentProgressCard({
  documentId,
  onDismiss,
}: {
  documentId: string;
  onDismiss: () => void;
}) {
  const document = useQuery({
    queryKey: ["document-progress", documentId],
    queryFn: () => api.get<DocumentDetail>(`/documents/${documentId}`),
    refetchInterval: (query) => {
      const current = query.state.data as DocumentDetail | undefined;
      return current && TERMINAL.has(current.status) ? false : 2000;
    },
    retry: 2,
  });

  if (document.isPending) {
    return (
      <div className="rounded-3xl border border-sky-200 bg-white/95 p-6 shadow-sm">
        <div className="flex items-center gap-3 text-sky-700">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="font-bold">Loading upload status…</span>
        </div>
      </div>
    );
  }

  if (document.isError) {
    return (
      <div className="rounded-3xl border border-rose-200 bg-rose-50/80 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="flex items-center gap-2 font-bold text-rose-900">
              <ShieldAlert className="h-5 w-5" />
              Status temporarily unavailable
            </p>
            <p className="mt-1 text-sm text-rose-800">
              The file ID is preserved. Retry after the API is available.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void document.refetch()}
            className="rounded-full border border-rose-300 bg-white p-2 text-rose-700"
            aria-label="Retry status"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>
    );
  }

  const item = document.data;
  const rawProgress = Number(item.latest_job?.detail.progress);
  const progress = Number.isFinite(rawProgress)
    ? Math.max(0, Math.min(100, rawProgress))
    : FALLBACK_PROGRESS[item.status];
  const rawStage = item.latest_job?.detail.stage;
  const stage =
    item.status === "EVALUATED"
      ? "Complete"
      : typeof rawStage === "string"
        ? rawStage
        : DOCUMENT_STATUS_LABELS[item.status];
  const failed = item.status === "FAILED" || item.status === "REJECTED";
  const complete = item.status === "EVALUATED";
  const needsAction = item.status === "NEEDS_BINDING" || item.status === "NEEDS_REVIEW";
  const pagesCompleted = Number(item.latest_job?.detail.pages_completed);
  const pagesTotal = Number(item.latest_job?.detail.pages_total);

  return (
    <article
      className={[
        "overflow-hidden rounded-3xl border bg-white/95 shadow-[0_10px_35px_rgba(15,23,42,0.07)]",
        failed
          ? "border-rose-300"
          : needsAction
            ? "border-amber-300"
            : complete
              ? "border-emerald-300"
              : "border-sky-300",
      ].join(" ")}
    >
      <div className="flex items-start gap-4 p-6">
        <div
          className={[
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl",
            failed
              ? "bg-rose-100 text-rose-700"
              : complete
                ? "bg-emerald-100 text-emerald-700"
                : "bg-sky-100 text-sky-700",
          ].join(" ")}
        >
          {failed ? (
            <ShieldAlert className="h-5 w-5" />
          ) : complete ? (
            <CheckCircle2 className="h-5 w-5" />
          ) : (
            <Loader2 className="h-5 w-5 animate-spin" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="truncate font-extrabold text-slate-950">
                {item.original_filename}
              </h3>
              <p className="mt-0.5 text-xs text-slate-500">
                {bytes(item.byte_size)} · {item.page_count} page
                {item.page_count === 1 ? "" : "s"}
              </p>
            </div>
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label={`Dismiss ${item.original_filename}`}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-4 flex items-center justify-between gap-3 text-sm">
            <span className="font-bold text-slate-800">{stage}</span>
            <span className="font-black tabular-nums text-slate-700">{Math.round(progress)}%</span>
          </div>
          <div
            className="mt-2 h-3 overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress)}
            aria-label={`${item.original_filename} processing progress`}
          >
            <div
              className={[
                "h-full rounded-full transition-[width] duration-700",
                failed
                  ? "bg-rose-500"
                  : needsAction
                    ? "bg-amber-500"
                    : complete
                      ? "bg-emerald-500"
                      : "bg-gradient-to-r from-sky-500 to-cyan-400",
              ].join(" ")}
              style={{ width: `${progress}%` }}
            />
          </div>

          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
            <span>{DOCUMENT_TYPE_LABELS[item.doc_type]}</span>
            <span>{item.establishment_name ?? "Workplace being identified"}</span>
            {Number.isFinite(pagesCompleted) && Number.isFinite(pagesTotal) && pagesTotal > 0 && (
              <span>
                {pagesCompleted}/{pagesTotal} pages read
              </span>
            )}
          </div>

          {failed && item.rejection_reason && (
            <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-800">
              {item.rejection_reason}
            </p>
          )}
          {needsAction && item.review_reasons.length > 0 && (
            <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-900">
              {item.review_reasons[0]}
            </p>
          )}
        </div>
      </div>
    </article>
  );
}
