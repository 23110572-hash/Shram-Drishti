import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  CheckCircle2,
  ChevronDown,
  FlaskConical,
  Scale,
  ShieldQuestion,
} from "lucide-react";

import { api } from "@/lib/api";
import { count } from "@/lib/format";
import {
  CODE_SHORT_LABELS,
  RULE_BASIS_EXPLANATIONS,
  RULE_BASIS_LABELS,
  type LabourCode,
  type RuleBasis,
  type RuleOut,
  type RulesOverview,
} from "@/lib/types";
import {
  AwaitingNotificationBadge,
  Badge,
  KindBadge,
  SeverityBadge,
} from "@/components/ui/Badge";
import {
  Caution,
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "@/components/ui/State";

/** Rule packs, shown openly.
 *
 *  An employer accused of a breach is entitled to see the exact test that was
 *  applied, the section it comes from, and what the figure it applies rests on.
 *  A compliance system that will not show its own rules cannot expect to be
 *  trusted by the people it judges.
 *
 *  Each rule states its basis rather than a pass/fail "verified" flag. That flag
 *  conflated two unrelated things — whether a statutory figure had been
 *  confirmed, and whether the rule could be trusted — so a check that a register
 *  adds up, which involves no statutory figure at all, was labelled unverified
 *  and quietly discounted in scoring. Only RULES_PENDING is a real caveat, and it
 *  is the only basis that carries a warning here.
 */

/** What has to be obtained to clear each pending rule, grouped by instrument.
 *
 *  Listed on the page rather than in a comment because "eleven rules await a
 *  notification" is not actionable and "these five documents would clear them"
 *  is. */
const PENDING_DOCUMENTS: { instrument: string; clears: string }[] = [
  {
    instrument: "Code on Wages (Central) Rules, 2020",
    clears: "overtime hours threshold",
  },
  {
    instrument: "OSH Code (Central) Rules, 2020",
    clears:
      "creche headcount, daily and weekly hour ceilings, accident notification period, health examination classes",
  },
  {
    instrument: "Employees' Provident Funds Scheme, 1952 (para 38) and EPF Act s.6",
    clears: "deposit deadline and the 12% contribution rate",
  },
  {
    instrument: "ESI (Central) Rules, r.50",
    clears: "the wage ceiling for ESIC coverage",
  },
  {
    instrument: "State minimum wage notifications",
    clears: "the wage floor for each State assessed",
  },
];

export function RulesPage() {
  const [code, setCode] = useState<LabourCode | "">("");
  const [onlyPending, setOnlyPending] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const overview = useQuery({
    queryKey: ["rules-overview"],
    queryFn: () => api.get<RulesOverview>("/rules"),
  });

  const params = new URLSearchParams();
  if (code) params.set("code", code);
  if (onlyPending) params.set("awaiting_notification", "true");

  const rules = useQuery({
    queryKey: ["rules-list", code, onlyPending],
    queryFn: () => api.get<RuleOut[]>(`/rules/list?${params.toString()}`),
  });

  const summary = overview.data;
  const list = rules.data ?? [];

  return (
    <div className="space-y-10">
      <header className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2.5 rounded-full border border-amber-200 bg-amber-50 px-4 py-1.5 text-sm font-bold text-amber-900">
            <BookOpen className="h-4 w-4" />
            Codified statute
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950 sm:text-5xl">
            Rules
          </h1>
          <p className="mt-2 max-w-3xl text-base text-slate-700 sm:text-lg">
            Every compliance test the system applies, the statutory provision it
            rests on, and where that provision was read from. Nothing is hidden:
            a finding you cannot audit is a finding you cannot defend.
          </p>
        </div>

        {summary && (
          <div className="flex items-center gap-3">
            <div className="rounded-3xl border border-slate-200 bg-white/85 px-6 py-3.5 text-center shadow-sm">
              <span className="block text-xs font-bold uppercase tracking-wider text-slate-500">
                Rules
              </span>
              <span className="text-xl font-extrabold text-slate-900">
                {count(summary.total_rules)}
              </span>
            </div>
            <div className="rounded-3xl border border-emerald-300 bg-emerald-50/90 px-6 py-3.5 text-center shadow-sm">
              <span
                className="block text-xs font-bold uppercase tracking-wider text-slate-500"
                title="Rules that need nothing further to be applied: the figure is in the Act, or the rule applies no outside figure at all."
              >
                Sound as they stand
              </span>
              <span className="text-xl font-extrabold text-emerald-900">
                {count(summary.sound_rules)}
              </span>
            </div>
          </div>
        )}
      </header>

      {/* What each rule's figure rests on. Shown before the caution, so the
          caution reads as one category out of four rather than as a verdict on
          the rule set. */}
      {summary && (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {(Object.keys(RULE_BASIS_LABELS) as RuleBasis[]).map((basis) => {
            const total = summary.by_basis[basis] ?? 0;
            const pending = basis === "RULES_PENDING";

            return (
              <article
                key={basis}
                className={[
                  "space-y-1.5 rounded-3xl border p-5 shadow-sm",
                  pending
                    ? "border-amber-300 bg-amber-50/80"
                    : "border-emerald-200 bg-emerald-50/50",
                ].join(" ")}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <h2 className="text-sm font-bold text-slate-900">
                    {RULE_BASIS_LABELS[basis]}
                  </h2>
                  <span
                    className={[
                      "text-2xl font-extrabold",
                      pending ? "text-amber-900" : "text-emerald-900",
                    ].join(" ")}
                  >
                    {total}
                  </span>
                </div>
                <p className="text-xs leading-relaxed text-slate-700">
                  {RULE_BASIS_EXPLANATIONS[basis]}
                </p>
              </article>
            );
          })}
        </section>
      )}

      {overview.isError && (
        <ErrorState
          error={overview.error}
          context="the rule packs"
          onRetry={() => void overview.refetch()}
        />
      )}

      {summary && summary.awaiting_notification > 0 && (
        <Caution
          title={`${summary.awaiting_notification} rules are waiting on a government notification`}
        >
          <p>
            The four Codes create these obligations but do not state the figure
            each one turns on. Parliament left those figures to be notified by the
            appropriate Government. For example, s.24(3) of the OSH Code says only
            that the Central Government "may make rules" for creche facilities —
            no headcount appears in the Act at all, so no reading of the Act can
            supply one.
          </p>
          <p className="mt-2">
            These rules still run and are shown to inspectors, but the figure
            compared against comes from a secondary source. Findings from them are
            weighted lightly and should not be enforced until the notification is
            checked.
          </p>
          <div className="mt-3">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-700">
              What would clear them
            </p>
            <ul className="mt-1.5 space-y-1">
              {PENDING_DOCUMENTS.map((item) => (
                <li key={item.instrument} className="text-sm leading-relaxed">
                  <span className="font-semibold">{item.instrument}</span>
                  <span className="text-slate-600"> — {item.clears}</span>
                </li>
              ))}
            </ul>
          </div>
        </Caution>
      )}

      {/* Packs */}
      {summary && (
        <section className="grid gap-4 sm:grid-cols-2">
          {summary.packs.map((pack) => (
            <article
              key={`${pack.pack}@${pack.version}`}
              className="space-y-3 rounded-3xl border border-sky-200/90 bg-white/95 p-6 shadow-sm backdrop-blur-xl"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">
                    {pack.pack.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())}
                  </h2>
                  <p className="font-mono text-xs text-slate-500">
                    {pack.version} · {pack.jurisdiction}
                  </p>
                </div>
                {pack.is_overlay && <Badge tone="pending">State overlay</Badge>}
              </div>

              {pack.description && (
                <p className="text-xs leading-relaxed text-slate-600">
                  {pack.description}
                </p>
              )}

              <div className="flex items-center gap-2">
                <Badge tone="neutral">{pack.rule_count} rules</Badge>
                <Badge tone="good">{pack.sound_count} sound</Badge>
                {pack.awaiting_notification_count > 0 && (
                  <Badge tone="medium">
                    {pack.awaiting_notification_count} awaiting notification
                  </Badge>
                )}
              </div>
            </article>
          ))}
        </section>
      )}

      {/* Load errors, if any. These would mean a rule is not running at all. */}
      {summary && summary.issues.some((issue) => issue.level === "error") && (
        <section className="space-y-2 rounded-3xl border border-rose-300 bg-rose-50/80 p-6">
          <h2 className="text-sm font-bold uppercase tracking-wider text-rose-900">
            Rule pack errors
          </h2>
          <p className="text-xs text-rose-950">
            These rules failed validation and are not being applied.
          </p>
          <ul className="space-y-1 text-sm text-rose-950">
            {summary.issues
              .filter((issue) => issue.level === "error")
              .map((issue, index) => (
                <li key={index} className="font-mono text-xs">
                  <span className="font-bold">{issue.rule_id}</span> — {issue.message}
                </li>
              ))}
          </ul>
        </section>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setCode("")}
          aria-pressed={code === ""}
          className={[
            "cursor-pointer rounded-full border px-4 py-2 text-sm font-bold transition-colors",
            code === ""
              ? "border-slate-900 bg-slate-900 text-white"
              : "border-slate-300 bg-white/90 text-slate-700 hover:bg-slate-50",
          ].join(" ")}
        >
          All Codes
        </button>

        {(Object.keys(CODE_SHORT_LABELS) as LabourCode[]).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setCode(item)}
            aria-pressed={code === item}
            className={[
              "cursor-pointer rounded-full border px-4 py-2 text-sm font-bold transition-colors",
              code === item
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 bg-white/90 text-slate-700 hover:bg-slate-50",
            ].join(" ")}
          >
            {CODE_SHORT_LABELS[item]}
            {summary?.by_code[item] !== undefined && (
              <span className="ml-1.5 opacity-70">{summary.by_code[item]}</span>
            )}
          </button>
        ))}

        <label className="ml-auto flex cursor-pointer items-center gap-2.5 rounded-full border border-slate-300 bg-white/90 px-4 py-2 text-sm font-bold text-slate-700">
          <input
            type="checkbox"
            checked={onlyPending}
            onChange={(event) => setOnlyPending(event.target.checked)}
            className="h-4 w-4 cursor-pointer rounded border-slate-400 text-sky-600"
          />
          Awaiting a notification only
        </label>
      </div>

      {/* Rules */}
      <div className="overflow-hidden rounded-3xl border border-sky-200/90 bg-white/95 shadow-sm backdrop-blur-xl">
        {rules.isPending && <SkeletonRows rows={8} columns={3} />}

        {rules.isError && <ErrorState error={rules.error} context="the rules" />}

        {rules.isSuccess && list.length === 0 && (
          <EmptyState
            icon={ShieldQuestion}
            title="No rules match"
            description="Clear the filters to see the full rule set."
          />
        )}

        {rules.isSuccess && list.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {list.map((rule) => {
              const open = expanded === rule.id;

              return (
                <li key={rule.id}>
                  <button
                    type="button"
                    onClick={() => setExpanded(open ? null : rule.id)}
                    aria-expanded={open}
                    className="flex w-full cursor-pointer items-start gap-4 px-6 py-4 text-left transition-colors hover:bg-sky-50/50"
                  >
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <SeverityBadge severity={rule.severity} />
                        <KindBadge kind={rule.kind} />
                        <Badge tone="info">{CODE_SHORT_LABELS[rule.code]}</Badge>
                        {rule.awaiting_notification ? (
                          <AwaitingNotificationBadge />
                        ) : (
                          <Badge
                            tone="good"
                            title={RULE_BASIS_EXPLANATIONS[rule.basis]}
                          >
                            <CheckCircle2 aria-hidden="true" className="h-3 w-3" />
                            {RULE_BASIS_LABELS[rule.basis]}
                          </Badge>
                        )}
                        {rule.fixture_count > 0 && (
                          <Badge
                            tone="neutral"
                            title="Worked examples proving the rule behaves as intended, including a case that must fail"
                          >
                            <FlaskConical aria-hidden="true" className="h-3 w-3" />
                            {rule.fixture_count} test cases
                          </Badge>
                        )}
                      </div>

                      <p className="text-base font-bold text-slate-900">
                        {rule.title}
                      </p>

                      <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-600">
                        <Scale aria-hidden="true" className="h-3.5 w-3.5" />
                        {rule.citation}
                      </p>
                    </div>

                    <ChevronDown
                      className={`mt-1 h-4 w-4 shrink-0 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
                    />
                  </button>

                  {open && (
                    <div className="space-y-4 border-t border-slate-100 bg-slate-50/60 px-6 py-5">
                      <Detail label="Rule identifier" mono>
                        {rule.id} · {rule.pack}@{rule.pack_version}
                      </Detail>

                      <div>
                        <p className="text-xs font-bold uppercase tracking-wider text-slate-600">
                          What the figure in this rule rests on
                        </p>
                        <div
                          className={[
                            "mt-1 rounded-xl border px-3 py-2.5",
                            rule.awaiting_notification
                              ? "border-amber-300 bg-amber-50/70"
                              : "border-emerald-200 bg-emerald-50/50",
                          ].join(" ")}
                        >
                          <p className="text-sm font-bold text-slate-900">
                            {RULE_BASIS_LABELS[rule.basis]}
                          </p>
                          <p className="mt-0.5 text-sm leading-relaxed text-slate-700">
                            {RULE_BASIS_EXPLANATIONS[rule.basis]}
                          </p>
                        </div>
                      </div>

                      <Detail label="Where the provision was read from">
                        {rule.source_ref}
                      </Detail>

                      <Detail label="Message to the employer">
                        {rule.message_en}
                        {rule.message_hi && (
                          <span className="mt-1.5 block text-slate-600">
                            {rule.message_hi}
                          </span>
                        )}
                      </Detail>

                      {rule.remediation_en && (
                        <Detail label="Remedy offered">
                          {rule.remediation_en}
                        </Detail>
                      )}

                      {rule.applicability && (
                        <Detail label="Applies only when" mono>
                          {rule.applicability}
                        </Detail>
                      )}

                      {/* The test itself. Published deliberately: the expression is
                          the whole basis of any finding it produces. */}
                      <Detail label="Compliance test (true means compliant)" mono>
                        {rule.expression}
                      </Detail>

                      <div className="flex flex-wrap gap-2 text-xs">
                        {rule.for_each && (
                          <Badge tone="neutral">Checked per {rule.for_each} row</Badge>
                        )}
                        {rule.requires.map((requirement) => (
                          <Badge key={requirement} tone="info">
                            needs {requirement}
                          </Badge>
                        ))}
                        <Badge tone="neutral">weight {rule.weight}</Badge>
                      </div>

                      {rule.fixtures.length > 0 && (
                        <div className="space-y-1.5">
                          <p className="text-xs font-bold uppercase tracking-wider text-slate-600">
                            Test cases
                          </p>
                          <ul className="space-y-1">
                            {rule.fixtures.map((fixture) => (
                              <li
                                key={fixture.name}
                                className="flex items-center gap-2 text-xs"
                              >
                                <Badge tone={fixture.should_pass ? "good" : "critical"}>
                                  {fixture.should_pass ? "must pass" : "must fail"}
                                </Badge>
                                <span className="font-mono text-slate-700">
                                  {fixture.name}
                                </span>
                                {fixture.note && (
                                  <span className="text-slate-500">— {fixture.note}</span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function Detail({
  label,
  children,
  mono = false,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-wider text-slate-600">
        {label}
      </p>
      <p
        className={[
          "mt-1 leading-relaxed text-slate-800",
          mono
            ? "break-words rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-xs"
            : "text-sm",
        ].join(" ")}
      >
        {children}
      </p>
    </div>
  );
}
