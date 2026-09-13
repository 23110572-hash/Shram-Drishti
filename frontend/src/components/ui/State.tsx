import type { ComponentType, ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import { ApiError, apiBaseUrl } from "@/lib/api";

/** Loading, empty and error states.
 *
 *  Kept in one file because they are the same component with different content,
 *  and because consistency matters more here than anywhere else in the UI: an
 *  officer needs to tell at a glance whether a screen is empty because there is
 *  nothing to show or because something broke.
 */

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 py-16 text-sm font-semibold text-slate-500"
    >
      <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin text-sky-600" />
      {label}&hellip;
    </div>
  );
}

/** Skeleton rows for a table that is still loading.
 *
 *  Used instead of a spinner where the shape of the result is already known —
 *  it stops the layout jumping when the data lands.
 */
export function SkeletonRows({ rows = 5, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div aria-hidden="true" className="divide-y divide-slate-100">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex items-center gap-4 px-6 py-4">
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <div
              key={columnIndex}
              className="h-3.5 animate-pulse rounded-full bg-slate-200/80"
              style={{ width: `${100 / columns - (columnIndex === 0 ? 4 : 8)}%` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

interface EmptyStateProps {
  icon: ComponentType<{ className?: string }>;
  title: string;
  description: string;
  action?: ReactNode;
  tone?: "neutral" | "good";
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  tone = "neutral",
}: EmptyStateProps) {
  const ring =
    tone === "good"
      ? "bg-emerald-50 border-emerald-200 text-emerald-700"
      : "bg-sky-50 border-sky-200 text-sky-700";

  return (
    <div className="px-8 py-16 text-center">
      <div className="mx-auto max-w-md space-y-4">
        <div
          className={`mx-auto flex h-16 w-16 items-center justify-center rounded-full border ${ring}`}
        >
          <Icon className="h-8 w-8" />
        </div>
        <h3 className="text-xl font-bold text-slate-900">{title}</h3>
        <p className="text-sm leading-relaxed text-slate-600">{description}</p>
        {action && <div className="pt-2">{action}</div>}
      </div>
    </div>
  );
}

/** Error state that distinguishes the failure modes an officer can act on.
 *
 *  A 401 means the session lapsed; a network failure means the backend is not
 *  running. Collapsing both into "something went wrong" sends people to the
 *  wrong fix, which on a local deployment is the difference between signing in
 *  again and starting the API.
 */
export function ErrorState({
  error,
  onRetry,
  context,
}: {
  error: unknown;
  onRetry?: () => void;
  context?: string;
}) {
  const { title, detail } = describe(error, context);

  return (
    <div role="alert" className="px-8 py-14 text-center">
      <div className="mx-auto max-w-lg space-y-4">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-rose-200 bg-rose-50 text-rose-700">
          <AlertTriangle className="h-7 w-7" />
        </div>
        <h3 className="text-lg font-bold text-slate-900">{title}</h3>
        <p className="text-sm leading-relaxed text-slate-600">{detail}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="cursor-pointer rounded-full border border-slate-300 bg-white px-6 py-2.5 text-sm font-bold text-slate-800 transition-colors hover:bg-slate-50"
          >
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

function describe(
  error: unknown,
  context?: string,
): { title: string; detail: string } {
  const subject = context ?? "this information";

  if (error instanceof ApiError) {
    if (error.isAuthError) {
      return {
        title: "Your session has expired",
        detail: "Sign in again from the Profile page to continue.",
      };
    }
    if (error.isForbidden) {
      return {
        title: "Not available to your role",
        detail: `Your account does not have permission to view ${subject}.`,
      };
    }
    if (error.isNotFound) {
      return {
        title: "Not found",
        detail: `${subject.charAt(0).toUpperCase()}${subject.slice(1)} could not be found, or it is outside your jurisdiction.`,
      };
    }
    if (error.isRateLimited) {
      return {
        title: "Too many requests",
        detail: "Wait a moment and try again.",
      };
    }
    return {
      title: `Could not load ${subject}`,
      detail: error.message,
    };
  }

  // Not an ApiError, so the request never completed: wrong address, or a CORS
  // block. Naming the address this build is actually using distinguishes the two
  // immediately — and catches the case where the API URL never reached the build.
  return {
    title: "Cannot reach the service",
    detail:
      `No response from the API at ${apiBaseUrl()}. Either that address is ` +
      `wrong, it is not permitting requests from ${window.location.origin}, or ` +
      "the service is still starting up.",
  };
}

/** A caution banner. Used for the two warnings that must never be styled as
 *  ordinary text: thin evidence behind a score, and a rule whose figure is still
 *  waiting on a government notification. */
export function Caution({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div
      role="note"
      className="rounded-2xl border border-amber-300 bg-amber-50/90 p-4 text-sm text-amber-950"
    >
      <p className="flex items-center gap-2 font-bold">
        <AlertTriangle aria-hidden="true" className="h-4 w-4" />
        {title}
      </p>
      <div className="mt-1 leading-relaxed">{children}</div>
    </div>
  );
}
