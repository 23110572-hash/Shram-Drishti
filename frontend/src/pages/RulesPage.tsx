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
  type LabourCode,
  type RuleOut,
  type RulesOverview,
} from "@/lib/types";
import {
  Badge,
  KindBadge,
  SeverityBadge,
  UnverifiedRuleBadge,
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
 *  applied, the section it comes from, and whether that threshold has been
 *  confirmed against the primary statutory text. A compliance system that will
 *  not show its own rules cannot expect to be trusted by the people it judges.
 *
 *  Unverified rules are listed first rather than buried, because those are the
 *  ones a reviewer needs to look at.
 */

export function RulesPage() {
  const [code, setCode] = useState<LabourCode | "">("");
  const [onlyUnverified, setOnlyUnverified] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const overview = useQuery({
    queryKey: ["rules-overview"],
    queryFn: () => api.get<RulesOverview>("/rules"),
  });

  const params = new URLSearchParams();
  if (code) params.set("code", code);
  if (onlyUnverified) params.set("verified", "false");

  const rules = useQuery({
    queryKey: ["rules-list", code, onlyUnverified],
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
              <span className="block text-xs font-bold uppercase tracking-wider text-slate-500">
                Verified
              </span>
              <span className="text-xl font-extrabold text-emerald-900">
                {count(summary.verified_rules)}
              </span>
            </div>
          </div>
        )}
      </header>

      {overview.isError && (
        <ErrorState
          error={overview.error}
          context="the rule packs"
          onRetry={() => void overview.refetch()}
        />
      )}

      {summary && summary.unverified_rules > 0 && (
        <Caution title={`${summary.unverified_rules} thresholds not yet confirmed`}>
          These rules are usable and are shown to inspectors, but their operative
          number was read from a secondary source rather than the primary
          statutory text — typically because the value lives in the Central or
          State Rules rather than in the Act. Findings from them are flagged,
          weighted lightly in scoring, and should not be enforced as they stand.
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
                <Badge tone="good">{pack.verified_count} verified</Badge>
                {pack.unverified_count > 0 && (
                  <Badge tone="medium">{pack.unverified_count} unverified</Badge>
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
            checked={onlyUnverified}
            onChange={(event) => setOnlyUnverified(event.target.checked)}
            className="h-4 w-4 cursor-pointer rounded border-slate-400 text-sky-600"
          />
          Unverified only
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
                        {rule.verified ? (
                          <Badge tone="good">
                            <CheckCircle2 aria-hidden="true" className="h-3 w-3" />
                            Verified against primary text
                          </Badge>
                        ) : (
                          <UnverifiedRuleBadge />
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
