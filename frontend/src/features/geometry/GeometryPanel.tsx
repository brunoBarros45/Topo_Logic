import { AlertTriangle, CheckCircle2, FileUp, ShieldAlert } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type DragEvent } from "react";

import { useGeometriesQuery, useUploadGeometryMutation } from "@/api/queries";
import type { AxisConvention, UnitSystem } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n/useT";
import { useStudyBuilderStore } from "@/stores/studyBuilderStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";

export function GeometryPanel() {
  const t = useT();
  const { activeProjectId, activeGeometryId, setActiveGeometryId, announce } =
    useWorkspaceStore();
  const setStudyUnitSystem = useStudyBuilderStore((s) => s.setUnitSystem);

  const geometriesQuery = useGeometriesQuery(activeProjectId);
  const uploadMutation = useUploadGeometryMutation(activeProjectId);

  const [unitSystem, setUnitSystem] = useState<UnitSystem>("mm_N_MPa");
  const [axisConvention, setAxisConvention] = useState<AxisConvention>("Z_up");
  const [autoRepair, setAutoRepair] = useState(true);
  const [dragging, setDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const unitId = useId();
  const axisId = useId();
  const repairId = useId();
  const geomSelectId = useId();

  const geometries = useMemo(
    () => geometriesQuery.data ?? [],
    [geometriesQuery.data],
  );
  const activeGeometry = geometries.find((g) => g.id === activeGeometryId) ?? null;

  useEffect(() => {
    if (!activeGeometryId && geometries.length > 0) {
      setActiveGeometryId(geometries[0].id);
    }
  }, [activeGeometryId, geometries, setActiveGeometryId]);

  const handleFile = async (file: File | undefined | null) => {
    if (!file || !activeProjectId) return;
    const uploaded = await uploadMutation.mutateAsync({
      file,
      unitSystem,
      axisConvention,
      autoRepair,
    });
    setActiveGeometryId(uploaded.id);
    setStudyUnitSystem(uploaded.unit_system);
    announce(`${t("uploadTitle")}: ${uploaded.filename}`);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    void handleFile(file);
  };

  return (
    <Card className="space-y-3">
      <CardTitle>{t("uploadTitle")}</CardTitle>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label htmlFor={unitId}>{t("unitSystem")}</Label>
          <NativeSelect
            id={unitId}
            value={unitSystem}
            onChange={(e) => setUnitSystem(e.target.value as UnitSystem)}
          >
            <option value="mm_N_MPa">mm / N / MPa</option>
            <option value="m_N_Pa">m / N / Pa</option>
          </NativeSelect>
        </div>

        <div>
          <Label htmlFor={axisId}>{t("axisConvention")}</Label>
          <NativeSelect
            id={axisId}
            value={axisConvention}
            onChange={(e) => setAxisConvention(e.target.value as AxisConvention)}
          >
            <option value="Z_up">+Z Up (CAD)</option>
            <option value="Y_up">+Y Up (Web)</option>
          </NativeSelect>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <Label htmlFor={repairId} className="mb-0">
          {t("autoRepair")}
        </Label>
        <Switch id={repairId} checked={autoRepair} onCheckedChange={setAutoRepair} />
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`rounded-lg border border-dashed p-3 text-center transition-colors ${
          dragging
            ? "border-[var(--accent-primary)] bg-sky-500/10"
            : "border-[var(--border-subtle)] bg-[var(--bg-app)]"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".stl,.obj,.ply,.step,.stp"
          className="visually-hidden"
          aria-label={t("uploadAction")}
          data-testid="geometry-file-input"
          onChange={(e) => {
            void handleFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <FileUp
          className="mx-auto mb-1.5 h-5 w-5 text-[var(--text-muted)]"
          aria-hidden="true"
        />
        <p className="text-[11px] text-[var(--text-muted)] mb-2">{t("uploadHint")}</p>
        <Button
          variant="secondary"
          size="sm"
          disabled={!activeProjectId || uploadMutation.isPending}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploadMutation.isPending ? "..." : t("uploadAction")}
        </Button>
      </div>

      {uploadMutation.isError && (
        <div role="alert" className="rounded border border-red-500/40 bg-red-500/10 p-2 text-[11px] text-red-400">
          {uploadMutation.error.message}
        </div>
      )}

      {geometries.length > 0 && (
        <div>
          <Label htmlFor={geomSelectId}>CAD / STL Assets</Label>
          <NativeSelect
            id={geomSelectId}
            value={activeGeometryId ?? ""}
            onChange={(e) => setActiveGeometryId(e.target.value || null)}
          >
            {geometries.map((g) => (
              <option key={g.id} value={g.id}>
                {g.filename} ({g.format.toUpperCase()} · {g.unit_system})
              </option>
            ))}
          </NativeSelect>
        </div>
      )}

      {activeGeometry && (
        <div className="space-y-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-app)] p-2.5 text-[11px]">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium truncate">{activeGeometry.filename}</span>
            {activeGeometry.diagnostics.is_watertight ? (
              <Badge variant="success">
                <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                {t("watertight")}
              </Badge>
            ) : (
              <Badge variant="warning">
                <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                {t("openMesh")}
              </Badge>
            )}
          </div>

          <div className="grid grid-cols-2 gap-1.5 font-mono-tech text-[var(--text-muted)]">
            <span>Tris: {activeGeometry.diagnostics.triangle_count.toLocaleString()}</span>
            <span>Vol: {activeGeometry.diagnostics.volume.toFixed(1)}</span>
            <span>
              ΔX:{" "}
              {(
                activeGeometry.diagnostics.bounds.max_corner[0] -
                activeGeometry.diagnostics.bounds.min_corner[0]
              ).toFixed(1)}
            </span>
            <span>Diag: {activeGeometry.diagnostics.bounds.diagonal.toFixed(1)}</span>
          </div>

          {activeGeometry.diagnostics.scale_guard.is_suspicious && (
            <div
              role="status"
              className="rounded border border-amber-500/50 bg-amber-500/10 p-2 text-amber-300 space-y-1"
            >
              <div className="flex items-center gap-1.5 font-semibold">
                <ShieldAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>{t("scaleWarningTitle")}</span>
              </div>
              <p className="text-[11px] leading-snug">
                {activeGeometry.diagnostics.scale_guard.message}
              </p>
              {activeGeometry.diagnostics.scale_guard.suggested_unit_system && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    const sug = activeGeometry.diagnostics.scale_guard.suggested_unit_system!;
                    setUnitSystem(sug);
                    setStudyUnitSystem(sug);
                  }}
                >
                  {activeGeometry.diagnostics.scale_guard.suggested_unit_system}
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
