import { Link } from "react-router-dom";
import {
  BookOpen,
  Lock,
  Shield,
  Upload,
} from "lucide-react";

import { useAuth } from "@/lib/auth";

/** Landing page.
 *
 *  Provides an intuitive, plain-language overview of the compliance check system.
 *  Shows clear step-by-step guidance for all visitors and direct access to filings and rules.
 */

export function HomePage() {
  const { user } = useAuth();

  return (
    <div className="space-y-20 sm:space-y-24">
      {/* Hero */}
      <section className="mx-auto max-w-5xl space-y-8 pt-6 text-center">
        <div className="inline-flex items-center gap-2.5 rounded-full border border-slate-300/80 bg-white/80 px-5 py-2 text-sm font-bold text-slate-800 shadow-sm backdrop-blur-md">
          <Shield className="h-4 w-4 text-sky-700" />
          Ministry of Labour &amp; Employment &middot; Shram Suvidha
        </div>

        <h1 className="text-4xl font-extrabold leading-[1.1] tracking-tight text-slate-950 sm:text-6xl lg:text-7xl">
          AI Driven Smart Labour{" "}
          <span className="bg-gradient-to-r from-sky-700 via-blue-700 to-indigo-700 bg-clip-text text-transparent">
            Compliance Inspection
          </span>
        </h1>

        <p className="mx-auto max-w-3xl text-lg font-medium leading-relaxed text-slate-700 sm:text-2xl">
          Analyze workplace documents, detect compliance gaps, identify anomalies, and generate evidence-backed risk insights under India’s Labour Codes.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
          {user ? (
            <Link
              to="/documents"
              className="flex items-center gap-2 rounded-full bg-slate-900 px-8 py-3.5 text-base font-bold text-white shadow-lg transition-all hover:bg-slate-800"
            >
              <Upload className="h-5 w-5" />
              Submit documents
            </Link>
          ) : (
            <div
              className="flex cursor-not-allowed select-none items-center gap-2 rounded-full border border-slate-300/80 bg-slate-100/90 px-8 py-3.5 text-base font-bold text-slate-400 opacity-70 shadow-none"
              title="Sign in required to submit documents"
            >
              <Lock className="h-5 w-5 text-amber-500" />
              <span>Submit documents (Locked)</span>
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

      {/* How a filing becomes a finding */}
      <section className="mx-auto max-w-6xl space-y-10">
        <div className="mx-auto max-w-4xl space-y-4 text-center">
          <h2 className="text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">
            How a filing becomes a finding
          </h2>
          <p className="text-lg font-medium leading-relaxed text-slate-700 sm:text-xl">
            Four simple steps. The system reads your files, confirms every number, and checks official rules so every result is clear and reliable.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <Stage
            number="01"
            title="Read the documents"
            accent="text-sky-700"
            body="Digital PDFs are read immediately. Scanned papers and photos are read with smart vision tools that capture each table, row, and word accurately."
          />
          <Stage
            number="02"
            title="Check every number"
            accent="text-indigo-700"
            body="Every wage, work hour, and date is verified directly against your uploaded page. If any number is unclear, it is paused for a human check instead of guessing."
          />
          <Stage
            number="03"
            title="Match with the law"
            accent="text-amber-700"
            body="The system checks each verified figure against official statutory rules. You get the same fair, reliable result every time, with the exact legal rule cited."
          />
          <Stage
            number="04"
            title="Clear proof for everyone"
            accent="text-emerald-700"
            body="Every finding links directly to the exact page and table cell it came from. Employers can see why, and officers can review the proof without any confusion."
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
      <h3 className="text-xl font-bold text-slate-950 capitalize">{title}</h3>
      <p className="text-base font-medium leading-relaxed text-slate-700">{body}</p>
    </div>
  );
}
