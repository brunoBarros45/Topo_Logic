import { GizmoHelper, GizmoViewport, OrbitControls } from "@react-three/drei";
import { Canvas, type ThreeEvent, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type ComponentRef } from "react";
import * as THREE from "three";
import { acceleratedRaycast } from "three-mesh-bvh";

import type { AxisConvention } from "@/api/types";
import {
  publishCameraPose,
  subscribeCameraPose,
  type CameraPose,
} from "@/engine/cameraBridge";
import {
  extractPatchPositions,
  floodFillTriangles,
} from "@/engine/floodFillPicker";
import { sceneRegistry, type R3fMeshResource } from "@/engine/sceneRegistry";
import { useSceneResourceRevision } from "@/api/queries";
import { useStudyBuilderStore } from "@/stores/studyBuilderStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";

// Enable BVH raycast acceleration globally once
THREE.Mesh.prototype.raycast = acceleratedRaycast;

function cadToScene(v: readonly [number, number, number], isZUp: boolean): [number, number, number] {
  return isZUp ? [v[0], v[2], -v[1]] : [v[0], v[1], v[2]];
}

function sceneToCad(v: THREE.Vector3, isZUp: boolean): [number, number, number] {
  return isZUp ? [v.x, -v.z, v.y] : [v.x, v.y, v.z];
}

function cadVecToScene(v: THREE.Vector3, isZUp: boolean): THREE.Vector3 {
  return isZUp ? new THREE.Vector3(v.x, v.z, -v.y) : v.clone();
}

function SceneCameraBridge({
  viewerId,
  resource,
  isZUp,
  syncEnabled,
}: {
  viewerId: string;
  resource: R3fMeshResource | null;
  isZUp: boolean;
  syncEnabled: boolean;
}) {
  const { camera, invalidate } = useThree();
  const controlsRef = useRef<ComponentRef<typeof OrbitControls> | null>(null);
  const lastFramedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!resource || lastFramedKeyRef.current === resource.key) return;
    lastFramedKeyRef.current = resource.key;

    const [cx, cy, cz] = cadToScene(resource.center, isZUp);
    const dist = Math.max(resource.radius * 2.6, 5);
    camera.position.set(cx + dist * 0.7, cy + dist * 0.55, cz + dist * 0.7);
    camera.lookAt(cx, cy, cz);
    if (controlsRef.current) {
      controlsRef.current.target.set(cx, cy, cz);
      controlsRef.current.update();
    }
    invalidate();
  }, [resource, isZUp, camera, invalidate]);

  useEffect(() => {
    if (!syncEnabled) return;
    return subscribeCameraPose(viewerId, (pose: CameraPose) => {
      const [px, py, pz] = cadToScene(pose.position, isZUp);
      const [fx, fy, fz] = cadToScene(pose.focalPoint, isZUp);
      const [ux, uy, uz] = cadToScene(pose.viewUp, isZUp);
      camera.position.set(px, py, pz);
      camera.up.set(ux, uy, uz);
      if (controlsRef.current) {
        controlsRef.current.target.set(fx, fy, fz);
        controlsRef.current.update();
      } else {
        camera.lookAt(fx, fy, fz);
      }
      invalidate();
    });
  }, [viewerId, isZUp, syncEnabled, camera, invalidate]);

  const handleOrbitChange = () => {
    if (!syncEnabled || !controlsRef.current) return;
    const persp = camera as THREE.PerspectiveCamera;
    publishCameraPose(viewerId, {
      position: sceneToCad(camera.position, isZUp),
      focalPoint: sceneToCad(controlsRef.current.target, isZUp),
      viewUp: sceneToCad(cadVecToScene(camera.up, false), isZUp),
      fovDeg: persp.fov ?? 45,
    });
  };

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping={false}
      onChange={handleOrbitChange}
    />
  );
}

function EngineeringScene({
  viewerId,
  resourceKey,
  axisConvention,
}: {
  viewerId: string;
  resourceKey: string | null;
  axisConvention: AxisConvention;
}) {
  const revision = useSceneResourceRevision(resourceKey);
  const rawResource = sceneRegistry.get(resourceKey);
  const resource = rawResource?.kind === "r3f-mesh" ? rawResource : null;
  const isZUp = axisConvention === "Z_up";

  const {
    regions,
    supports,
    loadCases,
    designZones,
    pickingActive,
    pickingRegionName,
    creaseAngleDeg,
    highlightedRegionId,
    addFloodFillRegion,
  } = useStudyBuilderStore();
  const { cameraSyncEnabled, announce } = useWorkspaceStore();

  const overlayGeo = useMemo(() => {
    void revision;
    const current = sceneRegistry.get(resourceKey);
    const meshRes = current?.kind === "r3f-mesh" ? current : null;
    if (!meshRes || !highlightedRegionId) return null;
    const region = regions.find((r) => r.id === highlightedRegionId);
    if (!region || region.selector.kind !== "triangle_set") return null;
    const positions = extractPatchPositions(
      meshRes.geometry,
      region.selector.triangle_indices,
    );
    if (positions.length === 0) return null;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.computeVertexNormals();
    return geo;
  }, [resourceKey, highlightedRegionId, regions, revision]);

  useEffect(() => {
    return () => {
      overlayGeo?.dispose();
    };
  }, [overlayGeo]);

  const handleMeshClick = (e: ThreeEvent<MouseEvent>) => {
    if (
      !pickingActive ||
      !resource ||
      e.faceIndex === undefined ||
      e.faceIndex === null
    ) {
      return;
    }
    e.stopPropagation();
    const picked = floodFillTriangles(
      resource.adjacency,
      e.faceIndex,
      creaseAngleDeg,
    );
    addFloodFillRegion(pickingRegionName, picked, creaseAngleDeg);
    announce(`Flood-fill: ${picked.length} triangles`);
  };

  const scaleRef = resource ? Math.max(resource.radius * 0.14, 1) : 2;
  const highlightedColor =
    regions.find((r) => r.id === highlightedRegionId)?.color ?? "#38bdf8";

  return (
    <>
      <ambientLight intensity={0.75} />
      <directionalLight position={[10, 15, 12]} intensity={1.1} />
      <directionalLight position={[-10, -8, -10]} intensity={0.45} />

      <SceneCameraBridge
        viewerId={viewerId}
        resource={resource}
        isZUp={isZUp}
        syncEnabled={cameraSyncEnabled}
      />

      <group rotation={isZUp ? [-Math.PI / 2, 0, 0] : [0, 0, 0]}>
        {resource && (
          <mesh
            geometry={resource.geometry}
            onClick={handleMeshClick}
          >
            <meshStandardMaterial
              color="#7b8ea3"
              metalness={0.35}
              roughness={0.45}
              side={THREE.DoubleSide}
            />
          </mesh>
        )}

        {overlayGeo && (
          <mesh geometry={overlayGeo}>
            <meshBasicMaterial
              color={highlightedColor}
              transparent
              opacity={0.72}
              polygonOffset
              polygonOffsetFactor={-2}
              side={THREE.DoubleSide}
            />
          </mesh>
        )}

        {/* Boundary condition & DesignZone glyphs */}
        {resource &&
          regions.map((reg) => {
            if (reg.selector.kind === "bounding_box") {
              const [x0, y0, z0] = reg.selector.min_corner;
              const [x1, y1, z1] = reg.selector.max_corner;
              const size: [number, number, number] = [
                Math.max(x1 - x0, scaleRef * 0.15),
                Math.max(y1 - y0, scaleRef * 0.15),
                Math.max(z1 - z0, scaleRef * 0.15),
              ];
              const isZone = designZones.find((d) => d.region_id === reg.id);
              const boxColor =
                isZone?.zone_type === "passive_solid"
                  ? "#22c55e"
                  : isZone?.zone_type === "passive_void"
                    ? "#ef4444"
                    : reg.color;
              return (
                <mesh
                  key={reg.id}
                  position={[0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)]}
                >
                  <boxGeometry args={size} />
                  <meshBasicMaterial
                    color={boxColor}
                    wireframe={!isZone}
                    transparent
                    opacity={isZone ? 0.35 : 0.85}
                  />
                </mesh>
              );
            }
            if (reg.selector.kind === "plane") {
              const hasSup = supports.some((s) => s.region_id === reg.id);
              const hasLoad = loadCases.some((lc) =>
                lc.loads.some((l) => l.region_id === reg.id),
              );
              const glyphColor = hasSup ? "#22c55e" : hasLoad ? "#f59e0b" : reg.color;
              const [px, py, pz] = reg.selector.point;
              return (
                <mesh key={reg.id} position={[px, py, pz]}>
                  <coneGeometry args={[scaleRef * 0.35, scaleRef * 0.8, 12]} />
                  <meshStandardMaterial color={glyphColor} />
                </mesh>
              );
            }
            return null;
          })}
      </group>

      {resource && (
        <gridHelper
          args={[Math.max(resource.radius * 4, 20), 16, "#334155", "#1e293b"]}
          position={[
            cadToScene(resource.center, isZUp)[0],
            cadToScene(resource.boundsMin, isZUp)[1],
            cadToScene(resource.center, isZUp)[2],
          ]}
        />
      )}

      <GizmoHelper alignment="bottom-left" margin={[56, 56]}>
        <GizmoViewport axisColors={["#ef4444", "#22c55e", "#38bdf8"]} labelColor="white" />
      </GizmoHelper>
    </>
  );
}

export interface R3fSetupViewportProps {
  viewerId?: string;
  resourceKey: string | null;
  axisConvention: AxisConvention;
  statusLabel?: string | null;
}

export function R3fSetupViewport({
  viewerId = "r3f-main",
  resourceKey,
  axisConvention,
  statusLabel,
}: R3fSetupViewportProps) {
  const pickingActive = useStudyBuilderStore((s) => s.pickingActive);

  return (
    <div
      className={`relative h-full w-full bg-[#090d13] ${
        pickingActive ? "cursor-crosshair" : "cursor-grab"
      }`}
      data-testid={`r3f-viewport-${viewerId}`}
    >
      <Canvas
        dpr={[1, 2]}
        camera={{ fov: 45, near: 0.05, far: 100000 }}
        gl={{ antialias: true }}
      >
        <EngineeringScene
          viewerId={viewerId}
          resourceKey={resourceKey}
          axisConvention={axisConvention}
        />
      </Canvas>

      {statusLabel && (
        <div className="pointer-events-none absolute top-3 left-3 rounded bg-slate-950/75 px-2 py-1 text-[11px] font-mono-tech text-slate-300 border border-slate-800">
          {statusLabel}
        </div>
      )}
    </div>
  );
}
