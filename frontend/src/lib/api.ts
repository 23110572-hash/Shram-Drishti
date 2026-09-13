/** HTTP client with automatic access-token refresh.
 *
 *  The important behaviour here is the single-flight refresh. Without it, a
 *  dashboard that fires six requests on mount will, on an expired token, send
 *  six concurrent refresh calls. Because refresh tokens are single-use and
 *  rotating, the first would succeed and the rest would look like token reuse —
 *  which the backend correctly treats as theft and responds to by revoking every
 *  session. The user would be logged out for loading a page.
 *
 *  So: one refresh at a time, and everyone else waits on the same promise.
 */

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "@/lib/tokens";
import type { TokenResponse } from "@/lib/types";

/** Where the API lives.
 *
 *  Defaults to `/api`, which Vite proxies to the local backend in development.
 *  That keeps the browser same-origin, so there is no CORS configuration to get
 *  wrong locally.
 *
 *  When the frontend and backend are deployed to different hosts — Vercel and
 *  Render, for instance — set VITE_API_BASE_URL to the backend's full URL and
 *  add the frontend's origin to CORS_ALLOWED_ORIGINS on the backend.
 */
const BASE_URL = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api"
).replace(/\/+$/, "");

/** The API address this build is using.
 *
 *  Exposed because the commonest deployment mistake is invisible otherwise. Vite
 *  inlines VITE_* variables at build time, so setting VITE_API_BASE_URL in a
 *  hosting dashboard without redeploying leaves the bundle still pointing at the
 *  `/api` fallback — and every request then fails in a way that looks like the
 *  backend is down. Showing the address in the error tells you immediately whether
 *  the variable actually reached the build.
 */
export function apiBaseUrl(): string {
  return BASE_URL || "/api";
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }
}

/** In-flight refresh, shared by every caller that hits a 401. */
let refreshInFlight: Promise<boolean> | null = null;

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail !== undefined) return JSON.stringify(body.detail);
  } catch {
    /* non-JSON error body */
  }
  return response.statusText || `request failed with ${response.status}`;
}

async function performRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  const response = await fetch(`${BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    // Refresh failed: the token is expired, revoked, or was reused. Either way
    // the session is over — clear it so the router redirects to login rather
    // than looping on retries.
    clearTokens();
    return false;
  }

  const tokens = (await response.json()) as TokenResponse;
  setTokens(tokens.access_token, tokens.refresh_token);
  return true;
}

function refreshOnce(): Promise<boolean> {
  refreshInFlight ??= performRefresh().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  /** Skip the Authorization header. Used by login and refresh themselves. */
  anonymous?: boolean;
  signal?: AbortSignal;
}

async function send(
  path: string,
  options: RequestOptions,
  isRetry = false,
): Promise<Response> {
  const headers: Record<string, string> = {};

  // FormData sets its own Content-Type with the multipart boundary; setting it
  // manually breaks the upload.
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  if (!options.anonymous) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const init: RequestInit = {
    method: options.method ?? "GET",
    headers,
  };
  if (options.signal) init.signal = options.signal;

  if (options.body instanceof FormData) {
    // Narrowed on the value itself rather than a boolean flag, so TypeScript
    // can see that body is a valid BodyInit here.
    init.body = options.body;
  } else if (options.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }

  const response = await fetch(`${BASE_URL}${path}`, init);

  // One retry only. A second 401 after a successful refresh means the request
  // is genuinely unauthorised, not stale — retrying again would loop.
  if (response.status === 401 && !options.anonymous && !isRetry) {
    if (await refreshOnce()) {
      return send(path, options, true);
    }
  }

  return response;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await send(path, options);

  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorMessage(response));
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, signal ? { signal } : {}),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, body === undefined ? { method: "POST" } : { method: "POST", body }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, body === undefined ? { method: "PATCH" } : { method: "PATCH", body }),

  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),

  /** Anonymous POST, for login and refresh. */
  postAnonymous: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body, anonymous: true }),

  /** Multipart upload. FormData sets its own Content-Type with the boundary, so
   *  the client must not set one — see `send`. */
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),

  /** Fetch binary content as an object URL, for page images.
   *
   *  Page images are served through the authenticated API rather than as static
   *  files, because a scanned wage register is a worker's pay record and must
   *  stay behind the same establishment scoping as everything else. That means
   *  an `<img src>` cannot carry the bearer token, so the bytes are fetched here
   *  and wrapped in a blob URL.
   *
   *  Callers must revoke the returned URL when the image is no longer displayed,
   *  or the blob is retained for the lifetime of the document.
   */
  objectUrl: async (path: string, signal?: AbortSignal): Promise<string> => {
    const response = await send(path, signal ? { signal } : {});
    if (!response.ok) {
      throw new ApiError(response.status, await extractErrorMessage(response));
    }
    return URL.createObjectURL(await response.blob());
  },
};

/** Restore a session on page load by exchanging the stored refresh token.
 *  Returns false when there is nothing to restore. */
export async function restoreSession(): Promise<boolean> {
  if (!getRefreshToken()) return false;
  return refreshOnce();
}
