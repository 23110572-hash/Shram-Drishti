import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  Lightbulb,
  Search,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import {
  CODE_LABELS,
  CODE_SHORT_LABELS,
  type LabourCode,
  type RuleOut,
} from "@/lib/types";
import { RULE_GUIDE_DATA, type RuleGuideItem } from "@/lib/ruleGuideData";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/State";

const CODE_COLORS: Record<LabourCode, { badgeBg: string; badgeText: string; border: string; stepBg: string }> = {
  WAGES: {
    badgeBg: "bg-emerald-50",
    badgeText: "text-emerald-800",
    border: "border-emerald-200",
    stepBg: "bg-emerald-600 text-white",
  },
  INDUSTRIAL_RELATIONS: {
    badgeBg: "bg-indigo-50",
    badgeText: "text-indigo-800",
    border: "border-indigo-200",
    stepBg: "bg-indigo-600 text-white",
  },
  SOCIAL_SECURITY: {
    badgeBg: "bg-sky-50",
    badgeText: "text-sky-800",
    border: "border-sky-200",
    stepBg: "bg-sky-600 text-white",
  },
  OSH: {
    badgeBg: "bg-amber-50",
    badgeText: "text-amber-900",
    border: "border-amber-200",
    stepBg: "bg-amber-600 text-white",
  },
};

export function RulesPage() {
  const [selectedCode, setSelectedCode] = useState<LabourCode | "">("");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const rulesQuery = useQuery({
    queryKey: ["rules-list"],
    queryFn: () => api.get<RuleOut[]>("/rules/list"),
  });

  const allRules = rulesQuery.data ?? [];

  // Filter rules by selected code tab and search query
  const filteredRules = useMemo(() => {
    return allRules.filter((rule) => {
      if (selectedCode && rule.code !== selectedCode) {
        return false;
      }
      if (!searchQuery.trim()) {
        return true;
      }
      const q = searchQuery.toLowerCase();
      const guide = RULE_GUIDE_DATA[rule.id];
      const matchTitle = rule.title.toLowerCase().includes(q);
      const matchCitation = rule.citation.toLowerCase().includes(q);
      const matchCode = (CODE_SHORT_LABELS[rule.code] ?? "").toLowerCase().includes(q);
      const matchExplanation = guide?.simpleExplanation.toLowerCase().includes(q) || false;
      const matchExample = guide?.exampleScenario.toLowerCase().includes(q) || false;

      return matchTitle || matchCitation || matchCode || matchExplanation || matchExample;
    });
  }, [allRules, selectedCode, searchQuery]);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedIds(new Set(filteredRules.map((r) => r.id)));
  };

  const collapseAll = () => {
    setExpandedIds(new Set());
  };

  // Quick count per code
  const codeCounts = useMemo(() => {
    const counts: Record<string, number> = { "": allRules.length };
    for (const r of allRules) {
      counts[r.code] = (counts[r.code] ?? 0) + 1;
    }
    return counts;
  }, [allRules]);

  return (
    <div className="space-y-8 pb-16">
      {/* Clean Hero Header */}
      <header className="rounded-3xl border border-sky-100 bg-gradient-to-br from-white via-sky-50/40 to-blue-50/30 p-8 shadow-sm md:p-12">
        <div className="max-w-4xl space-y-4">
          <h1 className="text-4xl font-extrabold tracking-tight text-slate-900 sm:text-6xl">
            Labour Law Compliance Rules
          </h1>
          <p className="text-lg leading-relaxed text-slate-800 sm:text-xl">
            Simplifying labour compliance requirements under the four Labour Codes through clear, actionable guidance.
          </p>
        </div>
      </header>

      {/* Filter and Search Bar */}
      <section className="space-y-5">
        {/* Code Filter Pills */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => setSelectedCode("")}
            className={[
              "cursor-pointer rounded-full px-5 py-2.5 text-base font-bold transition-all",
              selectedCode === ""
                ? "bg-slate-900 text-white shadow-sm"
                : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
            ].join(" ")}
          >
            All Rules ({codeCounts[""] ?? 40})
          </button>

          {(["WAGES", "INDUSTRIAL_RELATIONS", "SOCIAL_SECURITY", "OSH"] as LabourCode[]).map((code) => {
            const countVal = codeCounts[code] ?? 0;
            const isSelected = selectedCode === code;
            return (
              <button
                key={code}
                type="button"
                onClick={() => setSelectedCode(code)}
                className={[
                  "cursor-pointer rounded-full px-5 py-2.5 text-base font-bold transition-all",
                  isSelected
                    ? "bg-slate-900 text-white shadow-sm"
                    : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
                ].join(" ")}
              >
                {CODE_SHORT_LABELS[code]}
                <span className="ml-1.5 text-sm opacity-80">({countVal})</span>
              </button>
            );
          })}
        </div>

        {/* Search Bar & Expand/Collapse Controls */}
        <div className="flex flex-col gap-3.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search rules by keyword (e.g. overtime, gratuity, creche, minimum wage, notice)..."
              className="w-full rounded-2xl border border-slate-200 bg-white py-3.5 pl-12 pr-11 text-base text-slate-900 placeholder-slate-400 shadow-sm transition-all focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-100"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                title="Clear search"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2.5 self-end sm:self-auto">
            <button
              type="button"
              onClick={expandAll}
              className="cursor-pointer rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm hover:bg-slate-50"
            >
              Expand All
            </button>
            <button
              type="button"
              onClick={collapseAll}
              className="cursor-pointer rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm hover:bg-slate-50"
            >
              Collapse All
            </button>
          </div>
        </div>
      </section>

      {/* Rules List (Step-Wise) */}
      <section className="space-y-4">
        {rulesQuery.isPending && <SkeletonRows rows={8} columns={2} />}

        {rulesQuery.isError && (
          <ErrorState
            error={rulesQuery.error}
            context="the compliance rules"
            onRetry={() => void rulesQuery.refetch()}
          />
        )}

        {rulesQuery.isSuccess && filteredRules.length === 0 && (
          <EmptyState
            icon={HelpCircle}
            title="No rules matched your search"
            description="Try searching with a different term, or reset the filters above to see all rules."
          />
        )}

        {rulesQuery.isSuccess && filteredRules.length > 0 && (
          <div className="space-y-4">
            {filteredRules.map((rule, idx) => {
              const isExpanded = expandedIds.has(rule.id);
              const stepNumber = String(idx + 1).padStart(2, "0");
              const guide = RULE_GUIDE_DATA[rule.id] as RuleGuideItem | undefined;
              const colorConfig = CODE_COLORS[rule.code] || CODE_COLORS.WAGES;

              // Fallback simple explanation if not in dictionary
              const simpleText =
                guide?.simpleExplanation ||
                rule.message_en ||
                "This statutory rule establishes mandatory compliance criteria under Indian labour codes.";

              return (
                <article
                  key={rule.id}
                  className={[
                    "overflow-hidden rounded-3xl border transition-all duration-200",
                    isExpanded
                      ? "border-sky-300 bg-white shadow-md ring-1 ring-sky-200"
                      : "border-slate-200/90 bg-white hover:border-slate-300 hover:shadow-sm",
                  ].join(" ")}
                >
                  {/* Clickable Header */}
                  <button
                    type="button"
                    onClick={() => toggleExpand(rule.id)}
                    aria-expanded={isExpanded}
                    className="flex w-full cursor-pointer items-center justify-between gap-4 p-5 text-left sm:p-7"
                  >
                    <div className="flex items-center gap-4 sm:gap-6">
                      {/* Number Badge */}
                      <span
                        className={[
                          "flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl text-sm font-black sm:h-14 sm:w-14 sm:text-base",
                          colorConfig.stepBg,
                        ].join(" ")}
                      >
                        {stepNumber}
                      </span>

                      {/* Rule Title & Category */}
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-2">
                          <span
                            className={[
                              "inline-flex items-center rounded-full px-3 py-0.5 text-xs font-bold sm:text-sm",
                              colorConfig.badgeBg,
                              colorConfig.badgeText,
                            ].join(" ")}
                          >
                            {CODE_LABELS[rule.code]}
                          </span>
                        </div>

                        <h2 className="text-lg font-bold text-slate-900 sm:text-2xl">
                          {rule.title}
                        </h2>

                        {!isExpanded && (
                          <p className="line-clamp-2 text-sm leading-relaxed text-slate-700 sm:text-base">
                            {simpleText}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Toggle Indicator Button */}
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="hidden text-sm font-bold text-sky-700 sm:inline-block">
                        {isExpanded ? "Hide Details" : "View Example & Guide"}
                      </span>
                      <div
                        className={[
                          "flex h-9 w-9 items-center justify-center rounded-full transition-colors",
                          isExpanded ? "bg-sky-100 text-sky-800" : "bg-slate-100 text-slate-600 hover:bg-slate-200",
                        ].join(" ")}
                      >
                        {isExpanded ? (
                          <ChevronUp className="h-5 w-5" />
                        ) : (
                          <ChevronDown className="h-5 w-5" />
                        )}
                      </div>
                    </div>
                  </button>

                  {/* Expanded Step Details */}
                  {isExpanded && (
                    <div className="border-t border-slate-100 bg-slate-50/50 p-6 pt-5 sm:p-8 sm:pt-6">
                      <div className="space-y-6">
                        {/* 1. Plain English Explanation */}
                        <div className="rounded-2xl border border-blue-100 bg-blue-50/50 p-6">
                          <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-blue-900">
                            <BookOpen className="h-4.5 w-4.5 text-blue-700" />
                            Plain English Explanation
                          </div>
                          <p className="mt-2.5 text-base leading-relaxed text-slate-800 sm:text-lg">
                            {simpleText}
                          </p>
                        </div>

                        {/* 2. Real-World Practical Example */}
                        {guide && (
                          <div className="space-y-3.5">
                            <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-800">
                              <Lightbulb className="h-4.5 w-4.5 text-amber-600" />
                              Real-World Practical Example
                            </div>

                            {/* Example Context Scenario */}
                            <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm font-medium text-slate-800 sm:text-base">
                              <span className="font-bold text-slate-900">Scenario: </span>
                              {guide.exampleScenario}
                            </div>

                            {/* Compliant vs Violation Comparison */}
                            <div className="grid gap-3.5 sm:grid-cols-2">
                              {/* Compliant Case */}
                              <div className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5">
                                <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-emerald-900">
                                  <CheckCircle2 className="h-4.5 w-4.5 text-emerald-600" />
                                  Compliant Example (Pass)
                                </div>
                                <p className="mt-2.5 text-sm leading-relaxed text-emerald-950 sm:text-base">
                                  {guide.compliantExample}
                                </p>
                              </div>

                              {/* Violation Case */}
                              <div className="rounded-2xl border border-rose-200 bg-rose-50/60 p-5">
                                <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-rose-900">
                                  <ShieldAlert className="h-4.5 w-4.5 text-rose-600" />
                                  Violation Example (Breach)
                                </div>
                                <p className="mt-2.5 text-sm leading-relaxed text-rose-950 sm:text-base">
                                  {guide.violationExample}
                                </p>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* 3. Action Required / How to Comply */}
                        <div className="rounded-2xl border border-slate-200 bg-white p-6">
                          <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-900">
                            <ShieldCheck className="h-4.5 w-4.5 text-emerald-600" />
                            How to Comply (Action Required)
                          </div>
                          {guide?.actionToComply && guide.actionToComply.length > 0 ? (
                            <ul className="mt-3.5 space-y-2.5 text-sm text-slate-800 sm:text-base">
                              {guide.actionToComply.map((step, sIdx) => (
                                <li key={sIdx} className="flex items-start gap-2.5">
                                  <span className="mt-2 block h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
                                  <span>{step}</span>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="mt-2.5 text-sm text-slate-800 sm:text-base">
                              {rule.remediation_en ||
                                "Ensure payroll records, registers, and statutory returns reflect this requirement."}
                            </p>
                          )}
                        </div>

                      </div>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
