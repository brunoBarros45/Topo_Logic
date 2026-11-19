import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  useFemSummaryQuery,
  useJobsQuery,
  useTopOptHistoryQuery,
  useTopOptSummaryQuery,
} from "@/api/queries";
import { NativeSelect } from "@/components/ui/select";
import { useT } from "@/i18n/useT";
import { useWorkspaceStore } from "@/stores/workspaceStore";

export function SimulationCompare() {
  const t = useT();
  const { activeProjectId, activeJobId, compareJobId, setCompareJobId } =
    useWorkspaceStore();

  const jobsQuery = useJobsQuery(activeProjectId);
  const completedJobs = (jobsQuery.data ?? []).filter(
    (j) => j.status === "completed",
  );
  const activeJob = completedJobs.find((j) => j.id === activeJobId) ?? null;
  const compareJob = completedJobs.find((j) => j.id === compareJobId) ?? null;

  const topoptHistA = useTopOptHistoryQuery(
    activeJobId,
    activeJob?.study_type === "topology_optimization",
  );
  const topoptHistB = useTopOptHistoryQuery(
    compareJobId,
    compareJob?.study_type === "topology_optimization",
  );

  const femSumA = useFemSummaryQuery(
    activeJobId,
    activeJob?.study_type === "static_fem",
  );
  const femSumB = useFemSummaryQuery(
    compareJobId,
    compareJob?.study_type === "static_fem",
  );
  const topoptSumA = useTopOptSummaryQuery(
    activeJobId,
    activeJob?.study_type === "topology_optimization",
  );
  const topoptSumB = useTopOptSummaryQuery(
    compareJobId,
    compareJob?.study_type === "topology_optimization",
  );

  // Merge iteration points for overlay chart
  const mergedPoints = (() => {
    const map = new Map<
      number,
      { iteration: number; complianceA?: number; complianceB?: number }
    >();
    for (const pt of topoptHistA.data?.points ?? []) {
      map.set(pt.iteration, { iteration: pt.iteration, complianceA: pt.compliance });
    }
    for (const pt of topoptHistB.data?.points ?? []) {
      const prev = map.get(pt.iteration) ?? { iteration: pt.iteration };
      map.set(pt.iteration, { ...prev, complianceB: pt.compliance });
    }
    return Array.from(map.values()).sort((a, b) => a.iteration - b.iteration);
  })();

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 h-full">
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-medium text-[var(--text-muted)]">
            {t("selectCompareJob")}
          </span>
          <NativeSelect
            value={compareJobId ?? ""}
            aria-label={t("selectCompareJob")}
            onChange={(e) => setCompareJobId(e.target.value || null)}
            className="w-56"
          >
            <option value="">— Select completed job —</option>
            {completedJobs
              .filter((j) => j.id !== activeJobId)
              .map((j) => (
                <option key={j.id} value={j.id}>
                  {j.study_type === "static_fem" ? "FEM" : "TopOpt"} · {j.id.slice(0, 8)}
                </option>
              ))}
          </NativeSelect>
        </div>

        <table className="w-full text-[11px] border-collapse border border-[var(--border-subtle)] rounded">
          <caption className="visually-hidden">{t("compareTab")}</caption>
          <thead>
            <tr className="bg-[var(--bg-elevated)] text-left text-[var(--text-muted)]">
              <th scope="col" className="p-1.5 border border-[var(--border-subtle)]">
                Metric
              </th>
              <th scope="col" className="p-1.5 border border-[var(--border-subtle)] font-mono-tech">
                Sim A ({activeJobId?.slice(0, 6) ?? "—"})
              </th>
              <th scope="col" className="p-1.5 border border-[var(--border-subtle)] font-mono-tech">
                Sim B ({compareJobId?.slice(0, 6) ?? "—"})
              </th>
            </tr>
          </thead>
          <tbody className="font-mono-tech">
            <tr>
              <th scope="row" className="p-1.5 border border-[var(--border-subtle)] font-sans text-left">
                Compliance
              </th>
              <td className="p-1.5 border border-[var(--border-subtle)]">
                {topoptSumA.data?.final_compliance.toFixed(2) ??
                  femSumA.data?.load_case_results[0]?.compliance.toFixed(2) ??
                  "—"}
              </td>
              <td className="p-1.5 border border-[var(--border-subtle)]">
                {topoptSumB.data?.final_compliance.toFixed(2) ??
                  femSumB.data?.load_case_results[0]?.compliance.toFixed(2) ??
                  "—"}
              </td>
            </tr>
            <tr>
              <th scope="row" className="p-1.5 border border-[var(--border-subtle)] font-sans text-left">
                {t("massSaved")}
              </th>
              <td className="p-1.5 border border-[var(--border-subtle)]">
                {topoptSumA.data?.weight_savings
                  ? `${topoptSumA.data.weight_savings.mass_saved_g.toFixed(1)} g (-${topoptSumA.data.weight_savings.mass_reduction_percent.toFixed(1)}%)`
                  : "—"}
              </td>
              <td className="p-1.5 border border-[var(--border-subtle)]">
                {topoptSumB.data?.weight_savings
                  ? `${topoptSumB.data.weight_savings.mass_saved_g.toFixed(1)} g (-${topoptSumB.data.weight_savings.mass_reduction_percent.toFixed(1)}%)`
                  : "—"}
              </td>
            </tr>
            <tr>
              <th scope="row" className="p-1.5 border border-[var(--border-subtle)] font-sans text-left">
                Peak σ / Min SF
              </th>
              <td className="p-1.5 border border-[var(--border-subtle)]">
                {femSumA.data?.load_case_results[0]
                  ? `${femSumA.data.load_case_results[0].von_mises_stats.max_value.toFixed(1)} / SF ${femSumA.data.load_case_results[0].min_safety_factor.toFixed(2)}`
                  : "—"}
              </td>
              <td className="p-1.5 border border-[var(--border-subtle)]">
                {femSumB.data?.load_case_results[0]
                  ? `${femSumB.data.load_case_results[0].von_mises_stats.max_value.toFixed(1)} / SF ${femSumB.data.load_case_results[0].min_safety_factor.toFixed(2)}`
                  : "—"}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="h-44 min-w-0 rounded border border-[var(--border-subtle)] bg-[var(--bg-app)] p-2">
        {mergedPoints.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={mergedPoints}>
              <CartesianGrid strokeDasharray="3 3" stroke="#253142" />
              <XAxis dataKey="iteration" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} width={48} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line
                type="monotone"
                dataKey="complianceA"
                name="Sim A Compliance"
                stroke="#38bdf8"
                dot={false}
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="complianceB"
                name="Sim B Compliance"
                stroke="#f59e0b"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-[11px] text-[var(--text-muted)]">
            Select TopOpt jobs to overlay convergence curves.
          </div>
        )}
      </div>
    </div>
  );
}
