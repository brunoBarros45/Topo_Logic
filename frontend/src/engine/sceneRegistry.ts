import type vtkImageData from "@kitware/vtk.js/Common/DataModel/ImageData";
import type vtkPolyData from "@kitware/vtk.js/Common/DataModel/PolyData";
import vtkXMLImageDataReader from "@kitware/vtk.js/IO/XML/XMLImageDataReader";
import vtkXMLPolyDataReader from "@kitware/vtk.js/IO/XML/XMLPolyDataReader";
import * as THREE from "three";
import { MeshBVH } from "three-mesh-bvh";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import { buildTriangleAdjacency, type TriangleAdjacency } from "@/engine/floodFillPicker";

export interface R3fMeshResource {
  kind: "r3f-mesh";
  key: string;
  geometry: THREE.BufferGeometry;
  adjacency: TriangleAdjacency;
  boundsMin: [number, number, number];
  boundsMax: [number, number, number];
  center: [number, number, number];
  radius: number;
  vertexCount: number;
  triangleCount: number;
}

export interface VtkFemResource {
  kind: "vtk-fem";
  key: string;
  polyData: vtkPolyData;
  basePoints: Float32Array;
  displacement: Float32Array | null;
  fieldNames: string[];
  fieldRanges: Record<string, [number, number]>;
  pointCount: number;
  polyCount: number;
}

export interface VtkTopOptResource {
  kind: "vtk-vti";
  key: string;
  imageData: vtkImageData;
  dimensions: [number, number, number];
  bounds: [number, number, number, number, number, number];
  range: [number, number];
}

export type SceneResource = R3fMeshResource | VtkFemResource | VtkTopOptResource;

type RegistryListener = () => void;

export interface ResourceHandle {
  key: string;
  revision: number;
}

/**
 * Off-React imperative registry managing heavy Three.js geometries, BVHs,
 * TypedArrays, and VTK datasets with bounded LRU eviction and explicit GPU disposal.
 */
export class SceneResourceRegistry {
  private readonly maxEntries: number;
  private readonly entries = new Map<string, SceneResource>();
  private readonly revisions = new Map<string, number>();
  private readonly listeners = new Set<RegistryListener>();
  private globalRevision = 0;

  constructor(maxEntries = 12) {
    this.maxEntries = maxEntries;
  }

  subscribe = (listener: RegistryListener): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): number => this.globalRevision;

  getRevision(key: string | null): number {
    if (!key) return 0;
    return this.revisions.get(key) ?? 0;
  }

  get(key: string | null): SceneResource | undefined {
    if (!key) return undefined;
    const found = this.entries.get(key);
    if (found) {
      // Refresh LRU recency
      this.entries.delete(key);
      this.entries.set(key, found);
    }
    return found;
  }

  getStats(): { entryCount: number; keys: string[] } {
    return {
      entryCount: this.entries.size,
      keys: Array.from(this.entries.keys()),
    };
  }

  registerR3fGeometry(key: string, geometry: THREE.BufferGeometry): R3fMeshResource {
    if (!geometry.getAttribute("normal")) {
      geometry.computeVertexNormals();
    }
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();

    const bvh = new MeshBVH(geometry);
    (geometry as THREE.BufferGeometry & { boundsTree?: MeshBVH }).boundsTree = bvh;

    const adjacency = buildTriangleAdjacency(geometry);
    const bbox = geometry.boundingBox ?? new THREE.Box3();
    const bs = geometry.boundingSphere ?? new THREE.Sphere();
    const posAttr = geometry.getAttribute("position");

    const resource: R3fMeshResource = {
      kind: "r3f-mesh",
      key,
      geometry,
      adjacency,
      boundsMin: [bbox.min.x, bbox.min.y, bbox.min.z],
      boundsMax: [bbox.max.x, bbox.max.y, bbox.max.z],
      center: [bs.center.x, bs.center.y, bs.center.z],
      radius: Math.max(bs.radius, 1e-3),
      vertexCount: posAttr ? posAttr.count : 0,
      triangleCount: adjacency.triangleCount,
    };

    this.insertResource(key, resource);
    return resource;
  }

  async registerGlbBuffer(key: string, arrayBuffer: ArrayBuffer): Promise<R3fMeshResource> {
    const loader = new GLTFLoader();
    const gltf = await new Promise<{ scene: THREE.Group }>((resolve, reject) => {
      loader.parse(arrayBuffer, "", resolve, reject);
    });

    const geometries: THREE.BufferGeometry[] = [];
    gltf.scene.updateMatrixWorld(true);
    gltf.scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh && obj.geometry instanceof THREE.BufferGeometry) {
        const clone = obj.geometry.clone();
        clone.applyMatrix4(obj.matrixWorld);
        geometries.push(clone);
      }
    });

    if (geometries.length === 0) {
      throw new Error("GLB asset contained no renderable mesh geometries.");
    }

    let merged: THREE.BufferGeometry;
    if (geometries.length === 1) {
      merged = geometries[0];
    } else {
      const combined = mergeGeometries(geometries, false);
      geometries.forEach((g) => g.dispose());
      if (!combined) {
        throw new Error("Failed to merge GLB sub-meshes.");
      }
      merged = combined;
    }
    return this.registerR3fGeometry(key, merged);
  }

  registerStlBuffer(key: string, arrayBuffer: ArrayBuffer): R3fMeshResource {
    const loader = new STLLoader();
    const geometry = loader.parse(arrayBuffer);
    return this.registerR3fGeometry(key, geometry);
  }

  registerFemVtpBuffer(key: string, arrayBuffer: ArrayBuffer): VtkFemResource {
    const reader = vtkXMLPolyDataReader.newInstance();
    const ok = reader.parseAsArrayBuffer(arrayBuffer);
    if (!ok) {
      reader.delete();
      throw new Error("Failed to parse VTK XML PolyData (.vtp) payload.");
    }
    const polyData = reader.getOutputData(0);
    reader.delete();

    const ptsRaw = polyData.getPoints().getData();
    const basePoints = new Float32Array(ptsRaw.length);
    basePoints.set(ptsRaw);

    const pd = polyData.getPointData();
    const fieldNames: string[] = [];
    const fieldRanges: Record<string, [number, number]> = {};
    let displacement: Float32Array | null = null;

    const nArrays = pd.getNumberOfArrays();
    for (let i = 0; i < nArrays; i++) {
      const arr = pd.getArrayByIndex(i);
      if (!arr) continue;
      const name = arr.getName();
      if (!name) continue;
      fieldNames.push(name);
      const r = arr.getRange(0);
      fieldRanges[name] = [r[0], r[1]];
      if (name === "displacement" && arr.getNumberOfComponents() === 3) {
        const dRaw = arr.getData();
        displacement = new Float32Array(dRaw.length);
        displacement.set(dRaw);
      }
    }

    const resource: VtkFemResource = {
      kind: "vtk-fem",
      key,
      polyData,
      basePoints,
      displacement,
      fieldNames,
      fieldRanges,
      pointCount: polyData.getNumberOfPoints(),
      polyCount: polyData.getNumberOfPolys(),
    };

    this.insertResource(key, resource);
    return resource;
  }

  registerTopOptVtiBuffer(key: string, arrayBuffer: ArrayBuffer): VtkTopOptResource {
    const reader = vtkXMLImageDataReader.newInstance();
    const ok = reader.parseAsArrayBuffer(arrayBuffer);
    if (!ok) {
      reader.delete();
      throw new Error("Failed to parse VTK XML ImageData (.vti) payload.");
    }
    const imageData = reader.getOutputData(0);
    reader.delete();

    const dims = imageData.getDimensions();
    const b = imageData.getBounds();
    const scalars = imageData.getPointData().getScalars();
    const rangeTuple = scalars ? scalars.getRange(0) : [0, 1];

    const resource: VtkTopOptResource = {
      kind: "vtk-vti",
      key,
      imageData,
      dimensions: [dims[0], dims[1], dims[2]],
      bounds: [b[0], b[1], b[2], b[3], b[4], b[5]],
      range: [rangeTuple[0], rangeTuple[1]],
    };

    this.insertResource(key, resource);
    return resource;
  }

  deleteResource(key: string): void {
    const existing = this.entries.get(key);
    if (!existing) return;
    this.entries.delete(key);
    this.disposeResource(existing);
    this.notify();
  }

  clear(): void {
    for (const resource of this.entries.values()) {
      this.disposeResource(resource);
    }
    this.entries.clear();
    this.notify();
  }

  private insertResource(key: string, resource: SceneResource): void {
    const existing = this.entries.get(key);
    if (existing) {
      this.entries.delete(key);
      this.disposeResource(existing);
    }

    while (this.entries.size >= this.maxEntries) {
      const oldestKey = this.entries.keys().next().value;
      if (oldestKey === undefined) break;
      const oldest = this.entries.get(oldestKey);
      this.entries.delete(oldestKey);
      if (oldest) this.disposeResource(oldest);
    }

    this.entries.set(key, resource);
    const nextRev = (this.revisions.get(key) ?? 0) + 1;
    this.revisions.set(key, nextRev);
    this.notify();
  }

  private disposeResource(resource: SceneResource): void {
    if (resource.kind === "r3f-mesh") {
      const geo = resource.geometry as THREE.BufferGeometry & {
        boundsTree?: { dispose?: () => void };
      };
      geo.boundsTree = undefined;
      geo.dispose();
    } else if (resource.kind === "vtk-fem") {
      resource.polyData.delete();
    } else if (resource.kind === "vtk-vti") {
      resource.imageData.delete();
    }
  }

  private notify(): void {
    this.globalRevision += 1;
    for (const listener of this.listeners) {
      listener();
    }
  }
}

export const sceneRegistry = new SceneResourceRegistry(12);
