import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  Key,
  Lock,
  LogOut,
  Mail,
  MapPin,
  ShieldAlert,
  ShieldCheck,
  User,
} from "lucide-react";

import { ApiError } from "@/lib/api";
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
        setError(
          "The service did not respond. Confirm the backend is running on port 8000.",
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
      <div className="mx-auto grid max-w-5xl items-start gap-8 lg:grid-cols-12">
        <div className="space-y-6 rounded-3xl border border-sky-200/90 bg-white/95 p-8 shadow-[0_12px_40px_rgba(56,189,248,0.12)] backdrop-blur-2xl lg:col-span-7">
          <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-sky-200 bg-sky-100 text-sky-700">
              <User className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-xl font-extrabold text-slate-900">Sign in</h1>
              <p className="text-xs font-medium text-slate-500">
                For employers, Inspector-cum-Facilitators and administrators
              </p>
            </div>
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm font-medium text-rose-800"
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSignIn} noValidate className="space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-xs font-bold uppercase tracking-wider text-slate-700">
                Email address
              </span>
              <div className="relative">
                <Mail
                  aria-hidden="true"
                  className="pointer-events-none absolute left-3.5 top-3.5 h-5 w-5 text-slate-400"
                />
                <input
                  type="email"
                  required
                  autoComplete="username"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full rounded-2xl border border-slate-300 bg-slate-50 py-3 pl-11 pr-4 text-sm text-slate-900 transition-colors placeholder:text-slate-400 focus:border-sky-600 focus:bg-white focus:outline-none"
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-bold uppercase tracking-wider text-slate-700">
                Password
              </span>
              <div className="relative">
                <Lock
                  aria-hidden="true"
                  className="pointer-events-none absolute left-3.5 top-3.5 h-5 w-5 text-slate-400"
                />
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-2xl border border-slate-300 bg-slate-50 py-3 pl-11 pr-4 text-sm text-slate-900 transition-colors placeholder:text-slate-400 focus:border-sky-600 focus:bg-white focus:outline-none"
                />
              </div>
            </label>

            <button
              type="submit"
              disabled={submitting || !email || !password}
              className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-2xl bg-slate-900 py-3.5 text-sm font-bold text-white shadow-md transition-all hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? "Signing in…" : "Sign in"}
              {!submitting && <ArrowRight className="h-4 w-4" />}
            </button>
          </form>

          <p className="border-t border-slate-100 pt-4 text-xs leading-relaxed text-slate-500">
            Accounts are created by an administrator using the{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono">
              create-admin
            </code>{" "}
            command. Repeated failed attempts lock an account temporarily.
          </p>
        </div>

        <div className="space-y-6 lg:col-span-5">
          <div className="space-y-3 rounded-3xl border border-sky-100 bg-white/90 p-6 shadow-sm backdrop-blur-xl">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-900">
              What each role can do
            </h2>
            <dl className="space-y-3 text-xs leading-relaxed text-slate-700">
              <div>
                <dt className="font-bold text-slate-900">Employer</dt>
                <dd>
                  Submits filings for their own establishments, sees their own
                  findings, and can acknowledge or dispute them.
                </dd>
              </div>
              <div>
                <dt className="font-bold text-slate-900">
                  Inspector-cum-Facilitator
                </dt>
                <dd>
                  Reads everything within an assigned jurisdiction, works the
                  risk-ranked worklist, and decides whether a finding is resolved,
                  waived or incorrect.
                </dd>
              </div>
              <div>
                <dt className="font-bold text-slate-900">Administrator</dt>
                <dd>Manages rule packs and accounts, and has full read access.</dd>
              </div>
              <div>
                <dt className="font-bold text-slate-900">Analyst</dt>
                <dd>Read-only aggregate view. No access to individual findings.</dd>
              </div>
            </dl>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white/80 p-5 text-xs leading-relaxed text-slate-600">
            <p className="mb-1 font-bold text-slate-900">Session handling</p>
            <p>
              The access token is held in memory only and the refresh token rotates
              on every use. Reusing an old refresh token is treated as theft and
              revokes every session on the account.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const jurisdictionScoped = user.role === "INSPECTOR" || user.role === "ANALYST";
  const hasScope = (user.jurisdictions ?? []).length > 0;

  return (
    <div className="space-y-8">
      <header className="border-b border-sky-100/80 pb-6">
        <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-100/70 px-3 py-1 text-xs font-semibold text-sky-800">
          <ShieldCheck className="h-3.5 w-3.5 text-sky-600" />
          Signed in
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">
          Profile
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Your identity, role and the scope of what you can see.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 rounded-2xl border border-sky-100 bg-white/95 p-6 shadow-sm backdrop-blur-xl sm:p-8 lg:col-span-2">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
            <div className="flex items-center gap-4">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-sky-500 to-indigo-600 text-white shadow-md">
                <User className="h-8 w-8" />
              </div>
              <div>
                <h2 className="text-2xl font-bold text-slate-900">
                  {user.full_name}
                </h2>
                <p className="text-sm font-semibold text-sky-700">
                  {ROLE_LABELS[user.role]}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">{user.email}</p>
              </div>
            </div>

            <Badge tone="good" dot>
              Active session
            </Badge>
          </div>

          <div className="grid grid-cols-1 gap-4 border-t border-slate-100 pt-4 sm:grid-cols-2">
            <Detail icon={Key} label="Account identifier" value={user.id} mono />
            <Detail
              icon={Building2}
              label="Organisation"
              value={user.organisation_id}
              mono
            />
          </div>

          {/* Jurisdiction. Stated exactly, because an empty list means no access. */}
          <div className="border-t border-slate-100 pt-4">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              <MapPin aria-hidden="true" className="h-3.5 w-3.5 text-slate-400" />
              Jurisdiction
            </div>

            {user.role === "ADMIN" && (
              <p className="text-sm text-slate-700">
                Administrator — every establishment, in every state.
              </p>
            )}

            {user.role === "EMPLOYER" && (
              <p className="text-sm text-slate-700">
                Scoped to the establishments registered under your organisation.
              </p>
            )}

            {jurisdictionScoped && hasScope && (
              <div className="flex flex-wrap gap-2">
                {user.jurisdictions.map((code) => (
                  <span
                    key={code}
                    className="rounded-lg border border-sky-200/80 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-800"
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

          <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
            {(user.role === "INSPECTOR" ||
              user.role === "ADMIN" ||
              user.role === "ANALYST") && (
              <Link
                to="/worklist"
                className="inline-flex items-center gap-2 rounded-xl bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-sky-700"
              >
                Open worklist
                <ArrowRight className="h-4 w-4" />
              </Link>
            )}
            <Link
              to="/documents"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 transition-colors hover:bg-slate-50"
            >
              Documents
            </Link>
            <button
              type="button"
              onClick={() => void handleSignOut()}
              className="ml-auto inline-flex cursor-pointer items-center gap-2 rounded-xl border border-rose-200 bg-white px-5 py-2.5 text-sm font-semibold text-rose-700 transition-colors hover:bg-rose-50"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>

        <div className="space-y-6">
          <div className="space-y-3 rounded-2xl border border-sky-100 bg-white/95 p-6 shadow-sm backdrop-blur-xl">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900">
              What is recorded
            </h3>
            <p className="text-xs leading-relaxed text-slate-600">
              Reading a document or a finding means reading a worker's pay record,
              so each access is written to a hash-chained audit log with its purpose
              — a requirement of purpose limitation, not an optional extra.
            </p>
            <ul className="space-y-1.5 text-xs text-slate-700">
              <li className="flex items-start gap-2">
                <CheckCircle2
                  aria-hidden="true"
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-600"
                />
                Document and finding access, with purpose
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2
                  aria-hidden="true"
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-600"
                />
                Every status change, with the reason given
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2
                  aria-hidden="true"
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-600"
                />
                Notices dispatched, so a cure period is provable
              </li>
            </ul>
          </div>

          {(user.role === "INSPECTOR" || user.role === "ADMIN") && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-5 text-xs leading-relaxed text-amber-950">
              <p className="mb-1 flex items-center gap-1.5 font-bold">
                <ShieldAlert aria-hidden="true" className="h-4 w-4" />
                Before you enforce
              </p>
              <p>
                Findings flagged as having an unverified threshold rest on a value
                read from a secondary source rather than the Act itself. Check the
                notified Rules before acting on one.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Detail({
  icon: Icon,
  label,
  value,
  mono = false,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50/80 p-4">
      <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
        <Icon className="h-3.5 w-3.5 text-slate-400" />
        {label}
      </div>
      <p
        className={[
          "break-all font-bold text-slate-800",
          mono ? "font-mono text-sm" : "text-sm",
        ].join(" ")}
      >
        {value}
      </p>
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
