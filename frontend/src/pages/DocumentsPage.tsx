import { useEffect, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  Loader2,
  Lock,
  RefreshCw,
  ShieldAlert,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import {
  UploadPanel,
  type EstablishmentUploadBatch,
} from "@/components/UploadPanel";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DocumentDetail, DocumentStatus } from "@/lib/types";

const ACTIVE_UPLOADS_KEY = "shram-drishti-active-establishments-v2";

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

function documentProgress(document: DocumentDetail): number {
  const raw = Number(document.latest_job?.detail.progress);
  return Number.isFinite(raw)
    ? Math.max(0, Math.min(100, raw))
    : FALLBACK_PROGRESS[document.status];
}

function processingSettled(document: DocumentDetail): boolean {
  return TERMINAL.has(document.status) && documentProgress(document) >= 100;
}

interface ActiveEstablishment {
  establishmentId: string;
  establishmentName: string;
  documentIds: string[];
}

function restoredUploads(): ActiveEstablishment[] {
  try {
    const value: unknown = JSON.parse(
      sessionStorage.getItem(ACTIVE_UPLOADS_KEY) ?? "[]",
    );
    if (!Array.isArray(value)) return [];

    return value.filter((item): item is ActiveEstablishment => {
      if (!item || typeof item !== "object") return false;
      const candidate = item as Partial<ActiveEstablishment>;
      return (
        typeof candidate.establishmentId === "string" &&
        typeof candidate.establishmentName === "string" &&
        Array.isArray(candidate.documentIds) &&
        candidate.documentIds.every((id) => typeof id === "string")
      );
    });
  } catch {
    return [];
  }
}

export function DocumentsPage() {
  const { user } = useAuth();
  const [activeEstablishments, setActiveEstablishments] =
    useState<ActiveEstablishment[]>(restoredUploads);

  useEffect(() => {
    try {
      sessionStorage.setItem(
        ACTIVE_UPLOADS_KEY,
        JSON.stringify(activeEstablishments),
      );
    } catch {
      // Progress still works for this page even when browser storage is blocked.
    }
  }, [activeEstablishments]);

  if (!user) {
    return (
      <div className="mx-auto max-w-5xl py-12">
        <div className="rounded-3xl border border-amber-200 bg-white/95 p-10 text-center shadow-xl">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-amber-100 text-amber-700">
            <Lock className="h-8 w-8" />
          </div>
          <h1 className="mt-5 text-3xl font-black text-slate-950">Document upload</h1>
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

  function addUploads(batch: EstablishmentUploadBatch) {
    setActiveEstablishments((current) => {
      const existing = current.find(
        (item) => item.establishmentId === batch.establishmentId,
      );
      if (!existing) return [batch, ...current];

      const merged: ActiveEstablishment = {
        establishmentId: batch.establishmentId,
        establishmentName: batch.establishmentName,
        documentIds: [...new Set([...batch.documentIds, ...existing.documentIds])],
      };
      return [
        merged,
        ...current.filter(
          (item) => item.establishmentId !== batch.establishmentId,
        ),
      ];
    });
  }

  function dismiss(establishmentId: string) {
    setActiveEstablishments((current) =>
      current.filter((item) => item.establishmentId !== establishmentId),
    );
  }

  return (
    <div className="space-y-8">
      <header className="border-b border-sky-100/80 pb-6">
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-950 sm:text-5xl">
          Upload documents
        </h1>
      </header>

      <UploadPanel onUploaded={addUploads} />

      <section className="space-y-4" aria-labelledby="processing-title">
        <h2 id="processing-title" className="text-xl font-extrabold text-slate-950">
          Document status
        </h2>

        {activeEstablishments.length === 0 ? (
          <div className="rounded-3xl border-2 border-dashed border-slate-300 bg-white/70 p-10 text-center">
            <Building2 className="mx-auto h-10 w-10 text-slate-400" />
            <p className="mt-3 font-bold text-slate-800">No current uploads</p>
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {activeEstablishments.map((item) => (
              <EstablishmentProgressCard
                key={item.establishmentId}
                item={item}
                onDismiss={() => dismiss(item.establishmentId)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function EstablishmentProgressCard({
  item,
  onDismiss,
}: {
  item: ActiveEstablishment;
  onDismiss: () => void;
}) {
  const queries = useQueries({
    queries: item.documentIds.map((documentId) => ({
      queryKey: ["document-progress", documentId],
      queryFn: () => api.get<DocumentDetail>(`/documents/${documentId}`),
      refetchInterval: (query: { state: { data?: unknown } }) => {
        const current = query.state.data as DocumentDetail | undefined;
        return current && processingSettled(current) ? false : 2000;
      },
      retry: 2,
    })),
  });

  const documents = queries
    .map((query) => query.data)
    .filter((document): document is DocumentDetail => Boolean(document));
  const progress = item.documentIds.length
    ? queries.reduce(
        (total, query) => total + (query.data ? documentProgress(query.data) : 0),
        0,
      ) / item.documentIds.length
    : 0;

  const unavailable = queries.some((query) => query.isError && !query.data);
  const failed = documents.some(
    (document) => document.status === "FAILED" || document.status === "REJECTED",
  );
  const needsAction = documents.some(
    (document) =>
      document.status === "NEEDS_BINDING" || document.status === "NEEDS_REVIEW",
  );
  const replaced = documents.some((document) => document.status === "SUPERSEDED");
  const complete =
    documents.length === item.documentIds.length &&
    documents.every(processingSettled) &&
    !failed;
  const displayedProgress = complete ? 100 : progress;

  const label = unavailable
    ? "Status unavailable"
    : failed
      ? "Processing failed"
      : complete
        ? "Completed"
        : "Processing";

  return (
    <article
      className={[
        "overflow-hidden rounded-3xl border bg-white/95 p-6 shadow-[0_10px_35px_rgba(15,23,42,0.07)]",
        failed || unavailable
          ? "border-rose-300"
          : needsAction
            ? "border-amber-300"
            : complete
              ? "border-emerald-300"
              : "border-sky-300",
      ].join(" ")}
    >
      <div className="flex items-start gap-4">
        <div
          className={[
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl",
            failed || unavailable
              ? "bg-rose-100 text-rose-700"
              : complete
                ? "bg-emerald-100 text-emerald-700"
                : "bg-sky-100 text-sky-700",
          ].join(" ")}
        >
          {failed || unavailable ? (
            <ShieldAlert className="h-5 w-5" />
          ) : complete ? (
            <CheckCircle2 className="h-5 w-5" />
          ) : (
            <Loader2 className="h-5 w-5 animate-spin" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <h3 className="truncate font-extrabold text-slate-950">
              {item.establishmentName}
            </h3>
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label={`Dismiss ${item.establishmentName}`}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-4 flex items-center justify-between gap-3 text-sm">
            <span className="font-bold text-slate-800">{label}</span>
            <span className="font-black tabular-nums text-slate-700">
              {Math.round(displayedProgress)}%
            </span>
          </div>
          <div
            className="mt-2 h-3 overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(displayedProgress)}
            aria-label={`${item.establishmentName} processing progress`}
          >
            <div
              className={[
                "h-full rounded-full transition-[width] duration-700",
                failed || unavailable
                  ? "bg-rose-500"
                  : needsAction
                    ? "bg-amber-500"
                    : complete
                      ? "bg-emerald-500"
                      : "bg-gradient-to-r from-sky-500 to-cyan-400",
              ].join(" ")}
              style={{ width: `${displayedProgress}%` }}
            />
          </div>

          {complete && needsAction && (
            <p className="mt-3 text-xs font-semibold text-amber-800">
              Automated checks are complete. Some extracted details should be confirmed by a reviewer.
            </p>
          )}
          {complete && replaced && (
            <p className="mt-2 text-xs font-semibold text-slate-600">
              A newer upload replaced an earlier file for this period.
            </p>
          )}

          {unavailable && (
            <button
              type="button"
              onClick={() => queries.forEach((query) => void query.refetch())}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-rose-700"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
