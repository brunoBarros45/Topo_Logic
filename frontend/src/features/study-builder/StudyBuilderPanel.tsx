import { Crosshair, Play, Plus, Square, Trash2, Wand2 } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import {
  useCancelJobMutation,
  useJobsQuery,
  useMaterialsQuery,
  useMeshesQuery,
  useSubmitFemMutation,
  useSubmitTopOptMutation,
} from "@/api/queries";
import type {
  DesignZoneType,
  FilterKind,
  OptimizerKind,
  SolverKind,
} from "@/api/types";
import { useJobStream } from "@/api/useJobStream";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { sceneRegistry } from "@/engine/sceneRegistry";
import { useT } from "@/i18n/useT";
import { useStudyBuilderStore, type ActiveStudyMode } from "@/stores/studyBuilderStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";

export function StudyBuilderPanel() {
  const t = useT();
  const {
    activeProjectId,
    activeGeometryId,
    activeMeshId,
    activeJobId,
    setActiveJobId,
    setViewportMode,
    announce,
  } = useWorkspaceStore();

  const s = useStudyBuilderStore();
  const materialsQuery = useMaterialsQuery(s.unitSystem);
  const meshesQuery = useMeshesQuery(activeProjectId);
  const jobsQuery = useJobsQuery(activeProjectId);

  const femMutation = useSubmitFemMutation(activeProjectId);
  const topoptMutation = useSubmitTopOptMutation(activeProjectId);
  const cancelMutation = useCancelJobMutation(activeProjectId);

  const activeMesh = meshesQuery.data?.find((m) => m.id === activeMeshId) ?? null;
  const activeJob = jobsQuery.data?.find((j) => j.id === activeJobId) ?? null;
  const liveStream = useJobStream(
    activeJobId,
    activeProjectId,
    activeJob?.status ?? null,
  );

  // Form local helper states
  const [selectedRegionId, setSelectedRegionId] = useState("");
  const [planeOriginX, setPlaneOriginX] = useState("0");
  const [planeNormX, setPlaneNormX] = useState("1");
  const [planeNormZ, setPlaneNormZ] = useState("0");
  const [forceZ, setForceZ] = useState("-500");
  const [zoneType, setZoneType] = useState<DesignZoneType>("passive_solid");

  const modeId = useId();
  const matId = useId();
  const pickNameId = useId();
  const regSelectId = useId();
  const optId = useId();
  const filterId = useId();
  const solverId = useId();
  const stressSwId = useId();

  const resolvedRegionId =
    s.regions.find((r) => r.id === selectedRegionId)?.id ?? s.regions[0]?.id ?? "";

  const handleLoadCantileverPreset = () => {
    const meshKey = activeMeshId ? `mesh-glb:${activeMeshId}` : null;
    const geomKey = activeGeometryId ? `geom-glb:${activeGeometryId}` : null;
    const res = sceneRegistry.get(meshKey) ?? sceneRegistry.get(geomKey);
    if (res && res.kind === "r3f-mesh") {
      s.loadCantileverPreset(res.boundsMin, res.boundsMax);
      return;
    }
    s.loadCantileverPreset([0, 0, 0], [50, 20, 20]);
  };

  const handleRunStudy = async (e: FormEvent) => {
    e.preventDefault();
    if (!activeProjectId || !activeGeometryId || !activeMeshId || !activeMesh) return;

    const materialPayload = s.useCustomMaterial
      ? {
          name: s.customMaterial.name,
          youngs_modulus: s.customMaterial.youngs_modulus,
          poissons_ratio: s.customMaterial.poissons_ratio,
          yield_strength: s.customMaterial.yield_strength,
          density: s.customMaterial.density,
        }
      : { preset_id: s.materialPresetId };

    const plainRegions = s.regions.map(({ id, name, selector }) => ({
      id,
      name,
      selector,
    }));

    const baseFem = {
      geometry_id: activeGeometryId,
      mesh_id: activeMeshId,
      unit_system: s.unitSystem,
      material: materialPayload,
      regions: plainRegions,
      supports: s.supports,
      load_cases: s.loadCases,
      element_type: activeMesh.element_type,
      solver_kind: s.solverKind,
    };

    if (s.studyMode === "static_fem") {
      const job = await femMutation.mutateAsync(baseFem);
      setActiveJobId(job.id);
      announce(`FEM queued: ${job.id}`);
      return;
    }

    const job = await topoptMutation.mutateAsync({
      ...baseFem,
      target_volume_fraction: s.targetVolumeFraction,
      penalty: s.penalty,
      e_min_ratio: 1e-9,
      filter_kind: s.filterKind,
      filter_radius_ratio: s.filterRadiusRatio,
      optimizer_kind: s.optimizerKind,
      move_limit: s.moveLimit,
      max_iterations: s.maxIterations,
      convergence_tol: 0.01,
      use_continuation: s.useContinuation,
      stress_constraint: s.stressConstraint,
      design_zones: s.designZones,
    });
    setActiveJobId(job.id);
    announce(`TopOpt queued: ${job.id}`);
  };

  const activeError = femMutation.error ?? topoptMutation.error;
  const isRunning =
    activeJob !== null &&
    !["completed", "cancelled", "failed"].includes(
      liveStream.status ?? activeJob.status,
    );

  return (
    <form onSubmit={handleRunStudy} className="space-y-3">
      {/* Study Mode & Solver */}
      <Card className="space-y-2.5">
        <div className="flex items-center justify-between">
          <CardTitle>{t("studyType")}</CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={handleLoadCantileverPreset}
            data-testid="cantilever-preset-btn"
          >
            <Wand2 className="h-3 w-3" aria-hidden="true" />
            <span>Cantilever Preset</span>
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label htmlFor={modeId}>{t("studyType")}</Label>
            <NativeSelect
              id={modeId}
              value={s.studyMode}
              onChange={(e) => s.setStudyMode(e.target.value as ActiveStudyMode)}
            >
              <option value="static_fem">{t("studyFem")}</option>
              <option value="topology_optimization">{t("studyTopOpt")}</option>
            </NativeSelect>
          </div>
          <div>
            <Label htmlFor={solverId}>Solver</Label>
            <NativeSelect
              id={solverId}
              value={s.solverKind}
              onChange={(e) => s.setSolverKind(e.target.value as SolverKind)}
            >
              <option value="auto">Auto (&lt;80k splu / AMG)</option>
              <option value="direct">Direct (splu)</option>
              <option value="pcg_amg">PCG + pyamg</option>
            </NativeSelect>
          </div>
        </div>

        <div>
          <Label htmlFor={matId}>{t("materialPreset")}</Label>
          <NativeSelect
            id={matId}
            value={s.materialPresetId}
            onChange={(e) => s.setMaterialPresetId(e.target.value)}
          >
            {(materialsQuery.data ?? []).map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} (E={m.youngs_modulus} {m.stress_unit})
              </option>
            ))}
          </NativeSelect>
        </div>
      </Card>

      {/* Regions & Flood-Fill */}
      <Card className="space-y-2.5">
        <CardTitle>{t("regionsTitle")}</CardTitle>

        <div className="space-y-2 rounded border border-[var(--border-subtle)] bg-[var(--bg-app)] p-2">
          <Label htmlFor={pickNameId}>{t("pickFloodFill")}</Label>
          <div className="flex gap-1.5">
            <Input
              id={pickNameId}
              value={s.pickingRegionName}
              onChange={(e) => s.setPickingRegionName(e.target.value)}
            />
            <Button
              variant={s.pickingActive ? "default" : "secondary"}
              onClick={() => {
                setViewportMode("setup");
                s.setPickingActive(!s.pickingActive);
              }}
              data-testid="toggle-flood-pick-btn"
            >
              <Crosshair className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{s.pickingActive ? "Picking..." : "Pick"}</span>
            </Button>
          </div>

          <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)]">
            <span>
              {t("creaseAngle")}: {s.creaseAngleDeg}°
            </span>
          </div>
          <Slider
            min={5}
            max={60}
            step={1}
            value={[s.creaseAngleDeg]}
            onValueChange={([val]) => s.setCreaseAngleDeg(val)}
            aria-label={t("creaseAngle")}
          />
        </div>

        <div className="grid grid-cols-4 gap-1.5 items-end">
          <div>
            <Label htmlFor="pl-ox">Plane X</Label>
            <Input
              id="pl-ox"
              type="number"
              value={planeOriginX}
              onChange={(e) => setPlaneOriginX(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="pl-nx">Nx</Label>
            <Input
              id="pl-nx"
              type="number"
              value={planeNormX}
              onChange={(e) => setPlaneNormX(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="pl-nz">Nz</Label>
            <Input
              id="pl-nz"
              type="number"
              value={planeNormZ}
              onChange={(e) => setPlaneNormZ(e.target.value)}
            />
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              const ox = Number(planeOriginX) || 0;
              const nx = Number(planeNormX) || 0;
              const nz = Number(planeNormZ) || 0;
              const id = s.addPlaneRegion(
                `Plane (${ox})`,
                [ox, 0, 0],
                [nx, 0, nz],
                0.05,
              );
              setSelectedRegionId(id);
            }}
          >
            <Plus className="h-3 w-3" aria-hidden="true" />
            <span>Plane</span>
          </Button>
        </div>

        {s.regions.length > 0 && (
          <ul className="space-y-1 max-h-28 overflow-y-auto cae-scroll">
            {s.regions.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between rounded border border-[var(--border-subtle)] bg-[var(--bg-app)] px-2 py-1 text-[11px]"
              >
                <button
                  type="button"
                  onClick={() => s.setHighlightedRegionId(r.id)}
                  className="flex items-center gap-1.5 text-left truncate cursor-pointer"
                >
                  <span
                    className="h-2.5 w-2.5 rounded-full shrink-0"
                    style={{ backgroundColor: r.color }}
                  />
                  <span className="truncate font-medium">{r.name}</span>
                  <span className="text-[var(--text-muted)]">({r.selector.kind})</span>
                </button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5"
                  aria-label={`Remove ${r.name}`}
                  onClick={() => s.removeRegion(r.id)}
                >
                  <Trash2 className="h-3 w-3" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Supports, Loads & Passive Zones */}
      <Card className="space-y-2.5">
        <CardTitle>
          {t("supportsTitle")} & {t("loadsTitle")}
        </CardTitle>

        <div className="space-y-2">
          <div>
            <Label htmlFor={regSelectId}>Target Region</Label>
            <NativeSelect
              id={regSelectId}
              value={resolvedRegionId}
              onChange={(e) => setSelectedRegionId(e.target.value)}
            >
              {s.regions.length === 0 ? (
                <option value="">— No regions —</option>
              ) : (
                s.regions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))
              )}
            </NativeSelect>
          </div>

          <div className="flex gap-1.5">
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
              disabled={!resolvedRegionId}
              onClick={() => s.addSupport(resolvedRegionId)}
            >
              + Fixed Support
            </Button>
            <div className="flex items-center gap-1 flex-1">
              <Input
                type="number"
                value={forceZ}
                aria-label="Force Z"
                onChange={(e) => setForceZ(e.target.value)}
              />
              <Button
                variant="secondary"
                size="sm"
                disabled={!resolvedRegionId}
                onClick={() => {
                  const lcId = s.loadCases[0]?.id ?? "lc-1";
                  s.addLoad(lcId, {
                    kind: "force",
                    region_id: resolvedRegionId,
                    force_vector: [0, 0, Number(forceZ) || -500],
                  });
                }}
              >
                + Fz (N)
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap gap-1">
            {s.supports.map((sup, i) => (
              <Badge key={`${sup.region_id}-${i}`} variant="success">
                <span>Fix: {sup.region_id}</span>
                <button
                  type="button"
                  onClick={() => s.removeSupport(i)}
                  aria-label="Remove support"
                  className="ml-1 hover:text-white cursor-pointer"
                >
                  ×
                </button>
              </Badge>
            ))}
            {s.loadCases.flatMap((lc) =>
              lc.loads.map((ld, i) => (
                <Badge key={`${lc.id}-${i}`} variant="warning">
                  <span>
                    {ld.kind === "force"
                      ? `F[${ld.force_vector.join(",")}]`
                      : `P=${ld.magnitude}`}
                  </span>
                  <button
                    type="button"
                    onClick={() => s.removeLoad(lc.id, i)}
                    aria-label="Remove load"
                    className="ml-1 hover:text-white cursor-pointer"
                  >
                    ×
                  </button>
                </Badge>
              )),
            )}
          </div>
        </div>

        {s.studyMode === "topology_optimization" && (
          <>
            <Separator />
            <div className="space-y-2">
              <div className="flex items-center justify-between text-[11px]">
                <span>{t("targetVolume")}:</span>
                <span className="font-mono-tech font-semibold">
                  {(s.targetVolumeFraction * 100).toFixed(0)}%
                </span>
              </div>
              <Slider
                min={0.15}
                max={0.85}
                step={0.05}
                value={[s.targetVolumeFraction]}
                onValueChange={([v]) => s.setTopOptField("targetVolumeFraction", v)}
                aria-label={t("targetVolume")}
              />

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label htmlFor={optId}>{t("optimizer")}</Label>
                  <NativeSelect
                    id={optId}
                    value={s.optimizerKind}
                    onChange={(e) =>
                      s.setTopOptField("optimizerKind", e.target.value as OptimizerKind)
                    }
                  >
                    <option value="oc">OC (Compliance)</option>
                    <option value="mma">MMA (MIT pyMOTO)</option>
                  </NativeSelect>
                </div>
                <div>
                  <Label htmlFor={filterId}>Filter</Label>
                  <NativeSelect
                    id={filterId}
                    value={s.filterKind}
                    onChange={(e) =>
                      s.setTopOptField("filterKind", e.target.value as FilterKind)
                    }
                  >
                    <option value="cone_density">Cone Filter</option>
                    <option value="heaviside_projection">Cone + Heaviside</option>
                  </NativeSelect>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 items-center">
                <div>
                  <Label htmlFor="max-iters">{t("maxIterations")}</Label>
                  <Input
                    id="max-iters"
                    type="number"
                    min={5}
                    max={250}
                    value={s.maxIterations}
                    onChange={(e) =>
                      s.setTopOptField("maxIterations", Math.max(5, Number(e.target.value) || 20))
                    }
                  />
                </div>
                <div className="flex items-center justify-between pt-4">
                  <Label htmlFor={stressSwId} className="mb-0">
                    P-norm σ
                  </Label>
                  <Switch
                    id={stressSwId}
                    checked={s.stressConstraint.enabled}
                    onCheckedChange={(enabled) => s.setStressConstraint({ enabled })}
                  />
                </div>
              </div>

              {s.stressConstraint.enabled && (
                <div>
                  <Label htmlFor="max-vm">{t("maxVonMises")} (MPa)</Label>
                  <Input
                    id="max-vm"
                    type="number"
                    min={1}
                    value={s.stressConstraint.max_von_mises ?? 180}
                    onChange={(e) =>
                      s.setStressConstraint({
                        max_von_mises: Math.max(1, Number(e.target.value) || 180),
                      })
                    }
                  />
                </div>
              )}

              <div className="flex gap-1.5 items-center pt-1">
                <NativeSelect
                  value={zoneType}
                  onChange={(e) => setZoneType(e.target.value as DesignZoneType)}
                  className="flex-1"
                  aria-label={t("zonesTitle")}
                >
                  <option value="passive_solid">Passive Solid (Keep)</option>
                  <option value="passive_void">Passive Void (Keep-out)</option>
                </NativeSelect>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!resolvedRegionId}
                  onClick={() => s.addDesignZone(resolvedRegionId, zoneType)}
                >
                  + Zone
                </Button>
              </div>
              {s.designZones.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {s.designZones.map((dz, i) => (
                    <Badge key={`${dz.region_id}-${i}`} variant="info">
                      <span>
                        {dz.zone_type === "passive_solid" ? "Solid" : "Void"}: {dz.region_id}
                      </span>
                      <button
                        type="button"
                        onClick={() => s.removeDesignZone(i)}
                        aria-label="Remove design zone"
                        className="ml-1 cursor-pointer"
                      >
                        ×
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </Card>

      {activeError && (
        <div role="alert" className="rounded border border-red-500/40 bg-red-500/10 p-2 text-[11px] text-red-400">
          {activeError.message}
        </div>
      )}

      <div className="flex gap-2">
        <Button
          type="submit"
          className="flex-1"
          disabled={
            !activeMeshId ||
            s.supports.length === 0 ||
            s.loadCases.every((lc) => lc.loads.length === 0) ||
            femMutation.isPending ||
            topoptMutation.isPending
          }
          data-testid="run-study-btn"
        >
          <Play className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{t("runStudy")}</span>
        </Button>

        {isRunning && activeJobId && (
          <Button
            variant="destructive"
            onClick={() => cancelMutation.mutate(activeJobId)}
          >
            <Square className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{t("cancelJob")}</span>
          </Button>
        )}
      </div>

      {activeJob && (
        <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-2.5 text-[11px] space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-mono-tech font-medium">
              {(liveStream.status ?? activeJob.status).toUpperCase()}
            </span>
            <span className="font-mono-tech text-[var(--text-muted)]">
              {Math.round((liveStream.progress || activeJob.progress) * 100)}%
            </span>
          </div>
          <progress
            value={liveStream.progress || activeJob.progress}
            max={1}
            className="h-1.5 w-full overflow-hidden rounded accent-[var(--accent-primary)]"
          />
          <p className="text-[var(--text-muted)] truncate">
            {liveStream.message || activeJob.message}
          </p>
        </div>
      )}
    </form>
  );
}
