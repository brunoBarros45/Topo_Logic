import "@kitware/vtk.js/Rendering/Profiles/Geometry";
import vtkPlane from "@kitware/vtk.js/Common/DataModel/Plane";
import vtkPolyData from "@kitware/vtk.js/Common/DataModel/PolyData";
import vtkImageMarchingCubes from "@kitware/vtk.js/Filters/General/ImageMarchingCubes";
import vtkActor from "@kitware/vtk.js/Rendering/Core/Actor";
import vtkColorTransferFunction from "@kitware/vtk.js/Rendering/Core/ColorTransferFunction";
import vtkMapper from "@kitware/vtk.js/Rendering/Core/Mapper";
import vtkPointPicker from "@kitware/vtk.js/Rendering/Core/PointPicker";
import vtkGenericRenderWindow from "@kitware/vtk.js/Rendering/Misc/GenericRenderWindow";
import { useEffect, useRef } from "react";

import { useSceneResourceRevision } from "@/api/queries";
import {
  publishCameraPose,
  subscribeCameraPose,
  type CameraPose,
} from "@/engine/cameraBridge";
import { applyColormapToTransferFunction } from "@/engine/colormaps";
import { sceneRegistry } from "@/engine/sceneRegistry";
import { usePostProcessStore } from "@/stores/postProcessStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";

export interface VtkResultsViewportProps {
  viewerId?: string;
  resourceKey: string | null;
  unitLabel: string;
  statusLabel?: string | null;
}

interface VtkRuntime {
  grw: ReturnType<typeof vtkGenericRenderWindow.newInstance>;
  actor: ReturnType<typeof vtkActor.newInstance>;
  mapper: ReturnType<typeof vtkMapper.newInstance>;
  ctf: ReturnType<typeof vtkColorTransferFunction.newInstance>;
  ghostActor: ReturnType<typeof vtkActor.newInstance>;
  ghostMapper: ReturnType<typeof vtkMapper.newInstance>;
  marchingCubes: ReturnType<typeof vtkImageMarchingCubes.newInstance>;
  picker: ReturnType<typeof vtkPointPicker.newInstance>;
  warpedPoly: ReturnType<typeof vtkPolyData.newInstance>;
  planeX: ReturnType<typeof vtkPlane.newInstance>;
  planeY: ReturnType<typeof vtkPlane.newInstance>;
  planeZ: ReturnType<typeof vtkPlane.newInstance>;
  warpedPointsBuf: Float32Array | null;
  bounds: [number, number, number, number, number, number];
}

export function VtkResultsViewport({
  viewerId = "vtk-main",
  resourceKey,
  unitLabel,
  statusLabel,
}: VtkResultsViewportProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const runtimeRef = useRef<VtkRuntime | null>(null);
  const framedKeyRef = useRef<string | null>(null);

  const revision = useSceneResourceRevision(resourceKey);
  const resource = sceneRegistry.get(resourceKey);

  const cameraSyncEnabled = useWorkspaceStore((s) => s.cameraSyncEnabled);
  const {
    scalarField,
    colormap,
    autoRange,
    manualMin,
    manualMax,
    deformScale,
    animateDeform,
    showGhostWireframe,
    clipX,
    clipY,
    clipZ,
    densityThreshold,
    setProbeReading,
  } = usePostProcessStore();

  // Mount generic render window and clean up explicitly on unmount
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const grw = vtkGenericRenderWindow.newInstance({
      background: [0.04, 0.06, 0.09],
      listenWindowResize: false,
    });
    grw.setContainer(el);
    grw.resize();

    const ctf = vtkColorTransferFunction.newInstance();
    const mapper = vtkMapper.newInstance();
    mapper.setLookupTable(ctf);
    mapper.setColorModeToMapScalars();
    mapper.setScalarModeToUsePointData();

    const actor = vtkActor.newInstance();
    actor.setMapper(mapper);

    const ghostMapper = vtkMapper.newInstance();
    ghostMapper.setScalarVisibility(false);
    const ghostActor = vtkActor.newInstance();
    ghostActor.setMapper(ghostMapper);
    ghostActor.getProperty().setRepresentationToWireframe();
    ghostActor.getProperty().setOpacity(0.18);
    ghostActor.getProperty().setColor(0.55, 0.65, 0.78);
    ghostActor.setVisibility(false);

    const marchingCubes = vtkImageMarchingCubes.newInstance({
      contourValue: 0.5,
      computeNormals: true,
      mergePoints: true,
    });

    const picker = vtkPointPicker.newInstance();
    picker.setPickFromList(true);
    picker.addPickList(actor);

    const warpedPoly = vtkPolyData.newInstance();
    const planeX = vtkPlane.newInstance({ normal: [-1, 0, 0], origin: [0, 0, 0] });
    const planeY = vtkPlane.newInstance({ normal: [0, -1, 0], origin: [0, 0, 0] });
    const planeZ = vtkPlane.newInstance({ normal: [0, 0, -1], origin: [0, 0, 0] });

    const renderer = grw.getRenderer();
    renderer.addActor(actor);
    renderer.addActor(ghostActor);

    const rt: VtkRuntime = {
      grw,
      actor,
      mapper,
      ctf,
      ghostActor,
      ghostMapper,
      marchingCubes,
      picker,
      warpedPoly,
      planeX,
      planeY,
      planeZ,
      warpedPointsBuf: null,
      bounds: [0, 1, 0, 1, 0, 1],
    };
    runtimeRef.current = rt;

    const ro = new ResizeObserver(() => {
      grw.resize();
    });
    ro.observe(el);

    const interactor = grw.getInteractor();
    const emitCamera = () => {
      if (!useWorkspaceStore.getState().cameraSyncEnabled) return;
      const cam = renderer.getActiveCamera();
      const pos = cam.getPosition();
      const fp = cam.getFocalPoint();
      const up = cam.getViewUp();
      publishCameraPose(viewerId, {
        position: [pos[0], pos[1], pos[2]],
        focalPoint: [fp[0], fp[1], fp[2]],
        viewUp: [up[0], up[1], up[2]],
        fovDeg: cam.getViewAngle(),
      });
    };
    const subAnim = interactor.onAnimation(emitCamera);
    const subEnd = interactor.onEndAnimation(emitCamera);

    return () => {
      subAnim.unsubscribe();
      subEnd.unsubscribe();
      ro.disconnect();
      planeX.delete();
      planeY.delete();
      planeZ.delete();
      warpedPoly.delete();
      picker.delete();
      marchingCubes.delete();
      ghostActor.delete();
      ghostMapper.delete();
      actor.delete();
      mapper.delete();
      ctf.delete();
      grw.delete();
      runtimeRef.current = null;
    };
  }, [viewerId]);

  // Camera sync subscriber
  useEffect(() => {
    if (!cameraSyncEnabled) return;
    return subscribeCameraPose(viewerId, (pose: CameraPose) => {
      const rt = runtimeRef.current;
      if (!rt) return;
      const renderer = rt.grw.getRenderer();
      const cam = renderer.getActiveCamera();
      cam.setPosition(...pose.position);
      cam.setFocalPoint(...pose.focalPoint);
      cam.setViewUp(...pose.viewUp);
      renderer.resetCameraClippingRange();
      rt.grw.getRenderWindow().render();
    });
  }, [viewerId, cameraSyncEnabled]);

  // Attach dataset + scalar field + LUT + ghost wireframe + clipping planes
  useEffect(() => {
    const rt = runtimeRef.current;
    if (!rt) return;
    const renderer = rt.grw.getRenderer();
    const rw = rt.grw.getRenderWindow();

    if (!resource) {
      rt.actor.setVisibility(false);
      rt.ghostActor.setVisibility(false);
      rw.render();
      return;
    }

    rt.actor.setVisibility(true);

    if (resource.kind === "vtk-fem") {
      rt.warpedPoly.shallowCopy(resource.polyData);
      if (
        !rt.warpedPointsBuf ||
        rt.warpedPointsBuf.length !== resource.basePoints.length
      ) {
        rt.warpedPointsBuf = new Float32Array(resource.basePoints.length);
      }
      rt.warpedPointsBuf.set(resource.basePoints);
      rt.warpedPoly.getPoints().setData(rt.warpedPointsBuf, 3);

      const pd = rt.warpedPoly.getPointData();
      const chosen =
        resource.fieldNames.includes(scalarField)
          ? scalarField
          : resource.fieldNames[0] ?? "von_mises";
      pd.setActiveScalars(chosen);

      const range = resource.fieldRanges[chosen] ?? [0, 1];
      const minVal = autoRange ? range[0] : manualMin;
      const maxVal = autoRange ? range[1] : manualMax;
      applyColormapToTransferFunction(rt.ctf, minVal, maxVal, colormap);

      rt.mapper.setScalarVisibility(true);
      rt.mapper.setScalarModeToUsePointData();
      rt.mapper.setScalarRange(minVal, Math.max(maxVal, minVal + 1e-6));
      rt.mapper.setInputData(rt.warpedPoly);

      rt.ghostMapper.setInputData(resource.polyData);
      rt.ghostActor.setVisibility(showGhostWireframe);

      const b = resource.polyData.getBounds();
      rt.bounds = [b[0], b[1], b[2], b[3], b[4], b[5]];
    } else if (resource.kind === "vtk-vti") {
      rt.ghostActor.setVisibility(false);
      rt.marchingCubes.setInputData(resource.imageData);
      rt.marchingCubes.setContourValue(densityThreshold);
      rt.mapper.setScalarVisibility(false);
      rt.actor.getProperty().setColor(0.22, 0.74, 0.97);
      rt.mapper.setInputConnection(rt.marchingCubes.getOutputPort());
      rt.bounds = resource.bounds;
    }

    // Apply clipping planes
    rt.mapper.removeAllClippingPlanes();
    const [xmin, xmax, ymin, ymax, zmin, zmax] = rt.bounds;
    if (clipX.enabled) {
      rt.planeX.setOrigin(xmin + clipX.ratio * (xmax - xmin), ymin, zmin);
      rt.mapper.addClippingPlane(rt.planeX);
    }
    if (clipY.enabled) {
      rt.planeY.setOrigin(xmin, ymin + clipY.ratio * (ymax - ymin), zmin);
      rt.mapper.addClippingPlane(rt.planeY);
    }
    if (clipZ.enabled) {
      rt.planeZ.setOrigin(xmin, ymin, zmin + clipZ.ratio * (zmax - zmin));
      rt.mapper.addClippingPlane(rt.planeZ);
    }

    if (framedKeyRef.current !== `${resource.key}:${revision}`) {
      framedKeyRef.current = `${resource.key}:${revision}`;
      renderer.resetCamera();
    }
    rw.render();
  }, [
    resource,
    revision,
    scalarField,
    colormap,
    autoRange,
    manualMin,
    manualMax,
    showGhostWireframe,
    clipX,
    clipY,
    clipZ,
    densityThreshold,
  ]);

  // Zero-allocation Float32 deformation warp + optional animation loop
  useEffect(() => {
    const rt = runtimeRef.current;
    if (!rt || !resource || resource.kind !== "vtk-fem") return;
    const { basePoints, displacement } = resource;
    const buf = rt.warpedPointsBuf;
    if (!buf || !displacement) return;

    const applyScale = (factor: number) => {
      for (let i = 0; i < buf.length; i++) {
        buf[i] = basePoints[i] + factor * displacement[i];
      }
      rt.warpedPoly.getPoints().modified();
      rt.warpedPoly.modified();
      rt.grw.getRenderWindow().render();
    };

    if (!animateDeform) {
      applyScale(deformScale);
      return;
    }

    let rafId = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const elapsed = (now - t0) * 0.004;
      const factor = deformScale * 0.5 * (1 - Math.cos(elapsed));
      applyScale(factor);
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [resource, revision, deformScale, animateDeform]);

  // Point-probe on click (ignoring drags)
  const pointerStartRef = useRef<{ x: number; y: number } | null>(null);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    pointerStartRef.current = { x: e.clientX, y: e.clientY };
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const start = pointerStartRef.current;
    pointerStartRef.current = null;
    if (!start || !resource || resource.kind !== "vtk-fem") return;
    if (Math.hypot(e.clientX - start.x, e.clientY - start.y) > 4) return;

    const rt = runtimeRef.current;
    const el = containerRef.current;
    if (!rt || !el) return;

    const rect = el.getBoundingClientRect();
    const size = rt.grw.getApiSpecificRenderWindow().getSize();
    const scaleX = rect.width > 0 ? size[0] / rect.width : 1;
    const scaleY = rect.height > 0 ? size[1] / rect.height : 1;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (rect.height - (e.clientY - rect.top)) * scaleY;

    rt.picker.pick([x, y, 0], rt.grw.getRenderer());
    const pointId = rt.picker.getPointId();
    if (pointId < 0) return;

    const scalars = rt.warpedPoly.getPointData().getArrayByName(scalarField);
    const val = scalars ? scalars.getTuple(pointId)[0] : 0;
    const pts = rt.warpedPoly.getPoints();
    const pt = pts.getTuple(pointId);
    setProbeReading({
      pointId,
      position: [pt[0], pt[1], pt[2]],
      value: val,
      field: scalarField,
      unit: unitLabel,
    });
  };

  return (
    <div
      className="relative h-full w-full bg-[#090d13]"
      data-testid={`vtk-viewport-${viewerId}`}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
    >
      <div ref={containerRef} className="h-full w-full" />
      {statusLabel && (
        <div className="pointer-events-none absolute top-3 left-3 rounded bg-slate-950/75 px-2 py-1 text-[11px] font-mono-tech text-slate-300 border border-slate-800">
          {statusLabel}
        </div>
      )}
    </div>
  );
}
