# Local Reference Codebase Catalog (`c:\AppWebFem\references\`)

Read-only local reference library cloned under `c:\AppWebFem\references\` (excluded from Git via `.gitignore`). Use this catalog to locate verified implementations, element stiffness templates, solvers, filters, and benchmarks instead of reinventing numerical building blocks from scratch.

---

## 1. License & Reuse Policy

| Directory | Upstream Repository | License | Allowed Use in `Topo_Logic` |
| :--- | :--- | :--- | :--- |
| `references/topy` | `williamhunter/topy` | **MIT** | **Reusable / Adaptable** (preserve MIT attribution & copyright notice). |
| `references/topy-wiki` | `williamhunter/topy.wiki` | **MIT** | **Documentation / Benchmarks** offline reference. |
| `references/PyTopo3D` | `jihoonkim888/PyTopo3D` | **MIT** | **Reusable / Adaptable** (preserve MIT attribution & copyright notice). |
| `references/pyMOTO` | `aatmdelissen/pyMOTO` | **MIT** | **Reusable / Adaptable** (preserve MIT attribution & copyright notice). |
| `references/scikit-fem` | `kinnala/scikit-fem` | **BSD-3-Clause** | **Reusable / Adaptable** (or import directly as a Python dependency; preserve BSD-3 notice if adapting snippets). |
| `references/TopOpt-MMA-Python` | `arjendeetman/TopOpt-MMA-Python` | No explicit LICENSE file (`mmapy` dep is **GPL-3.0**) | **Algorithmic Study Only** — DO NOT copy-paste code or add `mmapy` as a dependency of MIT `Topo_Logic`. |
| `references/TopOpt_in_PETSc` | `topopt/TopOpt_in_PETSc` | **LGPL-2.1** (C++ / MPI / PETSc) | **Algorithmic Study Only** — DO NOT copy-paste source into MIT `Topo_Logic`; use for PDE filter, continuation, and VTU architecture study. |

---

## 2. Engineering Task-to-File Lookup Map

### 3D Element Stiffness & Vectorized Sparse Assembly
- **Precomputed 3D Hex8 (`H8`) and 18-DOF / Higher-order Stiffness Matrices (`MIT`)**:
  - `references/topy/topy/data/H8_K.py`
  - `references/topy/topy/data/H18B_K.py`
  - `references/topy/topy/elements.py`
  - `references/PyTopo3D/pytopo3d/utils/stiffness.py`
  - `references/PyTopo3D/pytopo3d/utils/assembly.py`
- **Unstructured 3D Tetrahedral (`C3D4` / `C3D10`) & Hexahedral Linear Elasticity (`BSD-3-Clause`)**:
  - `references/scikit-fem/skfem/models/elasticity.py` (Lamé linear elasticity bilinear forms)
  - `references/scikit-fem/skfem/element/element_tet/` (`ElementTetP1`, `ElementTetP2`)
  - `references/scikit-fem/skfem/assembly/` (vectorized sparse matrix assembly)
  - `references/scikit-fem/skfem/io/meshio.py` (`meshio` / Gmsh import bridge)

### STL Design-Space Ingestion, Voxelization & Boundary Conditions
- **`.STL` Design Space & Keep-Out Obstacle Voxelization (`MIT`)**:
  - `references/PyTopo3D/pytopo3d/utils/import_design_space.py`
  - `references/PyTopo3D/pytopo3d/utils/obstacles.py`
  - `references/PyTopo3D/pytopo3d/preprocessing/geometry.py`
  - `references/PyTopo3D/pytopo3d/utils/axis_convention.py`
  - `references/PyTopo3D/pytopo3d/utils/boundary.py`

### Optimizers (OC & MMA), Filters & Stress Aggregation
- **MIT-Licensed Optimality Criteria (OC) & Method of Moving Asymptotes (MMA)**:
  - `references/pyMOTO/pymoto/common/mma.py` (clean MIT MMA implementation in Python/NumPy)
  - `references/pyMOTO/pymoto/common/optimizers.py`
  - `references/PyTopo3D/pytopo3d/utils/oc_update.py`
  - `references/topy/topy/optimisation.py`
- **Density / Sensitivity Filters, Heaviside Projection & Grey-Scale Suppression (`MIT`)**:
  - `references/pyMOTO/pymoto/modules/filter.py`
  - `references/PyTopo3D/pytopo3d/utils/filter.py`
  - `references/topy/topy/topology.py` (sensitivity filtering, `etaopt` continuation, grey-scale filter `gsf`)
- **P-Norm Stress / Displacement Aggregation (`MIT`)**:
  - `references/pyMOTO/pymoto/modules/aggregation.py`
- **Iterative & Sparse Linear Solvers (`MIT`)**:
  - `references/pyMOTO/pymoto/solvers/iterative.py`
  - `references/pyMOTO/pymoto/solvers/sparse.py`
  - `references/PyTopo3D/pytopo3d/utils/solver.py`

### Post-Processing, Export & Validation Benchmarks
- **3D Benchmark Problems & Convergence Reference**:
  - `references/topy/examples/mbb_beam/beam_3d_exp_gsf.tpd`
  - `references/topy/examples/cantilever/cantilvr_3d_etaopt_gsf.tpd`
  - `references/topy/examples/torque_arm/torque_arm_3d_etaopt_gsf.tpd`
  - `references/topy/examples/trestle/trestle_3d_etaopt_gsf.tpd`
  - `references/topy-wiki/Tutorials.md`
  - `references/PyTopo3D/pytopo3d/utils/export.py` & `pytopo3d/utils/metrics.py`
- **Algorithmic Study References (Conceptual Only — Do Not Copy)**:
  - `references/TopOpt-MMA-Python/src/topopt.py` — side-by-side OC vs MMA setup with volume inequality constraint
  - `references/TopOpt_in_PETSc/PDEFilter.cc` — Helmholtz PDE density filter math (faster/cleaner than dense cone matrices on very large 3D grids)
  - `references/TopOpt_in_PETSc/LinearElasticity.cc` & `TopOpt.cc` — 3D multigrid linear elasticity & $\beta$-continuation schedule
  - `references/TopOpt_in_PETSc/bin2vtu_v3.py` & `makevtu_v3.py` — VTU binary output layout concepts
