import { ChevronDown, ChevronUp, LineChart as LineChartIcon } from "lucide-react";
import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useJobsQuery, useTopOptHistoryQuery } from "@/api/queries";
import type { TopOptIterationPoint } from "@/api/types";
import { useJobStream } from "@/api/useJobStream";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SimulationCompare } from "@/features/analytics/SimulationCompare";
import { useT } from "@/i18n/useT";
import { usePostProcessStore } from "@/stores/postProcessStore";
import { useStudyBuilderStore } from "@/stores/studyBuilderStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";

export interface ConvergenceDrawerProps {
  overridePoints?: TopOptIterationPoint[];
}

export function ConvergenceDrawer({ overridePoints }: ConvergenceDrawerProps) {
  const t = useT();
  const { activeProjectId, activeJobId } = useWorkspaceStore();
  const { drawerOpen, setDrawerOpen } = usePostProcessStore();
  const targetVolFrac = useStudyBuilderStore((s) => s.targetVolumeFraction);

  const [logScale, setLogScale] = useState(false);

  const jobsQuery = useJobsQuery(activeProjectId);
  const activeJob = jobsQuery.data?.find((j) => j.id === activeJobId) ?? null;
  const isTopOpt = activeJob?.study_type === "topology_optimization";
  const isCompletedTopOpt = isTopOpt && activeJob?.status === "completed";

  const stream = useJobStream(
    activeJobId,
    activeProjectId,
    activeJob?.status ?? null,
  );
  const historyQuery = useTopOptHistoryQuery(activeJobId, isCompletedTopOpt);

  const points: TopOptIterationPoint[] =
    overridePoints ??
    (stream.liveIterations.length > 0
      ? stream.liveIterations
      : historyQuery.data?.points ?? []);

  const hasStress = points.some((p) => p.max_von_mises !== null);

  return (
    <section
      aria-label={t("analyticsDrawer")}
      className="border-t border-[var(--border-subtle)] bg-[var(--bg-panel)] shrink-0"
    >
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2 text-xs font-medium">
          <LineChartIcon className="h-3.5 w-3.5 text-[var(--accent-primary)]" aria-hidden="true" />
          <span>{t("analyticsDrawer")}</span>
          {points.length > 0 && (
            <span className="font-mono-tech text-[11px] text-[var(--text-muted)]">
              ({points.length} iters)
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {drawerOpen && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setLogScale((v) => !v)}
            >
              Scale: {logScale ? "Log" : "Linear"}
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-expanded={drawerOpen}
            aria-label={drawerOpen ? "Collapse charts" : "Expand charts"}
            onClick={() => setDrawerOpen(!drawerOpen)}
          >
            {drawerOpen ? (
              <ChevronDown className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronUp className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>
        </div>
      </div>

      {drawerOpen && (
        <div className="p-2.5 h-56 overflow-y-auto cae-scroll">
          <Tabs defaultValue="convergence">
            <TabsList>
              <TabsTrigger value="convergence">TopOpt Convergence</TabsTrigger>
              <TabsTrigger value="compare">{t("compareTab")}</TabsTrigger>
            </TabsList>

            <TabsContent value="convergence" className="mt-2">
              {points.length === 0 ? (
                <div className="flex h-36 items-center justify-center text-xs text-[var(--text-muted)]">
                  Submit or select a TopOpt simulation to inspect compliance, strain energy, and mass evolution.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 h-36">
                  {/* Chart 1: Compliance & Strain Energy */}
                  <div className="min-w-0 rounded border border-[var(--border-subtle)] bg-[var(--bg-app)] p-1.5">
                    <div className="text-[10px] font-medium text-[var(--text-muted)] mb-0.5">
                      {t("chartCompliance")}
                    </div>
                    <ResponsiveContainer width="100%" height={112}>
                      <LineChart data={points}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#253142" />
                        <XAxis dataKey="iteration" tick={{ fontSize: 10 }} />
                        <YAxis
                          scale={logScale ? "log" : "auto"}
                          domain={logScale ? ["auto", "auto"] : [0, "auto"]}
                          tick={{ fontSize: 10 }}
                          width={46}
                        />
                        <Tooltip />
                        <Legend wrapperStyle={{ fontSize: 10 }} />
                        <Line
                          type="monotone"
                          dataKey="compliance"
                          name="Compliance"
                          stroke="#38bdf8"
                          dot={false}
                          strokeWidth={2}
                        />
                        <Line
                          type="monotone"
                          dataKey="strain_energy"
                          name="Strain Energy"
                          stroke="#22c55e"
                          dot={false}
                          strokeWidth={1.5}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Chart 2: Volume Fraction & Remaining Mass */}
                  <div className="min-w-0 rounded border border-[var(--border-subtle)] bg-[var(--bg-app)] p-1.5">
                    <div className="text-[10px] font-medium text-[var(--text-muted)] mb-0.5">
                      {t("chartMassVolume")}
                    </div>
                    <ResponsiveContainer width="100%" height={112}>
                      <LineChart data={points}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#253142" />
                        <XAxis dataKey="iteration" tick={{ fontSize: 10 }} />
                        <YAxis yAxisId="vol" domain={[0, 1]} tick={{ fontSize: 10 }} width={36} />
                        <YAxis
                          yAxisId="mass"
                          orientation="right"
                          tick={{ fontSize: 10 }}
                          width={40}
                        />
                        <Tooltip />
                        <ReferenceLine
                          yAxisId="vol"
                          y={targetVolFrac}
                          stroke="#94a3b8"
                          strokeDasharray="4 4"
                        />
                        <Line
                          yAxisId="vol"
                          type="monotone"
                          dataKey="volume_fraction"
                          name="Vol Frac"
                          stroke="#a855f7"
                          dot={false}
                          strokeWidth={2}
                        />
                        <Line
                          yAxisId="mass"
                          type="monotone"
                          dataKey="remaining_mass_kg"
                          name="Mass (kg)"
                          stroke="#f59e0b"
                          dot={false}
                          strokeWidth={1.5}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Chart 3: Max Density Change & Peak Stress */}
                  <div className="min-w-0 rounded border border-[var(--border-subtle)] bg-[var(--bg-app)] p-1.5">
                    <div className="text-[10px] font-medium text-[var(--text-muted)] mb-0.5">
                      {t("chartDensityStress")}
                    </div>
                    <ResponsiveContainer width="100%" height={112}>
                      <LineChart data={points}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#253142" />
                        <XAxis dataKey="iteration" tick={{ fontSize: 10 }} />
                        <YAxis yAxisId="dx" tick={{ fontSize: 10 }} width={38} />
                        {hasStress && (
                          <YAxis
                            yAxisId="stress"
                            orientation="right"
                            tick={{ fontSize: 10 }}
                            width={42}
                          />
                        )}
                        <Tooltip />
                        <Line
                          yAxisId="dx"
                          type="monotone"
                          dataKey="max_density_change"
                          name="Max Δρ"
                          stroke="#14b8a6"
                          dot={false}
                          strokeWidth={2}
                        />
                        {hasStress && (
                          <Line
                            yAxisId="stress"
                            type="monotone"
                            dataKey="max_von_mises"
                            name="Peak σ_vM"
                            stroke="#ef4444"
                            dot={false}
                            strokeWidth={2}
                          />
                        )}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </TabsContent>

            <TabsContent value="compare" className="mt-2">
              <SimulationCompare />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </section>
  );
}
