import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  Building2,
  ClipboardList,
  Coins,
  Eye,
  FileSearch,
  HardHat,
  Lock,
  Scale,
  Shield,
  ShieldCheck,
  Upload,
  Users,
} from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { count, paise } from "@/lib/format";
import {
  type FindingCounts,
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

  const rules = useQuery({
    queryKey: ["rules-overview"],
    queryFn: () => api.get<RulesOverview>("/rules"),
    retry: false,
  });

  const findings = useQuery({
    queryKey: ["finding-counts", null],
    queryFn: () => api.get<FindingCounts>("/findings/counts?open_only=true"),
    enabled: Boolean(user),
    retry: false,
  });

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
          {user ? (
            <Link
              to="/documents"
              className="flex items-center gap-2 rounded-full bg-slate-900 px-8 py-3.5 text-base font-bold text-white shadow-lg transition-all hover:bg-slate-800"
            >
              <Upload className="h-5 w-5" />
              Submit filings
            </Link>
          ) : (
            <div
              className="flex cursor-not-allowed select-none items-center gap-2 rounded-full border border-slate-300/80 bg-slate-100/90 px-8 py-3.5 text-base font-bold text-slate-400 opacity-70 shadow-none"
              title="Sign in required to submit filings"
            >
              <Lock className="h-5 w-5 text-amber-500" />
              <span>Submit filings (Locked)</span>
            </div>
          )}
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
              className="rounded-full bg-sky-600 px-7 py-3.5 text-base font-bold text-white shadow-md transition-all hover:bg-sky-700"
            >
              Sign in
            </Link>
          )}
        </div>
      </section>

      {/* Signed-in summary */}
      {user && (
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

      {/* The four Codes */}
      <section className="mx-auto max-w-6xl space-y-10">
        <div className="mx-auto max-w-4xl space-y-4 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-sky-800">
            Statutory Framework
          </div>
          <h2 className="text-3xl font-black tracking-tight text-slate-950 sm:text-5xl">
            The four Labour Codes
          </h2>
          <p className="text-lg sm:text-xl font-medium leading-relaxed text-slate-700">
            All compliance rule packs are derived directly from the official Gazette and IndiaCode statutory text. Where an Act requires an operative threshold or formula to be notified by the appropriate Government, the rule states so clearly and is evaluated with care until that notification is officially obtained.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
          {/* Code on Wages */}
          <article className="flex flex-col justify-between space-y-5 rounded-3xl border border-sky-200/90 bg-white/95 p-8 sm:p-10 shadow-[0_12px_40px_rgba(56,189,248,0.08)] backdrop-blur-xl transition-all hover:border-sky-400 hover:shadow-md">
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-sky-200 bg-sky-100 text-sky-700 shadow-sm">
                    <Coins className="h-6 w-6" />
                  </div>
                  <h3 className="text-2xl font-black text-slate-950 sm:text-3xl">
                    Code on Wages, 2019
                  </h3>
                </div>
                {rules.data?.by_code["WAGES"] !== undefined && (
                  <Badge tone="good">{rules.data.by_code["WAGES"]} rules</Badge>
                )}
              </div>
              <p className="text-base sm:text-lg leading-relaxed text-slate-700 font-medium">
                Guarantees fair, universal, and timely wage payments across all establishments. The code establishes statutory minimum wage floors according to state and skill categories, ensures that overtime is compensated at double the normal rate, and protects workers by strictly capping total deductions at fifty percent. Furthermore, wages must be disbursed by the 7th of each month, with final dues paid within two working days of an employee leaving.
              </p>
            </div>
          </article>

          {/* Industrial Relations Code */}
          <article className="flex flex-col justify-between space-y-5 rounded-3xl border border-indigo-200/90 bg-white/95 p-8 sm:p-10 shadow-[0_12px_40px_rgba(99,102,241,0.08)] backdrop-blur-xl transition-all hover:border-indigo-400 hover:shadow-md">
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-indigo-200 bg-indigo-100 text-indigo-700 shadow-sm">
                    <Users className="h-6 w-6" />
                  </div>
                  <h3 className="text-2xl font-black text-slate-950 sm:text-3xl">
                    Industrial Relations Code, 2020
                  </h3>
                </div>
                {rules.data?.by_code["INDUSTRIAL_RELATIONS"] !== undefined && (
                  <Badge tone="good">{rules.data.by_code["INDUSTRIAL_RELATIONS"]} rules</Badge>
                )}
              </div>
              <p className="text-base sm:text-lg leading-relaxed text-slate-700 font-medium">
                Promotes constructive workplace cooperation, fair dispute redressal, and transparent worker representation. It requires establishments with 20 or more workers to maintain a balanced Grievance Redressal Committee with adequate representation for women, while units with 100 or more workers establish formal Works Committees. It also standardizes standing orders, enforces statutory strike notices, and establishes transparent procedures for retrenchment.
              </p>
            </div>
          </article>

          {/* Code on Social Security */}
          <article className="flex flex-col justify-between space-y-5 rounded-3xl border border-purple-200/90 bg-white/95 p-8 sm:p-10 shadow-[0_12px_40px_rgba(168,85,247,0.08)] backdrop-blur-xl transition-all hover:border-purple-400 hover:shadow-md">
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-purple-200 bg-purple-100 text-purple-700 shadow-sm">
                    <ShieldCheck className="h-6 w-6" />
                  </div>
                  <h3 className="text-2xl font-black text-slate-950 sm:text-3xl">
                    Code on Social Security, 2020
                  </h3>
                </div>
                {rules.data?.by_code["SOCIAL_SECURITY"] !== undefined && (
                  <Badge tone="good">{rules.data.by_code["SOCIAL_SECURITY"]} rules</Badge>
                )}
              </div>
              <p className="text-base sm:text-lg leading-relaxed text-slate-700 font-medium">
                Provides essential healthcare and life-cycle financial security across the entire workforce. The platform reconciles employee Provident Fund (EPF) and ESIC health benefits worker-by-worker against filed wage registers, confirms that declared contributions match wages paid, ensures timely statutory deposits, and secures proportionate gratuity for fixed-term employees.
              </p>
            </div>
          </article>

          {/* OSH Code */}
          <article className="flex flex-col justify-between space-y-5 rounded-3xl border border-teal-200/90 bg-white/95 p-8 sm:p-10 shadow-[0_12px_40px_rgba(20,184,166,0.08)] backdrop-blur-xl transition-all hover:border-teal-400 hover:shadow-md">
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-teal-200 bg-teal-100 text-teal-700 shadow-sm">
                    <HardHat className="h-6 w-6" />
                  </div>
                  <h3 className="text-2xl font-black text-slate-950 sm:text-3xl">
                    OSH &amp; Working Conditions Code, 2020
                  </h3>
                </div>
                {rules.data?.by_code["OSH"] !== undefined && (
                  <Badge tone="good">{rules.data.by_code["OSH"]} rules</Badge>
                )}
              </div>
              <p className="text-base sm:text-lg leading-relaxed text-slate-700 font-medium">
                Safeguards the health, safety, and daily working environment of every employee. It mandates official establishment registration and written appointment letters for all staff, enforces healthy daily and weekly work limits with statutory rest periods, regulates labor contractor licenses according to actual deployed staff, and guarantees clean welfare facilities alongside prompt reporting of workplace accidents.
              </p>
            </div>
          </article>
        </div>
      </section>

      {/* Where to go */}
      <section className="mx-auto grid max-w-5xl gap-4 sm:grid-cols-3">
        {user ? (
          <Shortcut
            to="/documents"
            icon={Upload}
            title="Submit filings"
            body="Upload a wage period and watch each document get identified and read."
          />
        ) : (
          <div
            className="cursor-not-allowed select-none rounded-3xl border border-slate-200/80 bg-white/60 p-6 opacity-60 backdrop-blur-md"
            title="Sign in required to submit filings"
          >
            <div className="flex items-center justify-between">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
                <Lock className="h-5 w-5 text-amber-500" />
              </div>
              <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-bold text-amber-700">
                Locked
              </span>
            </div>
            <h4 className="mt-4 text-base font-bold text-slate-500">
              Submit filings
            </h4>
            <p className="mt-1 text-xs text-slate-400">
              Upload a wage period and watch each document get identified and read (Sign-in required).
            </p>
          </div>
        )}
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
