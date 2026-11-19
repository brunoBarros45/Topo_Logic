import { Columns2, Eye, Layers, Link2, RotateCcw } from "lucide-react";
import { useEffect } from "react";

import { apiClient } from "@/api/apiClient";
import {
  useFemSummaryQuery,
  useGeometriesQuery,
  useJobsQuery,
  useLoadFemVtpResource,
  useLoadGlbResource,
  useLoadTopOptVtiResource,
  useTopOptSummaryQuery,
} from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import type { ColormapName } from "@/engine/colormaps";
import { sceneRegistry } from "@/engine/sceneRegistry";
import { useT } from "@/i18n/useT";
import { ColorbarLegend } from "@/features/viewport/ColorbarLegend";
import { ExportToolbar } from "@/features/viewport/ExportToolbar";
import { R3fSetupViewport } from "@/features/viewport/R3fSetupViewport";
import { VtkResultsViewport } from "@/features/viewport/VtkResultsViewport";
import {
  usePostProcessStore,
  type ScalarFieldName,
  type TopOptViewMode,
} from "@/stores/postProcessStore";
import {
  useWorkspaceStore,
  type SplitPreset,
  type ViewportMode,
} from "@/stores/workspaceStore";

export function ViewportHost() {
  const t = useT();
  const {
    activeProjectId,
    activeGeometryId,
    activeMeshId,
    activeJobId,
    compareJobId,
    viewportMode,
    splitPreset,
    cameraSyncEnabled,
    setViewportMode,
    setSplitPreset,
    setCameraSyncEnabled,
  } = useWorkspaceStore();

  const pp = usePostProcessStore();

  const geometriesQuery = useGeometriesQuery(activeProjectId);
  const jobsQuery = useJobsQuery(activeProjectId);
  const activeGeometry =
    geometriesQuery.data?.find((g) => g.id === activeGeometryId) ?? null;
  const activeJob = jobsQuery.data?.find((j) => j.id === activeJobId) ?? null;
  const compareJob = jobsQuery.data?.find((j) => j.id === compareJobId) ?? null;

  const isCompleted = activeJob?.status === "completed";
  const isFemCompleted = isCompleted && activeJob?.study_type === "static_fem";
  const isTopOptCompleted =
    isCompleted && activeJob?.study_type === "topology_optimization";

  const femSummaryQuery = useFemSummaryQuery(activeJobId, isFemCompleted);
  const topoptSummaryQuery = useTopOptSummaryQuery(activeJobId, isTopOptCompleted);

  useEffect(() => {
    const lcs = femSummaryQuery.data?.load_case_results ?? [];
    if (lcs.length > 0 && (!pp.activeLoadCaseId || !lcs.some((c) => c.load_case_id === pp.activeLoadCaseId))) {
      pp.setActiveLoadCaseId(lcs[0].load_case_id);
    }
  }, [femSummaryQuery.data, pp]);

  // Setup GLB (active meshed surface preferred, else uploaded repaired geometry)
  const setupKey = activeMeshId
    ? `mesh-glb:${activeMeshId}`
    : activeGeometryId
      ? `geom-glb:${activeGeometryId}`
      : null;

  useLoadGlbResource({
    key: setupKey,
    fetcher: activeMeshId
      ? () => apiClient.fetchMeshSurfaceGlb(activeMeshId)
      : activeGeometryId
        ? () => apiClient.fetchGeometryPreviewGlb(activeGeometryId)
        : null,
    enabled: Boolean(setupKey),
  });

  // TopOpt reconstructed GLB (when user inspects CAD reconstruction or in Setup mode)
  const reconstructedGlbKey = isTopOptCompleted && activeJobId
    ? `topopt-glb:${activeJobId}`
    : null;
  useLoadGlbResource({
    key: reconstructedGlbKey,
    fetcher: activeJobId
      ? () => apiClient.fetchTopOptReconstructedGlb(activeJobId)
      : null,
    enabled: Boolean(
      reconstructedGlbKey && pp.topOptViewMode === "reconstructed_glb",
    ),
  });

  // Active FEM .vtp & TopOpt .vti
  useLoadFemVtpResource(activeJobId, pp.activeLoadCaseId, isFemCompleted);
  useLoadTopOptVtiResource(activeJobId, isTopOptCompleted);

  // Compare job FEM .vtp or TopOpt .vti
  const compareIsFem =
    compareJob?.status === "completed" && compareJob.study_type === "static_fem";
  const compareIsTopOpt =
    compareJob?.status === "completed" &&
    compareJob.study_type === "topology_optimization";
  const compareFemSummary = useFemSummaryQuery(compareJobId, Boolean(compareIsFem));
  const compareLcId =
    compareFemSummary.data?.load_case_results[0]?.load_case_id ?? pp.activeLoadCaseId;

  useLoadFemVtpResource(
    compareJobId,
    compareLcId,
    Boolean(compareIsFem && viewportMode === "split" && splitPreset === "job_vs_job"),
  );
  useLoadTopOptVtiResource(
    compareJobId,
    Boolean(compareIsTopOpt && viewportMode === "split" && splitPreset === "job_vs_job"),
  );

  const resultsKey = isFemCompleted && activeJobId && pp.activeLoadCaseId
    ? `fem-vtp:${activeJobId}:${pp.activeLoadCaseId}`
    : isTopOptCompleted && activeJobId
      ? pp.topOptViewMode === "reconstructed_glb"
        ? reconstructedGlbKey
        : `topopt-vti:${activeJobId}`
      : null;

  const compareResultsKey = compareIsFem && compareJobId && compareLcId
    ? `fem-vtp:${compareJobId}:${compareLcId}`
    : compareIsTopOpt && compareJobId
      ? `topopt-vti:${compareJobId}`
      : null;

  const femRes = resultsKey ? sceneRegistry.get(resultsKey) : undefined;
  const activeLcStats = femSummaryQuery.data?.load_case_results.find(
    (c) => c.load_case_id === pp.activeLoadCaseId,
  );
  const unitLabel =
    pp.scalarField === "von_mises"
      ? activeLcStats?.von_mises_stats.unit ?? "MPa"
      : pp.scalarField === "displacement_magnitude"
        ? activeLcStats?.displacement_stats.unit ?? "mm"
        : "SF";

  const activeRange: [number, number] =
    femRes?.kind === "vtk-fem"
      ? femRes.fieldRanges[pp.scalarField] ?? [0, 1]
      : [0, 1];
  const legendMin = pp.autoRange ? activeRange[0] : pp.manualMin;
  const legendMax = pp.autoRange ? activeRange[1] : pp.manualMax;

  const axisConvention = activeGeometry?.axis_convention ?? "Z_up";

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-[#090d13]">
      {/* Viewport Mode Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-panel)] px-3 py-1.5">
        <div className="flex items-center gap-1.5" role="group" aria-label="Viewport Mode">
          {(
            [
              ["setup", t("viewSetup"), Layers],
              ["results", t("viewResults"), Eye],
              ["split", t("viewSplit"), Columns2],
            ] as const
          ).map(([mode, label, Icon]) => (
            <Button
              key={mode}
              variant={viewportMode === mode ? "default" : "ghost"}
              size="sm"
              onClick={() => setViewportMode(mode as ViewportMode)}
              data-testid={`viewport-mode-${mode}`}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{label}</span>
            </Button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          {viewportMode === "split" && (
            <NativeSelect
              value={splitPreset}
              aria-label="Split comparison mode"
              onChange={(e) => setSplitPreset(e.target.value as SplitPreset)}
              className="w-44"
            >
              <option value="setup_vs_results">Setup vs Results</option>
              <option value="job_vs_job">Active vs Compare Job</option>
            </NativeSelect>
          )}

          <div className="flex items-center gap-1.5 text-[11px]">
            <Link2 className="h-3.5 w-3.5 text-[var(--text-muted)]" aria-hidden="true" />
            <Label htmlFor="cam-sync-sw" className="mb-0">
              {t("syncCamera")}
            </Label>
            <Switch
              id="cam-sync-sw"
              checked={cameraSyncEnabled}
              onCheckedChange={setCameraSyncEnabled}
            />
          </div>

          <ExportToolbar
            jobId={activeJobId}
            studyType={activeJob?.study_type ?? null}
            loadCaseId={pp.activeLoadCaseId}
            isCompleted={isCompleted}
          />
        </div>
      </div>

      {/* Main 3D Canvas Area */}
      <div className="relative flex-1 overflow-hidden">
        {viewportMode === "setup" && (
          <R3fSetupViewport
            viewerId="r3f-main"
            resourceKey={setupKey}
            axisConvention={axisConvention}
            statusLabel={
              activeGeometry
                ? `${activeGeometry.filename} (${axisConvention})`
                : null
            }
          />
        )}

        {viewportMode === "results" && (
          <>
            {isTopOptCompleted && pp.topOptViewMode === "reconstructed_glb" ? (
              <R3fSetupViewport
                viewerId="r3f-reconstructed"
                resourceKey={reconstructedGlbKey}
                axisConvention={axisConvention}
                statusLabel="Reconstructed Watertight CAD (.glb)"
              />
            ) : (
              <VtkResultsViewport
                viewerId="vtk-main"
                resourceKey={resultsKey}
                unitLabel={unitLabel}
                statusLabel={
                  isFemCompleted
                    ? `${t("probeHint")} · LC: ${pp.activeLoadCaseId ?? ""}`
                    : isTopOptCompleted
                      ? `VTK.js ImageMarchingCubes · ρ ≥ ${pp.densityThreshold.toFixed(2)}`
                      : "Run FEM or TopOpt study to visualize results in VTK.js"
                }
              />
            )}
            {isFemCompleted && (
              <ColorbarLegend minVal={legendMin} maxVal={legendMax} unit={unitLabel} />
            )}
          </>
        )}

        {viewportMode === "split" && (
          <div className="grid h-full w-full grid-cols-2 divide-x divide-[var(--border-subtle)]">
            {splitPreset === "setup_vs_results" ? (
              <>
                <R3fSetupViewport
                  viewerId="r3f-split-left"
                  resourceKey={setupKey}
                  axisConvention={axisConvention}
                  statusLabel="Pre-Process (R3F)"
                />
                <div className="relative h-full w-full">
                  <VtkResultsViewport
                    viewerId="vtk-split-right"
                    resourceKey={resultsKey}
                    unitLabel={unitLabel}
                    statusLabel="Results (VTK.js)"
                  />
                  {isFemCompleted && (
                    <ColorbarLegend minVal={legendMin} maxVal={legendMax} unit={unitLabel} />
                  )}
                </div>
              </>
            ) : (
              <>
                <VtkResultsViewport
                  viewerId="vtk-split-a"
                  resourceKey={resultsKey}
                  unitLabel={unitLabel}
                  statusLabel={`Sim A: ${activeJobId?.slice(0, 8) ?? "—"}`}
                />
                <VtkResultsViewport
                  viewerId="vtk-split-b"
                  resourceKey={compareResultsKey}
                  unitLabel={unitLabel}
                  statusLabel={`Sim B: ${compareJobId?.slice(0, 8) ?? "Select Compare Job"}`}
                />
              </>
            )}
          </div>
        )}

        {/* Contextual Post-Processing Floating Inspector */}
        {viewportMode !== "setup" && isCompleted && (
          <div className="absolute top-12 left-3 z-20 w-60 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-panel)]/92 p-2.5 text-[11px] shadow-xl backdrop-blur space-y-2.5">
            {isFemCompleted && femSummaryQuery.data && (
              <>
                <div>
                  <Label htmlFor="pp-lc">Load Case</Label>
                  <NativeSelect
                    id="pp-lc"
                    value={pp.activeLoadCaseId ?? ""}
                    onChange={(e) => pp.setActiveLoadCaseId(e.target.value)}
                  >
                    {femSummaryQuery.data.load_case_results.map((c) => (
                      <option key={c.load_case_id} value={c.load_case_id}>
                        {c.load_case_id} (σmax={c.von_mises_stats.max_value.toFixed(1)})
                      </option>
                    ))}
                  </NativeSelect>
                </div>

                <div>
                  <Label htmlFor="pp-field">{t("scalarField")}</Label>
                  <NativeSelect
                    id="pp-field"
                    value={pp.scalarField}
                    onChange={(e) => pp.setScalarField(e.target.value as ScalarFieldName)}
                  >
                    <option value="von_mises">{t("fieldVonMises")}</option>
                    <option value="displacement_magnitude">{t("fieldDispMag")}</option>
                    <option value="safety_factor">{t("fieldSafetyFactor")}</option>
                  </NativeSelect>
                </div>

                <div>
                  <Label htmlFor="pp-cmap">{t("colormap")}</Label>
                  <NativeSelect
                    id="pp-cmap"
                    value={pp.colormap}
                    onChange={(e) => pp.setColormap(e.target.value as ColormapName)}
                  >
                    <option value="turbo">Turbo</option>
                    <option value="viridis">Viridis</option>
                    <option value="coolwarm">Cool-to-Warm</option>
                    <option value="plasma">Plasma</option>
                  </NativeSelect>
                </div>

                <div>
                  <div className="flex justify-between mb-0.5">
                    <span>{t("deformScale")}:</span>
                    <span className="font-mono-tech">{pp.deformScale.toFixed(0)}×</span>
                  </div>
                  <Slider
                    min={0}
                    max={50}
                    step={1}
                    value={[pp.deformScale]}
                    onValueChange={([v]) => pp.setDeformScale(v)}
                    aria-label={t("deformScale")}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <Label htmlFor="pp-anim" className="mb-0">
                    {t("animateDeform")}
                  </Label>
                  <Switch
                    id="pp-anim"
                    checked={pp.animateDeform}
                    onCheckedChange={pp.setAnimateDeform}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <Label htmlFor="pp-ghost" className="mb-0">
                    {t("ghostWireframe")}
                  </Label>
                  <Switch
                    id="pp-ghost"
                    checked={pp.showGhostWireframe}
                    onCheckedChange={pp.setShowGhostWireframe}
                  />
                </div>
              </>
            )}

            {isTopOptCompleted && (
              <>
                <div>
                  <Label htmlFor="topopt-vmode">TopOpt View</Label>
                  <NativeSelect
                    id="topopt-vmode"
                    value={pp.topOptViewMode}
                    onChange={(e) => pp.setTopOptViewMode(e.target.value as TopOptViewMode)}
                  >
                    <option value="vti_isosurface">VTK.js Voxel Isosurface (.vti)</option>
                    <option value="reconstructed_glb">Taubin Watertight CAD (.glb)</option>
                  </NativeSelect>
                </div>

                {pp.topOptViewMode === "vti_isosurface" && (
                  <div>
                    <div className="flex justify-between mb-0.5">
                      <span>{t("densityThreshold")}:</span>
                      <span className="font-mono-tech">{pp.densityThreshold.toFixed(2)}</span>
                    </div>
                    <Slider
                      min={0.1}
                      max={0.9}
                      step={0.05}
                      value={[pp.densityThreshold]}
                      onValueChange={([v]) => pp.setDensityThreshold(v)}
                      aria-label={t("densityThreshold")}
                    />
                  </div>
                )}

                {topoptSummaryQuery.data?.weight_savings && (
                  <div className="rounded border border-emerald-500/40 bg-emerald-500/10 p-2 space-y-0.5 text-emerald-300">
                    <div className="font-semibold">
                      {t("massSaved")}:{" "}
                      {topoptSummaryQuery.data.weight_savings.mass_saved_g.toFixed(1)} g
                    </div>
                    <div className="font-mono-tech">
                      −{topoptSummaryQuery.data.weight_savings.mass_reduction_percent.toFixed(1)}%
                      ({topoptSummaryQuery.data.weight_savings.optimized_mass_kg.toFixed(3)} kg)
                    </div>
                  </div>
                )}
              </>
            )}

            {/* Interactive XYZ Section Clipping */}
            <div className="border-t border-[var(--border-subtle)] pt-2 space-y-1.5">
              <div className="flex items-center justify-between font-medium text-[var(--text-muted)]">
                <span>{t("clipPlanes")}</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5"
                  aria-label="Reset clipping"
                  onClick={() => {
                    pp.setClipAxis("clipX", { enabled: false, ratio: 0.5 });
                    pp.setClipAxis("clipY", { enabled: false, ratio: 0.5 });
                    pp.setClipAxis("clipZ", { enabled: false, ratio: 0.5 });
                  }}
                >
                  <RotateCcw className="h-3 w-3" aria-hidden="true" />
                </Button>
              </div>
              {(["clipX", "clipY", "clipZ"] as const).map((axisKey) => {
                const state = pp[axisKey];
                const label = axisKey.replace("clip", "");
                return (
                  <div key={axisKey} className="flex items-center gap-2">
                    <Switch
                      checked={state.enabled}
                      onCheckedChange={(enabled) => pp.setClipAxis(axisKey, { enabled })}
                      aria-label={`Clip ${label}`}
                    />
                    <span className="w-3 font-mono-tech">{label}</span>
                    <Slider
                      disabled={!state.enabled}
                      min={0.05}
                      max={0.95}
                      step={0.05}
                      value={[state.ratio]}
                      onValueChange={([ratio]) => pp.setClipAxis(axisKey, { ratio })}
                      aria-label={`Clip ${label} ratio`}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
