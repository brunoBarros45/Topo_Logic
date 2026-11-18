---
name: threejs-fem-viewport
description: >-
  Build interactive Three.js / React Three Fiber 3D CAE viewports for uploading
  .STL and .OBJ models, selecting boundary-condition faces, visualizing FEM
  stress/displacement colormaps, and streaming live 3D topology optimization
  updates. Use when building the frontend 3D canvas, loaders, raycasting patch
  selection, clipping planes, or stress legend shaders.
---

# Three.js / R3F CAE Viewport for FEM & Topology Optimization

Deliver a responsive, physically legible engineering viewport for `.STL`/`.OBJ` preprocessing, boundary-condition picking, FEM post-processing, and live 3D Topology Optimization previews.

## 1. Model Ingestion, Framing & Coordinate Handling

- **Client-side preview**: Load uploaded `File`/`ArrayBuffer` immediately using `STLLoader` (binary + ASCII) or `OBJLoader` (`three/addons/loaders/...`) for instant preview while backend validation/meshing runs.
- **Normalize without mutating solver coordinates**: Compute `geometry.computeBoundingBox()` and `geometry.computeBoundingSphere()`. Do **not** silently rescale vertex coordinates without keeping the exact transform/unit metadata; instead frame the camera (`OrbitControls` target = bounding box center, camera distance from bounding sphere radius and `fov`) and size the reference grid & gizmo proportionally to the model scale.
- **Z-up vs Y-up**: CAD exports (`.STL` from SolidWorks/FreeCAD/Fusion) are usually `+Z` up, whereas Three.js defaults to `+Y` up. Wrap the scene model group in a single explicit orientation group (or set `camera.up.set(0, 0, 1)` consistently across `OrbitControls` and gizmo) so boundary-condition coordinates sent to the solver match world CAD coordinates 1:1.

## 2. Interactive Boundary Condition & Design-Zone Picking

Triangulated `.STL`/`.OBJ` meshes lack CAD B-Rep face IDs, so clicking a single triangle is useless to engineers:

1. **Dihedral-Angle Flood-Fill Patch Selection**:
   - Build a triangle adjacency map (shared edge -> neighboring triangles) once on geometry load (and index with `three-mesh-bvh` for fast raycasting on dense meshes).
   - When the user clicks triangle $t_0$ in **Face Select** mode, flood-fill across neighboring triangles whose face normal angle $\arccos(\mathbf{n}_i \cdot \mathbf{n}_j) \le \theta_{\text{crease}}$ (e.g., $15^\circ\text{–}30^\circ$, user-adjustable) to select an entire planar pad, bore cylinder, or boss automatically.
   - Also support **Box / Brush selection** and **Non-Design Region** tagging (preserve solid / keep-out void) for Topology Optimization.
2. **Clear Engineering Overlays**:
   - Render selected patches via an overlay `BufferGeometry` (with `polygonOffset` to prevent z-fighting).
   - Draw **Supports** (green/blue cones or tripod glyphs on constrained nodes/patches) and **Loads** (red/amber `ArrowHelper` or instanced 3D arrows aligned to force vector / face normal).
   - Ensure `OrbitControls` ignores drags starting over gizmos or while brush-selecting.

## 3. FEM Field Visualization (Von Mises, Displacement, Safety Factor)

- **Linear-Space Colormaps**:
  - Map scalar field $s_i \in [s_{\min}, s_{\max}]$ using perceptually uniform colormaps (**Turbo** or **Viridis**; avoid clipped jet rainbows where possible).
  - Write vertex colors as **linear RGB** into `geometry.setAttribute('color', new THREE.BufferAttribute(colorsFloat32, 3))` (Three.js r152+ manages sRGB output encoding automatically; converting hex/sRGB LUT stops via `.convertSRGBToLinear()` avoids washed-out midtones).
  - Alternatively, pass normalized scalar `aScalar` per vertex and evaluate the LUT + optional **discrete iso-contour bands** cleanly in a custom `ShaderMaterial` / `onBeforeCompile` fragment shader for razor-sharp stress bands without vertex-color interpolation muddiness.
- **Deformed Shape & Ghost Wireframe**:
  - Keep base positions `basePos` (`Float32Array`) and nodal displacement `disp` (`Float32Array`) separate; update `position` buffer via `pos[j] = basePos[j] + scaleFactor * disp[j]` and set `posAttr.needsUpdate = true` (recompute vertex normals if scale is large).
  - Render the undeformed shape as a low-opacity wireframe or semi-transparent ghost (`depthWrite: false`) behind the deformed result, plus a deformation animation toggle ($\alpha(t) = \alpha_{\max} \cdot \frac{1 - \cos(\omega t)}{2}$).
- **Synchronized Legend Colorbar**: Render an HTML/SVG legend overlay showing unit label (`MPa` / `mm`), min/max markers, customizable auto-vs-manual range clamping, and hover-probe readout (displaying exact interpolated stress/displacement at the hovered point).

## 4. Clipping Planes & Live TopOpt Streaming

- **Section / Clipping Planes**: Enable `renderer.localClippingEnabled = true` with interactive `X`/`Y`/`Z` slider planes (`THREE.Plane`) and optional stencil-cap shading so users can inspect internal Von Mises hotspots and internal cavities inside topology-optimized parts.
- **Streaming TopOpt Iterations**:
  - Receive compact binary payloads (`Float32Array` densities or indexed triangle buffers) rather than multi-megabyte JSON strings.
  - Reuse preallocated `InstancedMesh` (for voxel density thresholds $\tilde{\rho}_e \ge \tau$) or swap `BufferGeometry` only after explicitly calling `.dispose()` on superseded GPU geometries/materials/textures.
  - Monitor `renderer.info.memory` during rapid iteration previews to guarantee zero GPU memory leaks.

## 5. Verification Checklist

- [ ] Loading binary STL, ASCII STL, and OBJ models centers camera cleanly and displays zero console/WebGL warnings.
- [ ] Raycast + flood-fill selects planar/cylindrical patches accurately without z-fighting.
- [ ] Switching scalar fields (`Von Mises`, `Displacement`, `Safety Factor`) and deformation scale updates colors, geometry, and legend units consistently.
- [ ] Repeatedly uploading models or streaming 50+ TopOpt iterations does not monotonically grow `renderer.info.memory.geometries`.
