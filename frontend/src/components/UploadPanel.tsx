import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  FileText,
  Image as ImageIcon,
  Loader2,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import { getAccessToken } from "@/lib/tokens";
import { bytes } from "@/lib/format";
import type { EstablishmentSummary } from "@/lib/types";

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
 *  **Establishment is optional.** The binder reads the header and matches it.
 *  Selecting it here simply removes a failure mode for an employer with several
 *  units, where headers are abbreviated and easily confused.
 *
 *  **Real progress, not a spinner.** XHR rather than fetch, only because fetch
 *  cannot report upload progress. A fifty-megabyte scan over a slow line needs a
 *  progress bar or the user assumes it has hung and uploads it again.
 */

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,.txt,.csv,.ecr";
const MAX_BYTES = 64 * 1024 * 1024;

type ItemStatus = "queued" | "uploading" | "done" | "error";

interface QueueItem {
  key: string;
  file: File;
  status: ItemStatus;
  progress: number;
  message?: string | undefined;
  documentId?: string | undefined;
  supersedes?: string | null | undefined;
}

interface UploadPanelProps {
  onUploaded?: (documentIds: string[]) => void;
}

export function UploadPanel({ onUploaded }: UploadPanelProps) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);

  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [establishmentId, setEstablishmentId] = useState("");
  const [busy, setBusy] = useState(false);

  // Offered as a convenience only, so a failure to load the list must not block
  // uploading. The backend binds from the document header regardless.
  const establishments = useQuery({
    queryKey: ["establishments", "for-upload"],
    queryFn: () => api.get<EstablishmentSummary[]>("/establishments?limit=200"),
    retry: false,
  });

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

    // Sequential rather than parallel. Each accepted upload immediately starts
    // OCR and model calls on a background thread, and firing ten at once would
    // exhaust the OCR daily quota for every other establishment in the queue.
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
          supersedes: response.supersedes_document_id,
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
            Submit filings
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-600">
            Drop a whole wage period at once. Each document is identified from its
            own contents, matched to an establishment and period, then read by OCR
            and a vision model together so every figure can be traced back to a
            cell on the page.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-xs">
          <p className="font-bold text-slate-700">Accepted</p>
          <p className="mt-0.5 text-slate-500">PDF, scans, photos, EPF text files</p>
          <p className="mt-1 text-slate-500">Up to 64 MB and 500 pages each</p>
        </div>
      </header>

      {/* Establishment selector */}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-xs font-bold uppercase tracking-wider text-slate-700">
            Establishment{" "}
            <span className="font-semibold normal-case tracking-normal text-slate-500">
              (optional)
            </span>
          </span>
          <div className="relative">
            <Building2
              aria-hidden="true"
              className="pointer-events-none absolute left-3.5 top-3.5 h-5 w-5 text-slate-400"
            />
            <select
              value={establishmentId}
              onChange={(event) => setEstablishmentId(event.target.value)}
              className="w-full cursor-pointer appearance-none rounded-2xl border border-slate-300 bg-slate-50 py-3 pl-11 pr-4 text-sm font-medium text-slate-900 transition-colors focus:border-sky-600 focus:bg-white"
            >
              <option value="">Identify from the document header</option>
              {(establishments.data ?? []).map((establishment) => (
                <option key={establishment.id} value={establishment.id}>
                  {establishment.name} · {establishment.state_code}
                </option>
              ))}
            </select>
          </div>
          <span className="mt-1.5 block text-xs leading-relaxed text-slate-500">
            Leave this alone unless you run several units with similar names. A
            document that cannot be matched confidently is held for you to attach
            rather than guessed at.
          </span>
        </label>

        <div className="rounded-2xl border border-sky-100 bg-sky-50/60 p-4 text-xs leading-relaxed text-sky-950">
          <p className="flex items-center gap-1.5 font-bold">
            <Sparkles aria-hidden="true" className="h-3.5 w-3.5" />
            Re-uploading a corrected file is expected
          </p>
          <p className="mt-1">
            Every upload is read again from scratch. Nothing is carried over from an
            earlier copy of the same file, so a correction genuinely replaces what
            was there before.
          </p>
        </div>
      </div>

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
          Drag filings here, or{" "}
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
                  : `Submit ${pendingCount} filing${pendingCount === 1 ? "" : "s"}`}
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

/** One multipart upload with progress.
 *
 *  XMLHttpRequest rather than fetch purely for `upload.onprogress`, which fetch
 *  does not expose. The bearer token is read at call time rather than captured,
 *  so a refresh that happened mid-batch is picked up.
 */
function uploadOne(
  file: File,
  establishmentId: string,
  onProgress: (percent: number) => void,
): Promise<{ document_id: string; message: string; supersedes_document_id: string | null }> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    if (establishmentId) form.append("establishment_id", establishmentId);

    const request = new XMLHttpRequest();
    request.open("POST", "/api/documents");

    const token = getAccessToken();
    if (token) request.setRequestHeader("Authorization", `Bearer ${token}`);

    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        try {
          resolve(JSON.parse(request.responseText));
        } catch {
          reject(new Error("The server accepted the file but returned an unreadable reply."));
        }
        return;
      }
      reject({ status: request.status, body: request.responseText });
    };

    request.onerror = () =>
      reject(new Error("The connection dropped while uploading."));
    request.ontimeout = () => reject(new Error("The upload timed out."));

    request.send(form);
  });
}

function describeUploadError(error: unknown): string {
  if (error && typeof error === "object" && "status" in error) {
    const { status, body } = error as { status: number; body?: string };

    if (status === 401) {
      return "Your session expired during the upload. Sign in again and retry.";
    }
    if (status === 403) {
      return "Your role is not permitted to submit filings.";
    }
    if (status === 413) {
      return "The server rejected this file as too large.";
    }

    // The upload guard returns a structured reason: extension lying about
    // content, an encrypted PDF, a page-count bomb. Those messages are written
    // for the person uploading, so they are shown verbatim.
    if (body) {
      try {
        const parsed = JSON.parse(body) as { detail?: { message?: string } | string };
        if (typeof parsed.detail === "string") return parsed.detail;
        if (parsed.detail?.message) return parsed.detail.message;
      } catch {
        /* not JSON */
      }
    }
    return `The server rejected this file (HTTP ${status}).`;
  }

  if (error instanceof Error) return error.message;
  return "This file could not be submitted.";
}
