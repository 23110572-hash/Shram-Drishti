import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, MapPin, ShieldCheck, Users } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { count, date } from "@/lib/format";
import type { WorklistItem } from "@/lib/types";
import { CompletenessBar } from "@/pages/EstablishmentsPage";
import { Badge, RiskBadge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/State";

export function WorklistPage() {
  const { user } = useAuth();

  const worklist = useQuery({
    queryKey: ["worklist"],
    queryFn: () => api.get<WorklistItem[]>("/establishments/worklist?limit=50"),
    enabled: Boolean(user),
  });

  const items = worklist.data ?? [];

  if (!user) {
    return (
      <div className="rounded-3xl border border-sky-200/90 bg-white/95 shadow-sm backdrop-blur-xl">
        <EmptyState
          icon={ShieldCheck}
          title="Sign in to view the worklist"
          description="The inspection worklist is available to Inspector-cum-Facilitators and administrators."
          action={
            <Link
              to="/profile"
              className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-7 py-3 text-sm font-bold text-white shadow-md transition-colors hover:bg-slate-800"
            >
              Open Profile
              <ArrowRight className="h-4 w-4" />
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-950 sm:text-5xl">
          Inspection worklist
        </h1>
      </header>

      <div className="overflow-hidden rounded-3xl border border-sky-200/90 bg-white/95 shadow-sm backdrop-blur-xl">
        {worklist.isPending && <SkeletonRows rows={6} columns={5} />}

        {worklist.isError && (
          <ErrorState
            error={worklist.error}
            context="the worklist"
            onRetry={() => void worklist.refetch()}
          />
        )}

        {worklist.isSuccess && items.length === 0 && (
          <EmptyState
            icon={ShieldCheck}
            tone="good"
            title="Nothing queued for inspection"
            description="No establishment within your jurisdiction currently meets the threshold for a prioritised visit. Establishments appear here as filings are assessed."
          />
        )}

        {worklist.isSuccess && items.length > 0 && (
          <ol className="divide-y divide-slate-100">
            {items.map((item, index) => (
              <li key={item.establishment.id}>
                <Link
                  to={`/findings?establishment_id=${item.establishment.id}`}
                  className="flex items-start gap-5 px-6 py-5 transition-colors hover:bg-sky-50/50"
                >
                  {/* Rank */}
                  <div className="flex w-10 shrink-0 flex-col items-center pt-0.5">
                    <span className="font-mono text-sm font-black text-slate-400">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                  </div>

                  {/* Priority dial */}
                  <div className="w-16 shrink-0 text-center">
                    <span
                      className={[
                        "inline-flex h-12 w-12 items-center justify-center rounded-2xl border-2 font-mono text-sm font-black",
                        item.priority >= 85
                          ? "border-rose-300 bg-rose-50 text-rose-900"
                          : item.priority >= 70
                            ? "border-orange-300 bg-orange-50 text-orange-900"
                            : item.priority >= 50
                              ? "border-amber-300 bg-amber-50 text-amber-900"
                              : "border-slate-300 bg-slate-50 text-slate-700",
                      ].join(" ")}
                    >
                      {item.priority}
                    </span>
                    <p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      Priority
                    </p>
                  </div>

                  {/* Establishment */}
                  <div className="min-w-0 flex-1 space-y-2">
                    <p className="text-base font-bold text-slate-900">
                      {item.establishment.name}
                    </p>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
                      <span className="inline-flex items-center gap-1.5">
                        <MapPin aria-hidden="true" className="h-3.5 w-3.5" />
                        {item.establishment.state_code}
                        {item.establishment.district && ` · ${item.establishment.district}`}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <Users aria-hidden="true" className="h-3.5 w-3.5" />
                        {count(item.establishment.worker_count)} workers
                      </span>
                      {item.establishment.sector && (
                        <span>{item.establishment.sector}</span>
                      )}
                      <span>
                        last assessed{" "}
                        {item.establishment.last_evaluated_at
                          ? date(item.establishment.last_evaluated_at)
                          : "never"}
                      </span>
                    </div>

                    <p className="text-sm font-semibold text-slate-700">
                      {item.reason}
                    </p>
                  </div>

                  {/* Position */}
                  <div className="hidden w-40 shrink-0 space-y-2 text-right sm:block">
                    {item.establishment.risk_band ? (
                      <RiskBadge
                        band={item.establishment.risk_band}
                        score={item.establishment.latest_score}
                      />
                    ) : (
                      <Badge tone="neutral">Not assessed</Badge>
                    )}

                    {item.establishment.data_completeness !== null && (
                      <div className="flex justify-end">
                        <CompletenessBar
                          value={item.establishment.data_completeness}
                        />
                      </div>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
