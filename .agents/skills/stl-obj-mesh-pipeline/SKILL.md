---
name: stl-obj-mesh-pipeline
description: >-
  Ingest, validate, repair, scale, and volumetrically mesh uploaded 3D surface
  models (.STL, .OBJ, .PLY, .STEP) for finite element analysis (FEM) and
  topology optimization. Use when implementing 3D file upload endpoints, mesh
  repair pipelines, Gmsh tetrahedral/hexahedral meshing, unit normalization,
  or surface-patch to volume-node mapping.
---

# STL / OBJ Mesh Validation, Repair & Volumetric Meshing Pipeline

Turn arbitrary user-uploaded `.STL`, `.OBJ`, `.PLY`, and `.STEP` files into valid, positively oriented 3D finite element meshes while maintaining strict unit consistency and boundary face mapping.

## 1. Consistent Unit System & Sanity Checks

Always force an explicit, documented unit system before building stiffness matrices or applying loads:

| Quantity | SI (Meters) | Engineering (Millimeters) |
| :--- | :--- | :--- |
| Length | `m` | `mm` |
| Force | `N` | `N` |
| Stress / Young's Modulus ($E$) | `Pa` ($\text{N}/\text{m}^2$) | `MPa` ($\text{N}/\text{mm}^2$) |
| Density ($\rho$) | `kg/m^3` | `tonne/mm^3` ($10^{-12}\text{ kg/mm}^3$) |

- **Suspicious-scale guard**: `.STL` and `.OBJ` files carry no standardized unit metadata. Compute the bounding-box diagonal $D$ on upload. If the user selects `meters` and $D > 20$ (typical of a millimeter CAD export of a $100\text{ mm}$ bracket) or selects `millimeters` and $D < 1$, surface an immediate unit-conversion warning/toggle (`× 0.001` or `× 1000`) rather than silently solving with a $10^9\times$ stiffness error.
- **Coordinate normalization**: Record the original centroid/offset if exported back to CAD, and ensure consistent right-handed axes (`+Z` up or `+Y` up explicitly tagged in API metadata).

## 2. Surface Mesh Diagnostics & Repair (`.STL` / `.OBJ` / `.PLY`)

Before passing a surface mesh to a 3D tetrahedral mesher, run automated diagnostics (e.g., via `trimesh`, `pymeshfix`, `pymeshlab`, or `open3d`):

1. **Merge duplicate vertices** (`mesh.merge_vertices()`): ASCII/binary STLs store unindexed triangles (3 separate vertices per facet). Merge vertices within tolerance (e.g., $10^{-6} \cdot D$) so topology and watertightness checks work.
2. **Check topology & geometry**:
   - Connected components count (reject or ask user to select/union disjoint floating islands).
   - `is_watertight` and Euler characteristic / boundary edges (holes where edge degree == 1).
   - Non-manifold edges (edge degree > 2) or non-manifold vertices.
   - Degenerate zero-area triangles and self-intersections.
   - Consistent outward winding (`mesh.fix_normals()`, positive enclosed volume $V > 0$).
3. **Repair & fallback ladder**:
   - **Tier 1 (Clean / Minor gaps)**: `merge_vertices` -> remove degenerate/duplicate faces -> fill small holes (`trimesh.repair.fill_holes` or `pymeshfix.MeshFix`) -> `fix_normals`.
   - **Tier 2 (Self-intersecting / Multi-shell CAD export)**: Voxel remesh / winding-number surface extraction (e.g., OpenVDB / `pymeshlab` / `manifold3d` / signed-distance marching cubes) followed by quadric decimation while preserving sharp creases where needed.
   - Always return a diagnostic report to the UI (`triangle_count`, `watertight`, `volume`, `bounds`, `repaired_holes`, `warnings`).

## 3. Volumetric Tetrahedral Meshing with Gmsh Python API

When meshing a repaired `.STL`/`.OBJ` surface for FEM:

1. **Direct B-Rep `.STEP`/`.IGES`**: Import via `gmsh.model.occ.importShapes(path)`, `gmsh.model.occ.synchronize()`, and use `MeshSizeMin`/`MeshSizeMax` or `Mesh.MeshSizeFromCurvature`.
2. **Triangulated `.STL`/`.OBJ`**:
   - Call `gmsh.merge(stl_path)`.
   - Classify planar/curved regions by dihedral angle so Gmsh can reconstruct boundary curves and surfaces cleanly:
     ```python
     angle_rad = math.radians(40.0)
     gmsh.model.mesh.classifySurfaces(angle_rad, boundary=True, forReparametrization=True, curveAngle=math.radians(180))
     gmsh.model.mesh.createGeometry()
     surfaces = gmsh.model.getEntities(2)
     loop = gmsh.model.geo.addSurfaceLoop([s[1] for s in surfaces])
     gmsh.model.geo.addVolume([loop])
     gmsh.model.geo.synchronize()
     ```
   - If `createGeometry()` fails on noisy STL triangulations (e.g., high curvature / skinny triangles), skip parametrization (`forReparametrization=False`) or remesh the input surface first, or use a background voxel/hexahedral Cartesian grid inside the watertight STL via signed-distance / inside-outside ray test for fast Topology Optimization.
3. **Element order & sizing**:
   - Use **C3D10** (quadratic 10-node tetrahedra, `gmsh.option.setNumber("Mesh.ElementOrder", 2)`) for accurate stress recovery in linear static FEM (linear C3D4 tetrahedra suffer volumetric locking in bending unless heavily refined).
   - Use **C3D4** or uniform **H8** voxel meshes for fast iterative Topology Optimization where speed per iteration dominates.
   - Set `Mesh.Optimize = 1` and `Mesh.OptimizeNetgen = 1` (or `HXT` 3D algorithm) to eliminate sliver tetrahedra.

## 4. Mapping Web Viewport Picks to Volume Mesh Boundary Conditions

User clicks in Three.js happen on the **display surface triangles**, which may differ from the Gmsh volume mesh boundary after reparametrization or repair:

- **Preferred architecture**: Serve the **meshed boundary surface triangles** (extracted directly from the volumetric mesh exterior faces, preserving exact `volume_node_id` and `surface_face_tag`) back to the Three.js viewport once meshing completes, OR map uploaded triangle patches to volume boundary nodes via spatial KD-tree / normal-filtered surface proximity (`scipy.spatial.cKDTree`).
- Store boundary groups cleanly so both Dirichlet constraints (supports) and Neumann tractions (forces/pressures) map deterministically to node IDs and oriented triangle facets.

## 5. Verification Checklist

Before handing any mesh to the FEM or TopOpt solver, assert:
- [ ] `num_nodes > 0` and `num_elements > 0`.
- [ ] Total enclosed volume matches the repaired surface volume within $< 1\%$ (no missing cavity or inverted shell).
- [ ] Minimum element scaled Jacobian / quality metric $> 0$ (zero inverted/negative-volume tetrahedra).
- [ ] Every boundary patch has at least 3 non-collinear boundary nodes (for constraints) or positive surface area (for distributed tractions).
