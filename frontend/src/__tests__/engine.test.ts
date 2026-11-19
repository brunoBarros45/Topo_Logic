import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import { publishCameraPose, subscribeCameraPose } from "@/engine/cameraBridge";
import { getColormapCssGradient, sampleColormapRgb } from "@/engine/colormaps";
import {
  buildTriangleAdjacency,
  extractPatchPositions,
  floodFillTriangles,
} from "@/engine/floodFillPicker";
import { SceneResourceRegistry } from "@/engine/sceneRegistry";

describe("Flood-fill picker", () => {
  it("selects exactly one planar face (2 triangles) on both indexed and non-indexed boxes", () => {
    const indexedBox = new THREE.BoxGeometry(10, 10, 10);
    const nonIndexedBox = indexedBox.toNonIndexed();

    for (const geo of [indexedBox, nonIndexedBox]) {
      const adj = buildTriangleAdjacency(geo);
      expect(adj.triangleCount).toBe(12);

      const picked = floodFillTriangles(adj, 0, 22);
      expect(picked.length).toBe(2);

      const pos = extractPatchPositions(geo, picked);
      expect(pos.length).toBe(18); // 2 tris * 3 verts * 3 coords
      geo.dispose();
    }
  });
});

describe("SceneResourceRegistry LRU & GPU disposal", () => {
  it("evicts least recently used resources and invokes .dispose()", () => {
    const reg = new SceneResourceRegistry(2);
    const g1 = new THREE.BoxGeometry(1, 1, 1);
    const g2 = new THREE.BoxGeometry(2, 2, 2);
    const g3 = new THREE.BoxGeometry(3, 3, 3);

    const spy1 = vi.spyOn(g1, "dispose");
    const spy2 = vi.spyOn(g2, "dispose");
    const spy3 = vi.spyOn(g3, "dispose");

    reg.registerR3fGeometry("g1", g1);
    reg.registerR3fGeometry("g2", g2);
    // Touch g1 so g2 becomes least recently used
    expect(reg.get("g1")).toBeDefined();

    reg.registerR3fGeometry("g3", g3);
    expect(spy2).toHaveBeenCalledTimes(1);
    expect(spy1).not.toHaveBeenCalled();
    expect(reg.getStats().keys).toEqual(["g1", "g3"]);

    reg.clear();
    expect(spy1).toHaveBeenCalledTimes(1);
    expect(spy3).toHaveBeenCalledTimes(1);
  });
});

describe("CameraBridge & Colormaps", () => {
  it("broadcasts CameraPose to peer viewports without self-echo or recursion", () => {
    const onVtk = vi.fn();
    const onR3f = vi.fn();
    const unsubVtk = subscribeCameraPose("vtk-main", onVtk);
    const unsubR3f = subscribeCameraPose("r3f-main", onR3f);

    const pose = {
      position: [10, 20, 30] as [number, number, number],
      focalPoint: [0, 0, 0] as [number, number, number],
      viewUp: [0, 0, 1] as [number, number, number],
      fovDeg: 45,
    };
    publishCameraPose("r3f-main", pose);

    expect(onVtk).toHaveBeenCalledTimes(1);
    expect(onVtk).toHaveBeenCalledWith(pose, "r3f-main");
    expect(onR3f).not.toHaveBeenCalled();

    unsubVtk();
    unsubR3f();
  });

  it("samples bounded RGB stops and generates valid CSS gradients", () => {
    const [r, g, b] = sampleColormapRgb(0.5, "turbo");
    expect(r).toBeGreaterThanOrEqual(0);
    expect(r).toBeLessThanOrEqual(1);
    expect(g).toBeGreaterThanOrEqual(0);
    expect(b).toBeGreaterThanOrEqual(0);
    expect(getColormapCssGradient("viridis")).toContain("linear-gradient(");
  });
});
