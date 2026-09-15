import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Eye,
  FileSearch,
  Lock,
  Scale,
  Shield,
  Upload,
} from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { count, paise } from "@/lib/format";
import {
  type FindingCounts,
  type RulesOverview,
} from "@/lib/types";

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
          Ministry of Labour &amp; Employment &middot; Shram Suvidha
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

      {/* How a filing becomes a finding */}
      <section className="mx-auto max-w-6xl space-y-10">
        <div className="mx-auto max-w-4xl space-y-4 text-center">
          <h2 className="text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">
            How a filing becomes a finding
          </h2>
          <p className="text-lg font-medium leading-relaxed text-slate-700 sm:text-xl">
            Four simple stages. The division of labour between the model and the rules is
            deliberate and is the reason a finding can be defended.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <Stage
            number="01"
            title="Read the page"
            accent="text-sky-700"
            body="A PDF with a text layer is read directly and exactly. Anything else is rasterised, sent to OCR, and given to a vision model together with the page image so the two can be cross checked."
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
            body="Deterministic rules compare what was read against the number written in the Act. Same documents, same verdict, every time with the section cited."
          />
          <Stage
            number="04"
            title="Show the evidence"
            accent="text-emerald-700"
            body="Every finding links to the cell it came from, so an employer can check it and an inspector can act on it. A finding nobody can verify is one an employer can simply deny."
          />
        </div>
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
    <div className="space-y-4 rounded-3xl border border-slate-200/90 bg-white/95 p-7 shadow-sm backdrop-blur-md transition-all hover:border-slate-300 hover:shadow-md">
      <span className={`block font-mono text-xl font-black ${accent}`}>
        {number}
      </span>
      <h3 className="text-xl font-bold text-slate-950">{title}</h3>
      <p className="text-base font-medium leading-relaxed text-slate-700">{body}</p>
    </div>
  );
}
