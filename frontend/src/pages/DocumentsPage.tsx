import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
import type { EstablishmentProcessingOut } from "@/lib/types";

const ACTIVE_UPLOADS_KEY = "shram-drishti-active-establishments-v3";

interface ActiveEstablishment {
  establishmentId: string;
  establishmentName: string;
  batchId: string;
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
        typeof candidate.batchId === "string"
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
      // The current page still tracks progress when browser storage is blocked.
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
    const item: ActiveEstablishment = {
      establishmentId: batch.establishmentId,
      establishmentName: batch.establishmentName,
      batchId: batch.batchId,
    };
    setActiveEstablishments((current) => [
      item,
      ...current.filter(
        (existing) => existing.establishmentId !== batch.establishmentId,
      ),
    ]);
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
          Establishment processing
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
  const queryClient = useQueryClient();
  const progress = useQuery({
    queryKey: ["establishment-processing", item.establishmentId, item.batchId],
    queryFn: () =>
      api.get<EstablishmentProcessingOut>(
        `/establishments/${item.establishmentId}/processing`,
      ),
    refetchInterval: (query: { state: { data?: unknown } }) => {
      const current = query.state.data as EstablishmentProcessingOut | undefined;
      return current?.terminal ? false : 2000;
    },
    retry: 2,
  });

  const status = progress.data;
  useEffect(() => {
    if (!status?.terminal) return;
    void queryClient.invalidateQueries({ queryKey: ["establishments"] });
    void queryClient.invalidateQueries({
      queryKey: ["establishment", item.establishmentId],
    });
    void queryClient.invalidateQueries({ queryKey: ["findings"] });
  }, [item.establishmentId, queryClient, status?.terminal]);

  const unavailable = progress.isError && !status;
  const failed = Boolean(status?.terminal && !status.successful);
  const complete = Boolean(status?.terminal && status.successful);
  const value = status?.progress ?? 0;
  const label = unavailable ? "Status unavailable" : status?.stage ?? "Uploading documents";

  return (
    <article
      className={[
        "overflow-hidden rounded-3xl border bg-white/95 p-6 shadow-[0_10px_35px_rgba(15,23,42,0.07)]",
        failed || unavailable
          ? "border-rose-300"
          : complete
            ? status?.needs_action
              ? "border-amber-300"
              : "border-emerald-300"
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
              {Math.round(value)}%
            </span>
          </div>
          <div
            className="mt-2 h-3 overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(value)}
            aria-label={`${item.establishmentName} processing progress`}
          >
            <div
              className={[
                "h-full rounded-full transition-[width] duration-700",
                failed || unavailable
                  ? "bg-rose-500"
                  : complete
                    ? "bg-emerald-500"
                    : "bg-gradient-to-r from-sky-500 to-cyan-400",
              ].join(" ")}
              style={{ width: `${value}%` }}
            />
          </div>

          {status && status.total_documents > 0 && !status.terminal && (
            <p className="mt-2 text-xs font-semibold text-slate-600">
              {status.finished_documents} of {status.total_documents} documents finished
            </p>
          )}
          {complete && status?.needs_action && (
            <p className="mt-3 text-xs font-semibold text-amber-800">
              Automated checks are complete. Some extracted details should be confirmed by a reviewer.
            </p>
          )}
          {unavailable && (
            <button
              type="button"
              onClick={() => void progress.refetch()}
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
