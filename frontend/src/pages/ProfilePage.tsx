import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  Building2,
  Key,
  Lock,
  LogOut,
  Mail,
  MapPin,
  ShieldCheck,
  User,
} from "lucide-react";

import { ApiError, apiBaseUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS, STATE_CODES } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { Caution } from "@/components/ui/State";

/** Profile, and the sign-in form.
 *
 *  Combined on one screen because signing in is the only thing an anonymous
 *  visitor does here, and a separate login route would be an extra hop for no
 *  gain.
 *
 *  The jurisdiction display matters more than it looks. An empty jurisdiction list
 *  means no access at all, not access to everything — the backend fails closed on
 *  exactly this. Showing "all establishments" for an empty list would tell an
 *  officer they have national reach when in fact they will see nothing, and they
 *  would report the system as broken rather than asking to be provisioned.
 */

export function ProfilePage() {
  const { user, signIn, signOut } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      await signIn(email.trim().toLowerCase(), password);
    } catch (err) {
      if (err instanceof ApiError && err.isRateLimited) {
        setError(
          "Too many failed attempts. This account is locked temporarily as a brute-force protection.",
        );
      } else if (err instanceof ApiError && err.isAuthError) {
        setError("That email address and password do not match an account.");
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        // fetch() threw rather than returning a status, so the request never
        // completed. That is either the wrong API address or a CORS block, and
        // naming the address actually in use is the fastest way to tell which —
        // far more useful than the old message, which hardcoded "port 8000" and
        // sent people hunting for a local server that was never involved.
        setError(
          `Could not reach the API at ${apiBaseUrl()}. ` +
            "Either that address is wrong, or it is not permitting requests from " +
            `${window.location.origin}. The browser console has the exact reason.`,
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSignOut() {
    await signOut();
    void navigate("/", { replace: true });
  }

  if (!user) {
    return (
      <div className="mx-auto grid max-w-6xl items-start gap-8 lg:grid-cols-12">
        {/* Left Column: Sign In Card */}
        <div className="space-y-6 rounded-3xl border border-sky-200/90 bg-white/95 p-8 sm:p-10 shadow-[0_12px_40px_rgba(56,189,248,0.12)] backdrop-blur-2xl lg:col-span-6">
          <div className="flex items-center gap-4 border-b border-slate-100 pb-5">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-sky-200 bg-sky-100 text-sky-700 shadow-sm">
              <User className="h-7 w-7" />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-950">Sign in</h1>
              <p className="mt-1 text-sm font-semibold text-slate-600">
                Ministry of Labour &amp; Employment Portal
              </p>
            </div>
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm font-semibold text-rose-800 shadow-sm"
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSignIn} noValidate className="space-y-5">
            <label className="block">
              <span className="mb-2 block text-sm font-bold uppercase tracking-wider text-slate-800">
                Email address
              </span>
              <div className="relative">
                <Mail
                  aria-hidden="true"
                  className="pointer-events-none absolute left-4 top-4 h-5 w-5 text-slate-400"
                />
                <input
                  type="email"
                  required
                  autoComplete="username"
                  value={email}
                  placeholder="name@organisation.gov.in"
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full rounded-2xl border border-slate-300 bg-slate-50/90 py-3.5 pl-12 pr-4 text-base font-medium text-slate-900 transition-colors placeholder:text-slate-400 focus:border-sky-600 focus:bg-white focus:outline-none focus:ring-4 focus:ring-sky-100"
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-bold uppercase tracking-wider text-slate-800">
                Password
              </span>
              <div className="relative">
                <Lock
                  aria-hidden="true"
                  className="pointer-events-none absolute left-4 top-4 h-5 w-5 text-slate-400"
                />
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  placeholder="Enter your password"
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-2xl border border-slate-300 bg-slate-50/90 py-3.5 pl-12 pr-4 text-base font-medium text-slate-900 transition-colors placeholder:text-slate-400 focus:border-sky-600 focus:bg-white focus:outline-none focus:ring-4 focus:ring-sky-100"
                />
              </div>
            </label>

            <button
              type="submit"
              disabled={submitting || !email || !password}
              className="flex w-full cursor-pointer items-center justify-center gap-2.5 rounded-2xl bg-slate-950 py-4 text-base font-bold text-white shadow-xl transition-all hover:bg-slate-800 hover:scale-[1.01] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? "Signing in…" : "Sign in"}
              {!submitting && <ArrowRight className="h-5 w-5" />}
            </button>
          </form>
        </div>

        {/* Right Column: What each role can do (Enlarged & Easy to Read) */}
        <div className="space-y-4 rounded-3xl border border-sky-200/90 bg-white/95 p-8 sm:p-10 shadow-[0_12px_40px_rgba(56,189,248,0.12)] backdrop-blur-2xl lg:col-span-6">
          <div className="border-b border-slate-100 pb-4">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-bold uppercase tracking-wider text-sky-800">
              Role Permissions
            </span>
            <h2 className="mt-2 text-2xl sm:text-3xl font-black tracking-tight text-slate-950">
              What each role can do
            </h2>
            <p className="mt-1 text-sm font-medium text-slate-600">
              Authorized capabilities and access scopes across the platform
            </p>
          </div>

          <div className="space-y-4 pt-2">
            {/* Employer */}
            <div className="rounded-2xl border border-sky-100 bg-sky-50/50 p-4 sm:p-5 transition-all hover:border-sky-300 hover:bg-sky-50/80">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-sky-100 text-sky-700">
                  <Building2 className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-950">Employer</h3>
                  <span className="text-xs font-semibold text-sky-700">Establishment &amp; Self-Compliance</span>
                </div>
              </div>
              <p className="mt-2.5 text-sm sm:text-base font-medium leading-relaxed text-slate-700">
                Submits filings for their own establishments, sees their own findings, and can acknowledge or dispute them.
              </p>
            </div>

            {/* Inspector */}
            <div className="rounded-2xl border border-indigo-100 bg-indigo-50/50 p-4 sm:p-5 transition-all hover:border-indigo-300 hover:bg-indigo-50/80">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-950">Inspector</h3>
                  <span className="text-xs font-semibold text-indigo-700">Enforcement &amp; Jurisdictional Review</span>
                </div>
              </div>
              <p className="mt-2.5 text-sm sm:text-base font-medium leading-relaxed text-slate-700">
                Reads everything within an assigned jurisdiction, works the risk ranked worklist, and decides whether a finding is resolved, waived or incorrect.
              </p>
            </div>

            {/* Administrator */}
            <div className="rounded-2xl border border-purple-100 bg-purple-50/50 p-4 sm:p-5 transition-all hover:border-purple-300 hover:bg-purple-50/80">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-purple-100 text-purple-700">
                  <Key className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-950">Administrator</h3>
                  <span className="text-xs font-semibold text-purple-700">Governance &amp; System Configuration</span>
                </div>
              </div>
              <p className="mt-2.5 text-sm sm:text-base font-medium leading-relaxed text-slate-700">
                Manages rule packs and accounts, and has full read access.
              </p>
            </div>

            {/* Analyst */}
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50/50 p-4 sm:p-5 transition-all hover:border-emerald-300 hover:bg-emerald-50/80">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700">
                  <BarChart3 className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-950">Analyst</h3>
                  <span className="text-xs font-semibold text-emerald-700">Aggregate Compliance Analytics</span>
                </div>
              </div>
              <p className="mt-2.5 text-sm sm:text-base font-medium leading-relaxed text-slate-700">
                Read only aggregate view. No access to individual findings.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const jurisdictionScoped = user.role === "INSPECTOR" || user.role === "ANALYST";
  const hasScope = (user.jurisdictions ?? []).length > 0;

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header className="border-b border-sky-100/80 pb-6">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-100/80 px-4 py-1.5 text-sm font-bold text-sky-900">
          <ShieldCheck className="h-4 w-4 text-sky-600" />
          Signed in
        </div>
        <h1 className="text-4xl font-extrabold tracking-tight text-slate-900 sm:text-5xl">
          Profile
        </h1>
        <p className="mt-2 text-base font-medium text-slate-700 sm:text-lg">
          Your identity, role and the scope of what you can see.
        </p>
      </header>

      <div className="space-y-7 rounded-3xl border border-sky-200/90 bg-white/95 p-8 shadow-sm backdrop-blur-xl sm:p-10">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-start">
          <div className="flex items-center gap-5">
            <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-tr from-sky-500 to-indigo-600 text-white shadow-md">
              <User className="h-10 w-10" />
            </div>
            <div className="space-y-1">
              <h2 className="text-2xl font-extrabold text-slate-950 sm:text-3xl">
                {user.full_name}
              </h2>
              <p className="text-base font-bold text-sky-700 sm:text-lg">
                {ROLE_LABELS[user.role]}
              </p>
              <p className="text-sm font-medium text-slate-600 sm:text-base">{user.email}</p>
            </div>
          </div>

          <Badge tone="good" dot className="px-3.5 py-1.5 text-sm font-bold">
            Active session
          </Badge>
        </div>

        {/* Jurisdiction. Stated exactly, because an empty list means no access. */}
        <div className="border-t border-slate-100 pt-6">
          <div className="mb-3 flex items-center gap-2.5 text-sm font-bold uppercase tracking-wider text-slate-600 sm:text-base">
            <MapPin aria-hidden="true" className="h-4 w-4 text-slate-400" />
            Jurisdiction
          </div>

          {user.role === "ADMIN" && (
            <p className="text-base font-medium leading-relaxed text-slate-800 sm:text-lg">
              Administrator — every establishment, in every state.
            </p>
          )}

          {user.role === "EMPLOYER" && (
            <p className="text-base font-medium leading-relaxed text-slate-800 sm:text-lg">
              Scoped to the establishments registered under your organisation.
            </p>
          )}

          {jurisdictionScoped && hasScope && (
            <div className="flex flex-wrap gap-2.5 pt-1">
              {user.jurisdictions.map((code) => (
                <span
                  key={code}
                  className="rounded-xl border border-sky-200/80 bg-sky-50 px-4 py-2 text-sm font-bold text-sky-800"
                >
                  {stateName(code)}
                </span>
              ))}
            </div>
          )}

          {jurisdictionScoped && !hasScope && (
            <Caution title="No jurisdiction assigned">
              Your account has no state assigned to it, so no establishment is
              visible to you. This is deliberate: an unassigned account is given
              no access rather than full access. Ask an administrator to assign
              your jurisdiction.
            </Caution>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3.5 border-t border-slate-100 pt-6">
          {(user.role === "INSPECTOR" ||
            user.role === "ADMIN" ||
            user.role === "ANALYST") && (
            <Link
              to="/worklist"
              className="inline-flex items-center gap-2.5 rounded-2xl bg-sky-600 px-6 py-3.5 text-base font-bold text-white shadow-sm transition-colors hover:bg-sky-700"
            >
              Open worklist
              <ArrowRight className="h-5 w-5" />
            </Link>
          )}
          <Link
            to="/documents"
            className="inline-flex items-center gap-2 rounded-2xl border border-slate-300 bg-white px-6 py-3.5 text-base font-bold text-slate-800 transition-colors hover:bg-slate-50"
          >
            Documents
          </Link>
          <button
            type="button"
            onClick={() => void handleSignOut()}
            className="ml-auto inline-flex cursor-pointer items-center gap-2.5 rounded-2xl border border-rose-200 bg-white px-6 py-3.5 text-base font-bold text-rose-700 transition-colors hover:bg-rose-50"
          >
            <LogOut className="h-5 w-5" />
            Sign out
          </button>
        </div>
      </div>
      </div>
  );
}

function stateName(jurisdiction: string): string {
  const code = jurisdiction.includes("/")
    ? jurisdiction.split("/")[1]
    : jurisdiction;
  const match = STATE_CODES.find((state) => state.code === code);
  return match ? `${match.name} (${code})` : jurisdiction;
}
