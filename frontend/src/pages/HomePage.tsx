import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  Building2,
  ClipboardList,
  Database,
  Eye,
  FileSearch,
  Scale,
  Server,
  Shield,
  Upload,
} from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { count, paise } from "@/lib/format";
import {
  CODE_LABELS,
  type FindingCounts,
  type HealthResponse,
  type LabourCode,
  type ReadinessResponse,
  type RulesOverview,
} from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

/** Landing page.
 *
 *  Everything on this page is read from the running service. The counts are real
 *  counts, the rule totals come from the loaded packs, and the status indicators
 *  reflect actual connectivity. Nothing here is illustrative.
 *
 *  For a signed-in user it becomes a summary of their own position; for a visitor
 *  it explains what the system does and what it deliberately does not do.
 */

export function HomePage() {
  const { user } = useAuth();

  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthResponse>("/healthz"),
    refetchInterval: 60_000,
  });

  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: () => api.get<ReadinessResponse>("/readyz"),
    refetchInterval: 60_000,
    retry: false,
  });

  const rules = useQuery({
    queryKey: ["rules-overview"],
    queryFn: () => api.get<RulesOverview>("/rules"),
    enabled: Boolean(user),
    retry: false,
  });

  const findings = useQuery({
    queryKey: ["finding-counts", null],
    queryFn: () => api.get<FindingCounts>("/findings/counts?open_only=true"),
    enabled: Boolean(user),
    retry: false,
  });

  const codes = Object.keys(CODE_LABELS) as LabourCode[];

  return (
    <div className="space-y-20 sm:space-y-24">
      {/* Hero */}
      <section className="mx-auto max-w-5xl space-y-8 pt-6 text-center">
        <div className="inline-flex items-center gap-2.5 rounded-full border border-slate-300/80 bg-white/80 px-5 py-2 text-sm font-bold text-slate-800 shadow-sm backdrop-blur-md">
          <Shield className="h-4 w-4 text-sky-700" />
          Ministry of Labour &amp; Employment · National Career Service
        </div>

        <h1 className="text-4xl font-extrabold leading-[1.1] tracking-tight text-slate-950 sm:text-6xl lg:text-7xl">
          Labour Code inspection and{" "}
          <span className="bg-gradient-to-r from-sky-700 via-blue-700 to-indigo-700 bg-clip-text text-transparent">
            compliance assessment
          </span>
        </h1>

        <p className="mx-auto max-w-3xl text-lg font-medium leading-relaxed text-slate-700 sm:text-2xl">
          Reads an employer's registers, returns and challans, checks them against
          the four Labour Codes, and shows an inspector exactly which cell on which
          page supports every finding.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
          <Link
            to="/documents"
            className="flex items-center gap-2 rounded-full bg-slate-900 px-8 py-3.5 text-base font-bold text-white shadow-lg transition-all hover:bg-slate-800"
          >
            <Upload className="h-5 w-5" />
            Submit filings
          </Link>
          <Link
            to="/rules"
            className="flex items-center gap-2 rounded-full border border-slate-300 bg-white/90 px-7 py-3.5 text-base font-bold text-slate-900 shadow-sm transition-all hover:bg-white"
          >
            <BookOpen className="h-5 w-5 text-amber-700" />
            Read the rules
          </Link>
          {!user && (
            <Link
              to="/profile"
              className="rounded-full border border-slate-300/80 bg-slate-200/60 px-6 py-3.5 text-base font-bold text-slate-800 transition-all hover:bg-slate-200"
            >
              Sign in
            </Link>
          )}
        </div>
      </section>

      {/* Signed-in summary, or service status for a visitor. */}
      {user ? (
        <section className="mx-auto grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Link
            to="/findings"
            className="rounded-3xl border border-slate-200/90 bg-white/90 p-6 shadow-sm backdrop-blur-md transition-colors hover:border-sky-300"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Open breaches
              </span>
              <FileSearch className="h-4 w-4 text-rose-700" />
            </div>
            <p className="mt-1 text-3xl font-extrabold text-slate-900">
              {findings.data ? count(findings.data.scored_total) : "—"}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              Cited against a statutory provision
            </p>
          </Link>

          <Link
            to="/findings"
            className="rounded-3xl border border-slate-200/90 bg-white/90 p-6 shadow-sm backdrop-blur-md transition-colors hover:border-sky-300"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Amount at stake
              </span>
              <Scale className="h-4 w-4 text-amber-700" />
            </div>
            <p className="mt-1 text-3xl font-extrabold text-slate-900">
              {findings.data ? paise(findings.data.total_exposure_paise) : "—"}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              Where it could be quantified
            </p>
          </Link>

          <Link
            to="/establishments"
            className="rounded-3xl border border-slate-200/90 bg-white/90 p-6 shadow-sm backdrop-blur-md transition-colors hover:border-sky-300"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Advisory signals
              </span>
              <Eye className="h-4 w-4 text-sky-700" />
            </div>
            <p className="mt-1 text-3xl font-extrabold text-slate-900">
              {findings.data ? count(findings.data.advisory_total) : "—"}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              Never scored, never enforced
            </p>
          </Link>

          <Link
            to="/rules"
            className="rounded-3xl border border-slate-200/90 bg-white/90 p-6 shadow-sm backdrop-blur-md transition-colors hover:border-sky-300"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Rules loaded
              </span>
              <BookOpen className="h-4 w-4 text-indigo-700" />
            </div>
            <p className="mt-1 text-3xl font-extrabold text-slate-900">
              {rules.data ? count(rules.data.total_rules) : "—"}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              {rules.data
                ? `${rules.data.sound_rules} applicable as they stand`
                : "across four Codes"}
            </p>
          </Link>
        </section>
      ) : (
        <section className="mx-auto grid max-w-4xl gap-4 sm:grid-cols-2">
          <div className="space-y-2 rounded-3xl border border-slate-200/90 bg-white/80 p-6 shadow-sm backdrop-blur-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Service
              </span>
              <Server className="h-4 w-4 text-sky-700" />
            </div>
            <div className="flex items-center gap-2.5">
              <span
                className={
                  health.isSuccess
                    ? "h-3 w-3 rounded-full bg-emerald-600"
                    : "h-3 w-3 animate-pulse rounded-full bg-amber-600"
                }
              />
              <span className="text-base font-extrabold text-slate-900">
                {health.data
                  ? health.data.app
                  : health.isError
                    ? "Not responding"
                    : "Connecting…"}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              {health.data
                ? `Version ${health.data.version} · ${health.data.environment}`
                : "The API did not answer on port 8000."}
            </p>
          </div>

          <div className="space-y-2 rounded-3xl border border-slate-200/90 bg-white/80 p-6 shadow-sm backdrop-blur-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Database
              </span>
              <Database className="h-4 w-4 text-indigo-700" />
            </div>
            <div className="flex items-center gap-2.5">
              <span
                className={
                  readiness.data?.status === "ready"
                    ? "h-3 w-3 rounded-full bg-emerald-600"
                    : "h-3 w-3 rounded-full bg-amber-600"
                }
              />
              <span className="text-base font-extrabold text-slate-900">
                {readiness.data?.status === "ready" ? "Reachable" : "Not ready"}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              {readiness.data
                ? Object.entries(readiness.data.checks)
                    .map(([name, ok]) => `${name}: ${ok ? "ok" : "failing"}`)
                    .join(" · ")
                : "Checking connectivity."}
            </p>
          </div>
        </section>
      )}

      {/* What it does, honestly */}
      <section className="mx-auto max-w-6xl space-y-8">
        <div className="mx-auto max-w-3xl space-y-3 text-center">
          <h2 className="text-3xl font-extrabold text-slate-900 sm:text-4xl">
            How a filing becomes a finding
          </h2>
          <p className="text-base text-slate-600 sm:text-lg">
            Four stages. The division of labour between the model and the rules is
            deliberate and is the reason a finding can be defended.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Stage
            number="01"
            title="Read the page"
            accent="text-sky-700"
            body="A PDF with a text layer is read directly and exactly. Anything else is rasterised, sent to OCR, and given to a vision model together with the page image so the two can be cross-checked."
          />
          <Stage
            number="02"
            title="Prove every figure"
            accent="text-indigo-700"
            body="Each number is searched for among the OCR words on the page it was attributed to. A figure that cannot be found there, and was not declared as a correction, is held for a human rather than used."
          />
          <Stage
            number="03"
            title="Apply the statute"
            accent="text-amber-700"
            body="Deterministic rules compare what was read against the number written in the Act. Same documents, same verdict, every time — with the section cited."
          />
          <Stage
            number="04"
            title="Show the evidence"
            accent="text-emerald-700"
            body="Every finding links to the cell it came from, so an employer can check it and an inspector can act on it. A finding nobody can verify is one an employer can simply deny."
          />
        </div>
      </section>

      {/* The division of labour. Stated openly because it is the design choice
          that most affects whether the output can be trusted. */}
      <section className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-2">
        <article className="space-y-4 rounded-3xl border border-sky-200/90 bg-white/90 p-8 shadow-sm backdrop-blur-xl">
          <Badge tone="low">Model</Badge>
          <h3 className="text-xl font-bold text-slate-900">
            Reading, matching and explaining
          </h3>
          <p className="text-sm leading-relaxed text-slate-700">
            A model reads handwriting and stamps, works out which printed column is
            which, decides that "R. Kumar" and "RAJESH KUMAR S/O RAM LAL" are one
            person, answers questions about a standing order written in prose, and
            explains a finding in plain language. These have no fixed answer and no
            threshold to look up, which is exactly what a model is for.
          </p>
          <p className="text-sm leading-relaxed text-slate-700">
            It also reviews the findings and can raise problems the rules never
            anticipated. Those are marked advisory: they carry no citation and do
            not affect a score.
          </p>
        </article>

        <article className="space-y-4 rounded-3xl border border-amber-200/90 bg-white/90 p-8 shadow-sm backdrop-blur-xl">
          <Badge tone="medium">Rules</Badge>
          <h3 className="text-xl font-bold text-slate-900">
            Deciding compliance
          </h3>
          <p className="text-sm leading-relaxed text-slate-700">
            Section 18(3) caps deductions at fifty per cent. Section 14 requires
            overtime at twice the ordinary rate. Section 17(1)(iv) sets the seventh
            of the following month. These are single numbers from an Act, and the
            comparison against them is plain arithmetic.
          </p>
          <p className="text-sm leading-relaxed text-slate-700">
            No model participates in that decision. An employer who disputes a
            finding must get the same answer on a re-run, and the basis has to be a
            provision they can look up — not a judgement they cannot examine.
          </p>
        </article>
      </section>

      {/* The four Codes */}
      <section className="mx-auto max-w-6xl space-y-8">
        <div className="mx-auto max-w-3xl space-y-3 text-center">
          <h2 className="text-3xl font-extrabold text-slate-900 sm:text-4xl">
            The four Labour Codes
          </h2>
          <p className="text-base text-slate-600 sm:text-lg">
            Rule packs are built from the Gazette and IndiaCode text of each Act.
            Where an Act leaves a figure to be notified by the appropriate
            Government, the rule says so and is weighted lightly until that
            notification is obtained.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {codes.map((code) => (
            <article
              key={code}
              className="space-y-4 rounded-3xl border border-slate-200/90 bg-white/85 p-8 shadow-sm backdrop-blur-xl transition-colors hover:border-sky-400/60"
            >
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-xl font-bold text-slate-950 sm:text-2xl">
                  {CODE_LABELS[code]}
                </h3>
                {rules.data?.by_code[code] !== undefined && (
                  <Badge tone="neutral">{rules.data.by_code[code]} rules</Badge>
                )}
              </div>

              <p className="text-sm leading-relaxed text-slate-700 sm:text-base">
                {code === "WAGES" &&
                  "Minimum wage by state and skill category, overtime at not less than twice the ordinary rate, the fifty per cent deduction cap, wage periods of no more than a month, payment by the seventh of the following month, and settlement within two working days of exit."}
                {code === "OSH" &&
                  "Establishment registration, appointment letters for every employee, daily and weekly hour limits, contractor licensing against the number actually deployed, accident notification, and welfare and health obligations."}
                {code === "SOCIAL_SECURITY" &&
                  "Provident fund and ESIC coverage reconciled worker by worker against the wage register, the declared contribution base against the wages actually paid, deposit timeliness, and gratuity for fixed-term employees."}
                {code === "INDUSTRIAL_RELATIONS" &&
                  "Works Committee at a hundred workers, Grievance Redressal Committee at twenty with proportionate women's representation, standing orders at three hundred, strike notice periods, and prior permission for retrenchment."}
              </p>
            </article>
          ))}
        </div>
      </section>

      {/* Where to go */}
      <section className="mx-auto grid max-w-5xl gap-4 sm:grid-cols-3">
        <Shortcut
          to="/documents"
          icon={Upload}
          title="Submit filings"
          body="Upload a wage period and watch each document get identified and read."
        />
        <Shortcut
          to="/establishments"
          icon={Building2}
          title="Establishments"
          body="Compliance position, evidence completeness and applicable thresholds."
        />
        <Shortcut
          to="/worklist"
          icon={ClipboardList}
          title="Worklist"
          body="Establishments ranked for inspection by risk and by evidence gaps."
        />
      </section>
    </div>
  );
}

function Stage({
  number,
  title,
  body,
  accent,
}: {
  number: string;
  title: string;
  body: string;
  accent: string;
}) {
  return (
    <div className="space-y-3 rounded-3xl border border-slate-200/90 bg-white/85 p-6 shadow-sm backdrop-blur-md">
      <span className={`block font-mono text-base font-extrabold ${accent}`}>
        {number}
      </span>
      <h4 className="text-base font-bold text-slate-900">{title}</h4>
      <p className="text-sm leading-relaxed text-slate-600">{body}</p>
    </div>
  );
}

function Shortcut({
  to,
  icon: Icon,
  title,
  body,
}: {
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <Link
      to={to}
      className="group space-y-2 rounded-3xl border border-slate-200/90 bg-white/85 p-6 shadow-sm backdrop-blur-md transition-colors hover:border-sky-400"
    >
      <div className="flex items-center justify-between">
        <Icon className="h-5 w-5 text-sky-700" />
        <ArrowRight className="h-4 w-4 text-slate-400 transition-transform group-hover:translate-x-0.5" />
      </div>
      <h4 className="text-base font-bold text-slate-900">{title}</h4>
      <p className="text-sm leading-relaxed text-slate-600">{body}</p>
    </Link>
  );
}
