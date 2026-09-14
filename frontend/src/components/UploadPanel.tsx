import { useCallback, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  FileText,
  Image as ImageIcon,
  Loader2,
  Search,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";

import { api, apiBaseUrl, refreshAccessToken } from "@/lib/api";
import { getAccessToken } from "@/lib/tokens";
import { bytes } from "@/lib/format";
import type { EstablishmentSummary, UploadResponse } from "@/lib/types";

/** Upload panel.
 *
 *  Designed around what actually goes wrong when an employer's clerk uploads a
 *  month of filings.
 *
 *  **Many files at once.** A wage period means a wage register, a muster roll, an
 *  EPF challan and an ESIC challan. Uploading them one at a time turns a
 *  two-minute job into a twenty-minute one, so the whole batch is queued and each
 *  file reports its own progress.
 *
 *  **No document type field.** The backend identifies the document from its own
 *  contents and refuses to guess when unsure. Asking a clerk to pick a type adds
 *  a second source of truth that is wrong more often than the classifier, and a
 *  mislabelled document gets read against the wrong schema — which produces
 *  confident nonsense rather than an obvious failure.
 *
 *  **The workplace is asked as a question, not offered as a dropdown.** This used
 *  to be a pre-populated select, which failed twice over: "establishment" was
 *  never explained, and an employer with ten units had to scroll a list whose
 *  first entry looked pre-chosen. Now it is an explicit choice between taking the
 *  name from the document and picking one, with the list only appearing — and only
 *  loading — if the second is chosen.
 *
 *  **Real progress, not a spinner.** XHR rather than fetch, only because fetch
 *  cannot report upload progress. A fifty-megabyte scan over a slow line needs a
 *  progress bar or the user assumes it has hung and uploads it again.
 */

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,.txt,.csv,.ecr";
const MAX_BYTES = 64 * 1024 * 1024;

/** How many workplaces to list before asking the user to type. Long enough to
 *  scan, short enough that nobody scrolls looking for theirs. */
const MAX_VISIBLE_ESTABLISHMENTS = 8;

type ItemStatus = "queued" | "uploading" | "done" | "error";

/** Where the workplace comes from. Default is the document, because the header is
 *  usually right and because a pre-selected list invites the wrong pick. */
type BindMode = "auto" | "manual";

interface QueueItem {
  key: string;
  file: File;
  status: ItemStatus;
  progress: number;
  message?: string | undefined;
  documentId?: string | undefined;
}

interface UploadPanelProps {
  onUploaded?: (documentIds: string[]) => void;
}

export function UploadPanel({ onUploaded }: UploadPanelProps) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);

  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [bindMode, setBindMode] = useState<BindMode>("auto");
  const [establishmentId, setEstablishmentId] = useState("");
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);

  // Only fetched when the user asks to choose for themselves. An employer with one
  // unit never needs this list, and a failure to load it must not block uploading:
  // the header binding does not depend on it.
  const establishments = useQuery({
    queryKey: ["establishments", "for-upload"],
    queryFn: () => api.get<EstablishmentSummary[]>("/establishments?limit=200"),
    enabled: bindMode === "manual",
    retry: false,
  });

  // Typed filtering rather than a long dropdown. With ten or more units a
  // pre-populated select is a scrolling exercise, and the first entry sitting
  // there selected-looking is what makes people file against the wrong workplace.
  const { matches, truncated } = useMemo(() => {
    const all = establishments.data ?? [];
    const needle = filter.trim().toLowerCase();

    const hits = needle
      ? all.filter((item) =>
          [item.name, item.lin, item.district, item.state_code]
            .filter(Boolean)
            .some((field) => String(field).toLowerCase().includes(needle)),
        )
      : all;

    return {
      matches: hits.slice(0, MAX_VISIBLE_ESTABLISHMENTS),
      truncated: Math.max(0, hits.length - MAX_VISIBLE_ESTABLISHMENTS),
    };
  }, [establishments.data, filter]);

  const addFiles = useCallback((files: FileList | File[]) => {
    const incoming = Array.from(files);
    if (!incoming.length) return;

    setQueue((current) => {
      const existing = new Set(current.map((item) => `${item.file.name}:${item.file.size}`));
      const added: QueueItem[] = [];

      for (const file of incoming) {
        const signature = `${file.name}:${file.size}`;
        if (existing.has(signature)) continue;
        existing.add(signature);

        // Rejected here as well as server-side. Pushing 200 MB up the wire only
        // to be told it is too large wastes the user's time and bandwidth.
        const tooLarge = file.size > MAX_BYTES;
        const empty = file.size === 0;

        added.push({
          key: `${signature}:${Math.random().toString(36).slice(2, 8)}`,
          file,
          status: tooLarge || empty ? "error" : "queued",
          progress: 0,
          message: tooLarge
            ? `${bytes(file.size)} exceeds the 64 MB limit`
            : empty
              ? "This file is empty"
              : undefined,
        });
      }

      return [...current, ...added];
    });
  }, []);

  function patch(key: string, changes: Partial<QueueItem>) {
    setQueue((current) =>
      current.map((item) => (item.key === key ? { ...item, ...changes } : item)),
    );
  }

  async function uploadAll() {
    const pending = queue.filter((item) => item.status === "queued");
    if (!pending.length) return;

    setBusy(true);
    const uploaded: string[] = [];

    // Send files sequentially so the web process handles one multipart body at a
    // time. Accepted files enter the backend's durable single-worker queue; this
    // loop never starts OCR/model work itself.
    for (const item of pending) {
      patch(item.key, { status: "uploading", progress: 0, message: undefined });

      try {
        const response = await uploadOne(item.file, establishmentId, (progress) =>
          patch(item.key, { progress }),
        );
        patch(item.key, {
          status: "done",
          progress: 100,
          documentId: response.document_id,
          message: response.message,
        });
        uploaded.push(response.document_id);
      } catch (error) {
        patch(item.key, {
          status: "error",
          progress: 0,
          message: describeUploadError(error),
        });
      }
    }

    setBusy(false);

    if (uploaded.length) {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      onUploaded?.(uploaded);
    }
  }

  const pendingCount = queue.filter((item) => item.status === "queued").length;
  const doneCount = queue.filter((item) => item.status === "done").length;
  const failedCount = queue.filter((item) => item.status === "error").length;

  return (
    <section className="space-y-5 rounded-3xl border border-sky-200/90 bg-white/95 p-6 shadow-[0_10px_35px_rgba(56,189,248,0.10)] backdrop-blur-xl sm:p-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2.5 text-xl font-bold text-slate-900">
            <UploadCloud className="h-6 w-6 text-sky-600" />
            Submit documents
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-600">
            You can select all the documents for one wage period together. You do
            not need to say what each file is — that is taken from the document
            itself.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-xs">
          <p className="font-bold text-slate-700">Accepted</p>
          <p className="mt-0.5 text-slate-500">PDF, scans, photos, EPF text files</p>
          <p className="mt-1 text-slate-500">Up to 64 MB and 500 pages each</p>
        </div>
      </header>

      {/* Which workplace these documents belong to */}
      <fieldset className="rounded-2xl border border-slate-200 bg-slate-50/60 p-5">
        <legend className="px-1 text-sm font-bold text-slate-900">
          Which workplace do these documents belong to?
        </legend>

        <p className="mt-1 text-xs leading-relaxed text-slate-600">
          An establishment is one registered workplace — a single factory, unit,
          site, shop or office. Compliance is assessed separately for each one, so
          documents have to be attached to the right workplace.
        </p>

        <div className="mt-4 space-y-2.5">
          <label
            className={[
              "flex cursor-pointer items-start gap-3 rounded-2xl border p-3.5 transition-colors",
              bindMode === "auto"
                ? "border-sky-500 bg-white shadow-sm"
                : "border-slate-200 bg-white/70 hover:border-slate-300",
            ].join(" ")}
          >
            <input
              type="radio"
              name="bind-mode"
              checked={bindMode === "auto"}
              onChange={() => {
                setBindMode("auto");
                setEstablishmentId("");
              }}
              className="mt-0.5 h-4 w-4 cursor-pointer border-slate-400 text-sky-600"
            />
            <span>
              <span className="block text-sm font-bold text-slate-900">
                Take it from the document
              </span>
              <span className="mt-0.5 block text-xs leading-relaxed text-slate-600">
                Most registers and challans carry the workplace name in the header.
                If it cannot be read clearly, the document is kept aside for you to
                attach yourself rather than filed against a guess.
              </span>
            </span>
          </label>

          <label
            className={[
              "flex cursor-pointer items-start gap-3 rounded-2xl border p-3.5 transition-colors",
              bindMode === "manual"
                ? "border-sky-500 bg-white shadow-sm"
                : "border-slate-200 bg-white/70 hover:border-slate-300",
            ].join(" ")}
          >
            <input
              type="radio"
              name="bind-mode"
              checked={bindMode === "manual"}
              onChange={() => setBindMode("manual")}
              className="mt-0.5 h-4 w-4 cursor-pointer border-slate-400 text-sky-600"
            />
            <span>
              <span className="block text-sm font-bold text-slate-900">
                I will choose the workplace
              </span>
              <span className="mt-0.5 block text-xs leading-relaxed text-slate-600">
                Useful when you run several units with similar names.
              </span>
            </span>
          </label>
        </div>

        {bindMode === "manual" && (
          <div className="mt-4 space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
            <label className="block">
              <span className="mb-1.5 block text-xs font-bold uppercase tracking-wider text-slate-700">
                Type a name to find the workplace
              </span>
              <div className="relative">
                <Search
                  aria-hidden="true"
                  className="pointer-events-none absolute left-3.5 top-3 h-4.5 w-4.5 text-slate-400"
                />
                <input
                  type="text"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  placeholder="Name, registration number or district"
                  autoComplete="off"
                  className="w-full rounded-xl border border-slate-300 bg-slate-50 py-2.5 pl-10 pr-4 text-sm text-slate-900 transition-colors focus:border-sky-600 focus:bg-white"
                />
              </div>
            </label>

            {establishments.isPending && (
              <p className="text-xs text-slate-500">Loading your workplaces…</p>
            )}

            {establishments.isError && (
              <p className="text-xs font-semibold text-rose-700">
                Your list of workplaces could not be loaded. You can still upload —
                choose "Take it from the document" above.
              </p>
            )}

            {establishments.isSuccess && matches.length === 0 && (
              <p className="text-xs text-slate-600">
                {filter
                  ? "No workplace matches what you typed."
                  : "No workplaces are registered under your account yet."}
              </p>
            )}

            {matches.length > 0 && (
              <ul className="max-h-56 space-y-1 overflow-y-auto">
                {matches.map((establishment) => {
                  const chosen = establishmentId === establishment.id;

                  return (
                    <li key={establishment.id}>
                      <button
                        type="button"
                        onClick={() =>
                          setEstablishmentId(chosen ? "" : establishment.id)
                        }
                        aria-pressed={chosen}
                        className={[
                          "flex w-full cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors",
                          chosen
                            ? "border-sky-600 bg-sky-50"
                            : "border-transparent hover:bg-slate-50",
                        ].join(" ")}
                      >
                        <Building2
                          aria-hidden="true"
                          className={[
                            "h-4 w-4 shrink-0",
                            chosen ? "text-sky-700" : "text-slate-400",
                          ].join(" ")}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold text-slate-900">
                            {establishment.name}
                          </span>
                          <span className="block truncate text-xs text-slate-500">
                            {[
                              establishment.district,
                              establishment.state_code,
                              establishment.lin,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </span>
                        {chosen && (
                          <CheckCircle2
                            aria-hidden="true"
                            className="h-4 w-4 shrink-0 text-sky-700"
                          />
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}

            {truncated > 0 && (
              <p className="text-xs text-slate-500">
                {truncated} more not shown. Type a few letters to narrow the list.
              </p>
            )}
          </div>
        )}
      </fieldset>

      {/* Dropzone */}
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (event.dataTransfer.files) addFiles(event.dataTransfer.files);
        }}
        className={[
          "rounded-3xl border-2 border-dashed p-8 text-center transition-colors sm:p-12",
          dragging
            ? "border-sky-500 bg-sky-50/80"
            : "border-slate-300 bg-slate-50/60 hover:border-sky-400 hover:bg-sky-50/40",
        ].join(" ")}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          onChange={(event) => {
            if (event.target.files) addFiles(event.target.files);
            // Cleared so choosing the same file again re-triggers change.
            event.target.value = "";
          }}
          className="sr-only"
          id="filing-upload-input"
        />

        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-sky-200 bg-white text-sky-600 shadow-sm">
          <UploadCloud className="h-7 w-7" />
        </div>

        <p className="mt-4 text-base font-bold text-slate-900">
          Drag your documents here, or{" "}
          <label
            htmlFor="filing-upload-input"
            className="cursor-pointer text-sky-700 underline decoration-sky-300 decoration-2 underline-offset-2 hover:text-sky-800"
          >
            browse your files
          </label>
        </p>
        <p className="mx-auto mt-1.5 max-w-md text-sm text-slate-600">
          Wage registers, muster rolls, EPF and ESIC challans, appointment letters,
          licences, accident registers, annual returns.
        </p>
      </div>

      {/* Queue */}
      {queue.length > 0 && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-bold text-slate-800">
              {queue.length} file{queue.length === 1 ? "" : "s"} selected
              {doneCount > 0 && (
                <span className="ml-2 font-semibold text-emerald-700">
                  {doneCount} submitted
                </span>
              )}
              {failedCount > 0 && (
                <span className="ml-2 font-semibold text-rose-700">
                  {failedCount} failed
                </span>
              )}
            </p>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setQueue([])}
                disabled={busy}
                className="cursor-pointer inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-40"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear
              </button>
              <button
                type="button"
                onClick={() => void uploadAll()}
                disabled={busy || pendingCount === 0}
                className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <UploadCloud className="h-4 w-4" />
                )}
                {busy
                  ? "Submitting…"
                  : `Submit ${pendingCount} document${pendingCount === 1 ? "" : "s"}`}
              </button>
            </div>
          </div>

          <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white">
            {queue.map((item) => (
              <QueueRow
                key={item.key}
                item={item}
                onRemove={() =>
                  setQueue((current) => current.filter((q) => q.key !== item.key))
                }
                removable={!busy && item.status !== "uploading"}
              />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function QueueRow({
  item,
  onRemove,
  removable,
}: {
  item: QueueItem;
  onRemove: () => void;
  removable: boolean;
}) {
  const isImage = /\.(png|jpe?g|tiff?|webp|bmp)$/i.test(item.file.name);
  const Icon = isImage ? ImageIcon : FileText;

  return (
    <li className="flex items-center gap-4 px-4 py-3.5">
      <div
        className={[
          "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border",
          item.status === "done"
            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
            : item.status === "error"
              ? "border-rose-200 bg-rose-50 text-rose-700"
              : "border-slate-200 bg-slate-50 text-slate-500",
        ].join(" ")}
      >
        {item.status === "done" ? (
          <CheckCircle2 className="h-5 w-5" />
        ) : item.status === "error" ? (
          <AlertTriangle className="h-5 w-5" />
        ) : item.status === "uploading" ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <Icon className="h-5 w-5" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-bold text-slate-900">{item.file.name}</p>
        <p className="mt-0.5 text-xs text-slate-500">
          {bytes(item.file.size)}
          {item.status === "uploading" && ` · ${item.progress}% uploaded`}
        </p>

        {item.status === "uploading" && (
          <div
            role="progressbar"
            aria-valuenow={item.progress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Uploading ${item.file.name}`}
            className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200"
          >
            <div
              className="h-full rounded-full bg-sky-600 transition-all duration-200"
              style={{ width: `${item.progress}%` }}
            />
          </div>
        )}

        {item.message && (
          <p
            className={[
              "mt-1 text-xs leading-relaxed",
              item.status === "error" ? "font-semibold text-rose-700" : "text-slate-600",
            ].join(" ")}
          >
            {item.message}
          </p>
        )}
      </div>

      {removable && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${item.file.name}`}
          className="cursor-pointer rounded-full p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </li>
  );
}

/** One multipart upload with progress and one transparent token refresh. */
type UploadFailure = {
  status: number;
  body?: string;
  requestId?: string | null;
  message?: string;
};

function uploadOne(
  file: File,
  establishmentId: string,
  onProgress: (percent: number) => void,
  isRetry = false,
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    if (establishmentId) form.append("establishment_id", establishmentId);

    const request = new XMLHttpRequest();
    request.open("POST", `${apiBaseUrl()}/documents`);
    request.timeout = 120_000;

    const token = getAccessToken();
    if (token) request.setRequestHeader("Authorization", `Bearer ${token}`);

    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    request.onload = async () => {
      if (request.status === 401 && !isRetry && (await refreshAccessToken())) {
        uploadOne(file, establishmentId, onProgress, true).then(resolve, reject);
        return;
      }

      const requestId = request.getResponseHeader("X-Request-ID");
      if (request.status >= 200 && request.status < 300) {
        try {
          const parsed = JSON.parse(request.responseText) as Partial<UploadResponse>;
          if (
            typeof parsed.document_id !== "string" ||
            typeof parsed.message !== "string" ||
            typeof parsed.status !== "string"
          ) {
            throw new Error("response shape is invalid");
          }
          resolve(parsed as UploadResponse);
        } catch {
          reject({
            status: 502,
            requestId,
            message:
              "The upload endpoint returned an invalid response. Refresh the document list before retrying; the file may already have been received.",
          } satisfies UploadFailure);
        }
        return;
      }
      reject({
        status: request.status,
        body: request.responseText,
        requestId,
      } satisfies UploadFailure);
    };

    request.onerror = () =>
      reject(
        new Error(
          "The API connection was interrupted. Refresh the document list before retrying; the file may already have been received.",
        ),
      );
    request.ontimeout = () =>
      reject(new Error("The API did not acknowledge this upload within two minutes."));
    request.onabort = () => reject(new Error("The upload was cancelled."));

    request.send(form);
  });
}

function describeUploadError(error: unknown): string {
  if (error && typeof error === "object" && "status" in error) {
    const { status, body, requestId, message } = error as UploadFailure;
    if (message) return requestId ? `${message} Request ID: ${requestId}.` : message;

    if (status === 401) {
      return "Your session expired during the upload. Sign in again and retry.";
    }
    if (status === 403) {
      return "Your role is not permitted to submit filings.";
    }
    if (status === 413) {
      return "The server rejected this file as too large.";
    }
    if (status === 404 || status === 405) {
      return (
        `The configured upload address ${apiBaseUrl()}/documents is not the API ` +
        `(HTTP ${status}).`
      );
    }

    if (body) {
      try {
        const parsed = JSON.parse(body) as { detail?: { message?: string } | string };
        const detail =
          typeof parsed.detail === "string"
            ? parsed.detail
            : parsed.detail?.message;
        if (detail) return requestId ? `${detail} Request ID: ${requestId}.` : detail;
      } catch {
        /* The status and request id below remain actionable. */
      }
    }

    const base =
      status >= 500
        ? "The API could not accept this upload."
        : `The server rejected this file (HTTP ${status}).`;
    return requestId ? `${base} Request ID: ${requestId}.` : base;
  }

  if (error instanceof Error) return error.message;
  return "This file could not be submitted.";
}
