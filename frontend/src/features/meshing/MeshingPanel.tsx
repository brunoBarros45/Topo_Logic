import { Box } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";

import {
  useGenerateMeshMutation,
  useGeometriesQuery,
  useMeshesQuery,
} from "@/api/queries";
import type { ElementType } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { useT } from "@/i18n/useT";
import { useWorkspaceStore } from "@/stores/workspaceStore";

export function MeshingPanel() {
  const t = useT();
  const { activeProjectId, activeGeometryId, activeMeshId, setActiveMeshId, announce } =
    useWorkspaceStore();

  const geometriesQuery = useGeometriesQuery(activeProjectId);
  const meshesQuery = useMeshesQuery(activeProjectId);
  const generateMutation = useGenerateMeshMutation(activeProjectId);

  const activeGeometry =
    geometriesQuery.data?.find((g) => g.id === activeGeometryId) ?? null;

  const [elementType, setElementType] = useState<ElementType>("H8");
  const [elementSize, setElementSize] = useState("5");

  const elemTypeId = useId();
  const elemSizeId = useId();
  const meshSelectId = useId();

  useEffect(() => {
    if (!activeGeometry) return;
    const minExtent = Math.min(
      activeGeometry.diagnostics.bounds.max_corner[0] -
        activeGeometry.diagnostics.bounds.min_corner[0],
      activeGeometry.diagnostics.bounds.max_corner[1] -
        activeGeometry.diagnostics.bounds.min_corner[1],
      activeGeometry.diagnostics.bounds.max_corner[2] -
        activeGeometry.diagnostics.bounds.min_corner[2],
    );
    const suggested = Math.max(0.5, Number((minExtent / 4).toPrecision(2)));
    setElementSize(String(suggested));
  }, [activeGeometry]);

  const meshes = (meshesQuery.data ?? []).filter(
    (m) => !activeGeometryId || m.geometry_id === activeGeometryId,
  );
  const activeMesh = meshes.find((m) => m.id === activeMeshId) ?? null;

  useEffect(() => {
    if (!activeMeshId && meshes.length > 0) {
      setActiveMeshId(meshes[0].id);
    }
  }, [activeMeshId, meshes, setActiveMeshId]);

  const handleGenerate = async (e: FormEvent) => {
    e.preventDefault();
    if (!activeGeometryId) return;
    const size = Number(elementSize);
    if (!Number.isFinite(size) || size <= 0) return;

    const created = await generateMutation.mutateAsync({
      geometryId: activeGeometryId,
      elementType,
      targetElementSize: size,
    });
    setActiveMeshId(created.id);
    announce(`${t("meshSectionTitle")}: ${created.element_count} ${created.element_type}`);
  };

  return (
    <Card className="space-y-3">
      <CardTitle>{t("meshSectionTitle")}</CardTitle>

      <form onSubmit={handleGenerate} className="space-y-2.5">
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label htmlFor={elemTypeId}>{t("elementType")}</Label>
            <NativeSelect
              id={elemTypeId}
              value={elementType}
              onChange={(e) => setElementType(e.target.value as ElementType)}
            >
              <option value="H8">H8 (Hexa Voxel)</option>
              <option value="C3D4">C3D4 (Gmsh Tet4)</option>
              <option value="C3D10">C3D10 (Gmsh Tet10)</option>
            </NativeSelect>
          </div>
          <div>
            <Label htmlFor={elemSizeId}>{t("elementSize")}</Label>
            <Input
              id={elemSizeId}
              type="number"
              step="any"
              min="0.001"
              value={elementSize}
              onChange={(e) => setElementSize(e.target.value)}
            />
          </div>
        </div>

        <Button
          type="submit"
          className="w-full"
          disabled={!activeGeometryId || generateMutation.isPending}
          data-testid="generate-mesh-btn"
        >
          <Box className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{generateMutation.isPending ? "..." : t("generateMesh")}</span>
        </Button>
      </form>

      {generateMutation.isError && (
        <div role="alert" className="rounded border border-red-500/40 bg-red-500/10 p-2 text-[11px] text-red-400">
          {generateMutation.error.message}
        </div>
      )}

      {meshes.length > 0 && (
        <div>
          <Label htmlFor={meshSelectId}>Volume Meshes</Label>
          <NativeSelect
            id={meshSelectId}
            value={activeMeshId ?? ""}
            onChange={(e) => setActiveMeshId(e.target.value || null)}
          >
            {meshes.map((m) => (
              <option key={m.id} value={m.id}>
                {m.element_type} · {m.element_count} elems · {m.node_count} nodes
              </option>
            ))}
          </NativeSelect>
        </div>
      )}

      {activeMesh && (
        <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-app)] p-2.5 text-[11px] space-y-1">
          <div className="flex items-center justify-between">
            <Badge variant="info">{activeMesh.element_type}</Badge>
            <span className="font-mono-tech text-[var(--text-muted)]">
              J_min: {activeMesh.min_scaled_jacobian.toFixed(3)}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-1 font-mono-tech text-[var(--text-muted)]">
            <span>Nodes: {activeMesh.node_count}</span>
            <span>Elems: {activeMesh.element_count}</span>
            <span>Surf Tris: {activeMesh.surface_triangle_count}</span>
            <span>Vol: {activeMesh.total_volume.toFixed(1)}</span>
          </div>
        </div>
      )}
    </Card>
  );
}
