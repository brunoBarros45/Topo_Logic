import * as THREE from "three";

export interface TriangleAdjacency {
  triangleCount: number;
  neighbors: Int32Array[];
  normals: Float32Array;
}

const QUANTIZE_SCALE = 1e4;

/**
 * Builds edge-shared triangle adjacency and per-triangle unit normals once on mesh load.
 * Quantizes vertex coordinates so flood-fill works consistently on both indexed GLB and unindexed STL.
 */
export function buildTriangleAdjacency(geometry: THREE.BufferGeometry): TriangleAdjacency {
  const posAttr = geometry.getAttribute("position");
  if (!(posAttr instanceof THREE.BufferAttribute)) {
    return { triangleCount: 0, neighbors: [], normals: new Float32Array(0) };
  }

  const indexAttr = geometry.getIndex();
  const triangleCount = indexAttr
    ? Math.floor(indexAttr.count / 3)
    : Math.floor(posAttr.count / 3);
  if (triangleCount <= 0) {
    return { triangleCount: 0, neighbors: [], normals: new Float32Array(0) };
  }

  // Collapse coincident vertices by quantized position
  const spatialMap = new Map<string, number>();
  const vertToSpatial = new Int32Array(posAttr.count);
  let nextSpatialId = 0;

  for (let i = 0; i < posAttr.count; i++) {
    const qx = Math.round(posAttr.getX(i) * QUANTIZE_SCALE);
    const qy = Math.round(posAttr.getY(i) * QUANTIZE_SCALE);
    const qz = Math.round(posAttr.getZ(i) * QUANTIZE_SCALE);
    const key = `${qx},${qy},${qz}`;
    let id = spatialMap.get(key);
    if (id === undefined) {
      id = nextSpatialId++;
      spatialMap.set(key, id);
    }
    vertToSpatial[i] = id;
  }

  const normals = new Float32Array(triangleCount * 3);
  const edgeToTris = new Map<string, number[]>();

  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  const ab = new THREE.Vector3();
  const ac = new THREE.Vector3();
  const n = new THREE.Vector3();

  for (let t = 0; t < triangleCount; t++) {
    const i0 = indexAttr ? indexAttr.getX(t * 3) : t * 3;
    const i1 = indexAttr ? indexAttr.getX(t * 3 + 1) : t * 3 + 1;
    const i2 = indexAttr ? indexAttr.getX(t * 3 + 2) : t * 3 + 2;

    a.fromBufferAttribute(posAttr, i0);
    b.fromBufferAttribute(posAttr, i1);
    c.fromBufferAttribute(posAttr, i2);
    ab.subVectors(b, a);
    ac.subVectors(c, a);
    n.crossVectors(ab, ac);
    const len = n.length();
    if (len > 1e-12) {
      n.divideScalar(len);
    } else {
      n.set(0, 0, 1);
    }
    normals[t * 3] = n.x;
    normals[t * 3 + 1] = n.y;
    normals[t * 3 + 2] = n.z;

    const s0 = vertToSpatial[i0];
    const s1 = vertToSpatial[i1];
    const s2 = vertToSpatial[i2];
    const edges: [number, number][] = [
      [s0, s1],
      [s1, s2],
      [s2, s0],
    ];
    for (const [u, v] of edges) {
      if (u === v) continue;
      const eKey = u < v ? `${u}:${v}` : `${v}:${u}`;
      let list = edgeToTris.get(eKey);
      if (!list) {
        list = [];
        edgeToTris.set(eKey, list);
      }
      list.push(t);
    }
  }

  const neighborSets: Set<number>[] = Array.from({ length: triangleCount }, () => new Set());
  for (const tris of edgeToTris.values()) {
    if (tris.length < 2) continue;
    for (let i = 0; i < tris.length; i++) {
      for (let j = i + 1; j < tris.length; j++) {
        const ti = tris[i];
        const tj = tris[j];
        neighborSets[ti].add(tj);
        neighborSets[tj].add(ti);
      }
    }
  }

  const neighbors = neighborSets.map((set) => Int32Array.from(set));
  return { triangleCount, neighbors, normals };
}

/**
 * Flood-fills across neighboring triangles whose dihedral angle <= creaseAngleDeg.
 */
export function floodFillTriangles(
  adjacency: TriangleAdjacency,
  seedTriangle: number,
  creaseAngleDeg: number,
): number[] {
  if (
    seedTriangle < 0 ||
    seedTriangle >= adjacency.triangleCount ||
    adjacency.triangleCount === 0
  ) {
    return [];
  }

  const clampedDeg = Math.min(Math.max(creaseAngleDeg, 0.5), 89.5);
  const minDot = Math.cos((clampedDeg * Math.PI) / 180.0);

  const visited = new Uint8Array(adjacency.triangleCount);
  const queue: number[] = [seedTriangle];
  visited[seedTriangle] = 1;

  const { normals, neighbors } = adjacency;
  const result: number[] = [];

  for (let head = 0; head < queue.length; head++) {
    const cur = queue[head];
    result.push(cur);

    const nx = normals[cur * 3];
    const ny = normals[cur * 3 + 1];
    const nz = normals[cur * 3 + 2];

    const nbrs = neighbors[cur];
    for (let i = 0; i < nbrs.length; i++) {
      const nb = nbrs[i];
      if (visited[nb]) continue;
      const dot =
        nx * normals[nb * 3] + ny * normals[nb * 3 + 1] + nz * normals[nb * 3 + 2];
      if (dot >= minDot) {
        visited[nb] = 1;
        queue.push(nb);
      }
    }
  }

  result.sort((x, y) => x - y);
  return result;
}

/**
 * Builds packed unindexed XYZ Float32 vertices for rendering selected triangle patches.
 */
export function extractPatchPositions(
  geometry: THREE.BufferGeometry,
  triangleIndices: readonly number[],
): Float32Array {
  const posAttr = geometry.getAttribute("position");
  if (!(posAttr instanceof THREE.BufferAttribute) || triangleIndices.length === 0) {
    return new Float32Array(0);
  }
  const indexAttr = geometry.getIndex();
  const out = new Float32Array(triangleIndices.length * 9);

  for (let k = 0; k < triangleIndices.length; k++) {
    const t = triangleIndices[k];
    const i0 = indexAttr ? indexAttr.getX(t * 3) : t * 3;
    const i1 = indexAttr ? indexAttr.getX(t * 3 + 1) : t * 3 + 1;
    const i2 = indexAttr ? indexAttr.getX(t * 3 + 2) : t * 3 + 2;

    const base = k * 9;
    out[base] = posAttr.getX(i0);
    out[base + 1] = posAttr.getY(i0);
    out[base + 2] = posAttr.getZ(i0);
    out[base + 3] = posAttr.getX(i1);
    out[base + 4] = posAttr.getY(i1);
    out[base + 5] = posAttr.getZ(i1);
    out[base + 6] = posAttr.getX(i2);
    out[base + 7] = posAttr.getY(i2);
    out[base + 8] = posAttr.getZ(i2);
  }
  return out;
}
