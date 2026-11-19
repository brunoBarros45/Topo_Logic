import { CheckCircle2, Eye } from "lucide-react";

import {
  useFemSummaryQuery,
  useJobsQuery,
  useTopOptSummaryQuery,
} from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { useT } from "@/i18n/useT";
import { useWorkspaceStore } from "@/stores/workspaceStore";

export function JobsResultsPanel() {
  const t = useT();
  const { activeProjectId, activeJobId, setActiveJobId, setViewportMode } =
    useWorkspaceStore();

  const jobsQuery = useJobsQuery(activeProjectId);
  const jobs = jobsQuery.data ?? [];
  const activeJob = jobs.find((j) => j.id === activeJobId) ?? null;

  const isCompleted = activeJob?.status === "completed";
  const femQuery = useFemSummaryQuery(
    activeJobId,
    Boolean(isCompleted && activeJob?.study_type === "static_fem"),
  );
  const topoptQuery = useTopOptSummaryQuery(
    activeJobId,
    Boolean(isCompleted && activeJob?.study_type === "topology_optimization"),
  );

  return (
    <div className="space-y-3">
      <Card className="space-y-2">
        <CardTitle>{t("tabResults")}</CardTitle>
        {jobs.length === 0 ? (
          <p className="text-[11px] text-[var(--text-muted)]">No simulation jobs yet.</p>
        ) : (
          <ul className="space-y-1.5 max-h-56 overflow-y-auto cae-scroll">
            {jobs.map((job) => {
              const selected = job.id === activeJobId;
              const badgeVar =
                job.status === "completed"
                  ? "success"
                  : job.status === "failed"
                    ? "destructive"
                    : job.status === "cancelled"
                      ? "warning"
                      : "info";
              return (
                <li
                  key={job.id}
                  className={`rounded border p-2 text-[11px] space-y-1 ${
                    selected
                      ? "border-[var(--accent-primary)] bg-sky-500/10"
                      : "border-[var(--border-subtle)] bg-[var(--bg-app)]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => setActiveJobId(job.id)}
                      className="font-mono-tech font-medium truncate text-left cursor-pointer hover:underline"
                    >
                      {job.study_type === "static_fem" ? "FEM" : "TopOpt"} · {job.id.slice(0, 8)}
                    </button>
                    <Badge variant={badgeVar}>{job.status}</Badge>
                  </div>
                  <div className="flex items-center justify-between text-[var(--text-muted)]">
                    <span className="truncate">{job.message}</span>
                    {job.status === "completed" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setActiveJobId(job.id);
                          setViewportMode("results");
                        }}
                      >
                        <Eye className="h-3 w-3" aria-hidden="true" />
                        <span>View</span>
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {femQuery.data && (
        <Card className="space-y-2 text-[11px]">
          <CardTitle>FEM Summary</CardTitle>
          {femQuery.data.load_case_results.map((lc) => (
            <div
              key={lc.load_case_id}
              className="rounded border border-[var(--border-subtle)] bg-[var(--bg-app)] p-2 space-y-1 font-mono-tech"
            >
              <div className="flex items-center justify-between font-sans font-semibold">
                <span>{lc.load_case_id}</span>
                {lc.equilibrium.is_balanced && (
                  <Badge variant="success">
                    <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                    {t("equilibriumBalanced")}
                  </Badge>
                )}
              </div>
              <div>
                σ_vM max: {lc.von_mises_stats.max_value.toFixed(2)} {lc.von_mises_stats.unit}
              </div>
              <div>
                |u| max: {lc.displacement_stats.max_value.toFixed(4)} {lc.displacement_stats.unit}
              </div>
              <div>Min Safety Factor: {lc.min_safety_factor.toFixed(2)}</div>
            </div>
          ))}
        </Card>
      )}

      {topoptQuery.data && (
        <Card className="space-y-1.5 text-[11px] font-mono-tech">
          <CardTitle>TopOpt Summary</CardTitle>
          <div>Iterations: {topoptQuery.data.iterations_completed}</div>
          <div>Final Compliance: {topoptQuery.data.final_compliance.toFixed(3)}</div>
          <div>
            Final Volume: {(topoptQuery.data.final_volume_fraction * 100).toFixed(1)}%
          </div>
          {topoptQuery.data.weight_savings && (
            <div className="text-emerald-400">
              Saved: {topoptQuery.data.weight_savings.mass_saved_g.toFixed(2)} g (
              {topoptQuery.data.weight_savings.mass_reduction_percent.toFixed(1)}%)
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
