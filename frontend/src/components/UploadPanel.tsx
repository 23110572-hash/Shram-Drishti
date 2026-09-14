import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { useAuth } from "@/lib/auth";
import { getAccessToken } from "@/lib/tokens";
import { bytes } from "@/lib/format";
import type {
  EstablishmentDetail,
  EstablishmentInput,
  EstablishmentSummary,
  UploadResponse,
} from "@/lib/types";

/** Upload many documents for one explicitly selected establishment. */

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,.txt,.csv,.ecr";
const MAX_BYTES = 20 * 1024 * 1024;
const MAX_VISIBLE_ESTABLISHMENTS = 8;

const SUPPORTED_STATES = [
  ["AP", "Andhra Pradesh"],
  ["AR", "Arunachal Pradesh"],
  ["AS", "Assam"],
  ["BR", "Bihar"],
  ["CH", "Chandigarh"],
  ["CG", "Chhattisgarh"],
  ["DL", "Delhi"],
  ["GA", "Goa"],
  ["GJ", "Gujarat"],
  ["HR", "Haryana"],
  ["HP", "Himachal Pradesh"],
  ["JK", "Jammu & Kashmir"],
  ["JH", "Jharkhand"],
  ["KA", "Karnataka"],
  ["KL", "Kerala"],
  ["MP", "Madhya Pradesh"],
  ["MH", "Maharashtra"],
  ["MN", "Manipur"],
  ["ML", "Meghalaya"],
  ["MZ", "Mizoram"],
  ["NL", "Nagaland"],
  ["OD", "Odisha"],
  ["PY", "Puducherry"],
  ["PB", "Punjab"],
  ["RJ", "Rajasthan"],
  ["SK", "Sikkim"],
  ["TN", "Tamil Nadu"],
  ["TG", "Telangana"],
  ["TR", "Tripura"],
  ["UP", "Uttar Pradesh"],
  ["UK", "Uttarakhand"],
  ["WB", "West Bengal"],
] as const;

const EMPTY_ESTABLISHMENT_PROFILE = {
  worker_count: 0,
  worker_count_peak_12m: 0,
  women_worker_count: 0,
  contract_worker_count: 0,
  interstate_migrant_count: 0,
  is_factory: false,
  is_mine: false,
  is_plantation: false,
  is_construction: false,
  has_hazardous_process: false,
  engages_contract_labour: false,
  has_night_shift: false,
} satisfies Omit<EstablishmentInput, "name" | "state_code">;

type ItemStatus = "queued" | "uploading" | "done" | "error";

interface QueueItem {
  key: string;
  file: File;
  status: ItemStatus;
  progress: number;
  message?: string | undefined;
  documentId?: string | undefined;
}

export interface EstablishmentUploadBatch {
  establishmentId: string;
  establishmentName: string;
  documentIds: string[];
}

interface UploadPanelProps {
  onUploaded?: (batch: EstablishmentUploadBatch) => void;
}

export function UploadPanel({ onUploaded }: UploadPanelProps) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);

  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [filter, setFilter] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [newStateCode, setNewStateCode] = useState("");
  const [selectedEstablishment, setSelectedEstablishment] =
    useState<EstablishmentSummary | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canRegister = user?.role === "EMPLOYER" || user?.role === "ADMIN";

  const searchTerm = filter.trim();
  const establishments = useQuery({
    queryKey: ["establishments", "upload-search", searchTerm],
    queryFn: ({ signal }) =>
      api.get<EstablishmentSummary[]>(
        `/establishments?search=${encodeURIComponent(searchTerm)}&limit=${MAX_VISIBLE_ESTABLISHMENTS}`,
        signal,
      ),
    enabled:
      pickerOpen &&
      searchTerm.length >= 2 &&
      selectedEstablishment?.name !== searchTerm,
    retry: false,
    staleTime: 30_000,
  });

  const matches = establishments.data ?? [];

  const registerEstablishment = useMutation({
    mutationFn: ({ name, stateCode }: { name: string; stateCode: string }) =>
      api.post<EstablishmentDetail>("/establishments", {
        ...EMPTY_ESTABLISHMENT_PROFILE,
        name,
        state_code: stateCode,
      } satisfies EstablishmentInput),
    onSuccess: (created) => {
      setSelectedEstablishment(created);
      setFilter(created.name);
      setSelectionError(null);
      setRegistering(false);
      setNewStateCode("");
      setPickerOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["establishments"] });
    },
    onError: (error) => {
      setSelectionError(
        error instanceof Error
          ? error.message
          : "This establishment could not be registered.",
      );
    },
  });

  function startRegistration() {
    setSelectionError(null);
    setNewStateCode("");
    setRegistering(true);
    setPickerOpen(false);
  }

  function createAndSelect() {
    const name = filter.trim();
    if (name.length < 2) {
      setSelectionError("Enter at least two characters for the establishment name.");
      return;
    }
    if (!newStateCode) {
      setSelectionError("Choose the State or Union Territory for this establishment.");
      return;
    }
    registerEstablishment.mutate({ name, stateCode: newStateCode });
  }

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
            ? `${bytes(file.size)} exceeds the 20 MB limit`
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

    let target = selectedEstablishment;
    if (!target && searchTerm) {
      const exactMatches = matches.filter(
        (item) => item.name.trim().toLocaleLowerCase() === searchTerm.toLocaleLowerCase(),
      );
      if (exactMatches.length === 1) {
        target = exactMatches[0] ?? null;
        if (target) {
          setSelectedEstablishment(target);
          setFilter(target.name);
          setPickerOpen(false);
        }
      }
    }

    if (!target) {
      setSelectionError(
        canRegister
          ? "Select a matching establishment, or register this new name first."
          : "Select an existing establishment before uploading.",
      );
      setPickerOpen(!registering);
      return;
    }

    setSelectionError(null);
    setBusy(true);
    const uploaded: string[] = [];

    // Submit sequentially so one request body at a time reaches the free service.
    for (const item of pending) {
      patch(item.key, { status: "uploading", progress: 0, message: undefined });

      try {
        const response = await uploadOne(item.file, target.id, (progress) =>
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
      onUploaded?.({
        establishmentId: target.id,
        establishmentName: target.name,
        documentIds: uploaded,
      });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      setQueue((current) =>
        current.filter((item) => !item.documentId || !uploaded.includes(item.documentId)),
      );
    }
  }

  const pendingCount = queue.filter((item) => item.status === "queued").length;
  const doneCount = queue.filter((item) => item.status === "done").length;
  const failedCount = queue.filter((item) => item.status === "error").length;

  return (
    <section className="space-y-5 rounded-3xl border border-sky-200/90 bg-white/95 p-6 shadow-[0_10px_35px_rgba(56,189,248,0.10)] backdrop-blur-xl sm:p-8">
      <header>
        <h2 className="flex items-center gap-2.5 text-xl font-bold text-slate-900">
          <UploadCloud className="h-6 w-6 text-sky-600" />
          Submit documents
        </h2>
      </header>

      <div className="relative rounded-2xl border border-slate-200 bg-slate-50/60 p-5">
        <label htmlFor="establishment-search" className="block text-sm font-bold text-slate-900">
          Establishment name
        </label>
        <div className="relative mt-2">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3.5 top-3 h-4.5 w-4.5 text-slate-400"
          />
          <input
            id="establishment-search"
            type="search"
            role="combobox"
            aria-expanded={pickerOpen && matches.length > 0}
            aria-controls="establishment-options"
            aria-autocomplete="list"
            value={filter}
            onFocus={() => setPickerOpen(true)}
            onBlur={() => window.setTimeout(() => setPickerOpen(false), 120)}
            onChange={(event) => {
              setFilter(event.target.value);
              setSelectedEstablishment(null);
              setSelectionError(null);
              setRegistering(false);
              setNewStateCode("");
              setPickerOpen(true);
            }}
            placeholder="Start typing the establishment name"
            autoComplete="off"
            disabled={busy || registerEstablishment.isPending}
            className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-11 text-sm text-slate-900 transition-colors focus:border-sky-600 disabled:opacity-60"
          />
          {selectedEstablishment && (
            <CheckCircle2
              aria-label="Establishment selected"
              className="absolute right-3.5 top-2.5 h-5 w-5 text-emerald-600"
            />
          )}
        </div>

        {selectionError && (
          <p className="mt-2 text-xs font-semibold text-rose-700">{selectionError}</p>
        )}
        {establishments.isFetching && (
          <p className="mt-2 text-xs text-slate-500">Searching…</p>
        )}
        {establishments.isError && pickerOpen && (
          <p className="mt-2 text-xs font-semibold text-rose-700">
            Establishments could not be loaded. Please retry.
          </p>
        )}
        {establishments.isSuccess &&
          pickerOpen &&
          searchTerm.length >= 2 &&
          matches.length === 0 && (
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5">
              <p className="text-xs text-slate-600">No establishment matches this name.</p>
              {canRegister && (
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={startRegistration}
                  className="cursor-pointer rounded-full bg-sky-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-sky-800"
                >
                  Register new
                </button>
              )}
            </div>
          )}

        {pickerOpen && matches.length > 0 && (
          <ul
            id="establishment-options"
            role="listbox"
            className="mt-2 max-h-56 space-y-1 overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg"
          >
            {matches.map((establishment) => (
              <li key={establishment.id} role="option" aria-selected={false}>
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    setSelectedEstablishment(establishment);
                    setFilter(establishment.name);
                    setSelectionError(null);
                    setPickerOpen(false);
                  }}
                  className="flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-semibold text-slate-900 hover:bg-sky-50"
                >
                  <Building2 aria-hidden="true" className="h-4 w-4 shrink-0 text-sky-700" />
                  <span className="min-w-0">
                    <span className="block truncate">{establishment.name}</span>
                    <span className="block truncate text-xs font-medium text-slate-500">
                      {establishment.state_code}
                      {establishment.district && ` · ${establishment.district}`}
                      {establishment.lin && ` · LIN ${establishment.lin}`}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {registering && (
          <div className="mt-3 rounded-xl border border-sky-200 bg-sky-50/70 p-4">
            <p className="text-sm font-bold text-slate-900">
              Register “{searchTerm}”
            </p>
            <p className="mt-1 text-xs text-slate-600">
              Choose its State or Union Territory so the correct jurisdiction is used.
            </p>
            <label className="mt-3 block text-xs font-bold text-slate-700">
              State or Union Territory
              <select
                value={newStateCode}
                onChange={(event) => {
                  setNewStateCode(event.target.value);
                  setSelectionError(null);
                }}
                disabled={registerEstablishment.isPending}
                className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-sky-600 disabled:opacity-60"
              >
                <option value="">Choose State / UT</option>
                {SUPPORTED_STATES.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <div className="mt-3 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setRegistering(false);
                  setNewStateCode("");
                  setSelectionError(null);
                  setPickerOpen(true);
                }}
                disabled={registerEstablishment.isPending}
                className="cursor-pointer rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={createAndSelect}
                disabled={registerEstablishment.isPending}
                className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white hover:bg-slate-800 disabled:cursor-wait disabled:opacity-60"
              >
                {registerEstablishment.isPending && (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                )}
                {registerEstablishment.isPending ? "Registering…" : "Register and select"}
              </button>
            </div>
          </div>
        )}
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
          Drag your documents here, or{" "}
          <label
            htmlFor="filing-upload-input"
            className="cursor-pointer text-sky-700 underline decoration-sky-300 decoration-2 underline-offset-2 hover:text-sky-800"
          >
            browse your files
          </label>
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
                disabled={busy || registerEstablishment.isPending || pendingCount === 0}
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
    form.append("establishment_id", establishmentId);

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
