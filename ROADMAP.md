# `Topo_Logic` Roadmap

This roadmap tracks the evolution of **`Topo_Logic`** from architectural foundation through full 3D FEM, multi-constraint Topology Optimization, the decoupled Web Frontend, and the **Autodesk Fusion 360 Add-In**.

---

## Phase 0 — Repository & Engineering Foundation ✅ Done
- MIT license setup, contributor guidelines (`CONTRIBUTING.md`), and governance (`CODE_OF_CONDUCT.md`).
- Workspace engineering rules (`AGENTS.md`) and strict MIT/BSD vs. GPL/LGPL license hygiene boundaries.
- Domain-specific engineering skills (`.agents/skills/`) and read-only computational mechanics reference catalog (`references/`).

---

## Phase 1 — Hexagonal Architecture Foundation & `.STL` Vertical Slice ✅ Done
- **Pure Python 3.12+ Domain Layer** (`src/topo_logic/domain/`) with zero external dependencies:
  - Explicit consistent unit systems (`mm_N_MPa`, `m_N_Pa`), `+Z`/`+Y` axis convention, and suspicious-scale guard.
  - Isotropic material models & presets, client-agnostic `RegionSelector` union (`TriangleSetSelector`, `PlaneSelector`, `BoundingBoxSelector`, `CadFaceTagSelector`), multi-loadcase `LoadCase` definitions, OC/MMA + P-norm stress study configurations, `WeightSavingsMetrics` (`g`/`kg` & `%` reduction), and immutable `JobRecord` state machine.
- **Application Ports & Use Cases** (`src/topo_logic/application/`):
  - Strategy & repository `Protocol` boundaries for importers, repairers, meshers, solvers, optimizers, persistence, queues, and event streaming.
  - End-to-end `IngestGeometryUseCase`, `ProjectService`, and `JobService`.
- **Local-First, Cloud-Ready Infrastructure** (`src/topo_logic/infrastructure/`):
  - Binary & ASCII `.STL` validation (`TrimeshStlImporter`) and Tier-1 automated surface audit/repair (`TrimeshSurfaceRepairer`).
  - Atomic local filesystem artifact storage (`LocalFsArtifactStorage`) and WAL-mode SQLite persistence (`SqliteDatabase`).
  - Cooperative cancellation (`ThreadingCancellationToken`), background execution (`LocalJobQueue`), and async WebSocket pub/sub (`InMemoryEventBus`).
- **FastAPI Backend & CLI** (`src/topo_logic/interfaces/`):
  - OpenAPI REST endpoints (`/api/v1/health`, `/api/v1/materials`, `/projects`, `/geometries/upload`, `/geometries/{id}/download`, `/jobs`), WebSocket streaming (`/ws/jobs/{id}`), and `topo-logic` CLI (`info`, `serve`).
- **Maintainability Documentation & Tests**:
  - Spanish architecture, engineering, API contract, Fusion 360 blueprint, maintenance handbook, and 5 ADRs under `docs/`.
  - Automated AST architectural boundary fitness tests, domain unit tests, STL pipeline tests, and API integration tests.

---

## Phase 2 — 3D Linear Static FEM Engine (Multi-Loadcase) ✅ Done
- **Volumetric Meshing**:
  - 100% MIT structured hexahedral **`H8`** voxelizer for watertight `.STL` bodies.
  - Optional **`Gmsh` CLI subprocess adapter** (`VolumetricMesherPort`) for unstructured quadratic **`C3D10`** tetrahedral stress meshes without linking GPL `libgmsh` into the core MIT package.
- **Elasticity Solver & Multi-Loadcase Assembly**:
  - Vectorized sparse stiffness assembly ($\mathbf{K}$), symmetric Dirichlet imposition, and tributary-area consistent Neumann load integration across `LoadCase[]`.
  - Linear solver strategies: SciPy sparse direct solver (< ~80k DOFs) and `pyamg` Preconditioned Conjugate Gradient (> ~80k DOFs).
- **Post-Processing & Binary Fields**:
  - Nodal displacement vectors, Cauchy stress, Von Mises equivalent stress, safety factor, reaction forces, and global static equilibrium verification.
  - Compact `Float32` binary field download endpoints for high-speed WebGL/client visualization.
- **Engineering Benchmarks**:
  - Automated analytical verification suite: 3D uniaxial tension patch test, Euler-Bernoulli / Timoshenko cantilever beam deflection, and static equilibrium residuals ($< 10^{-6} \|\mathbf{F}\|$).

---

## Phase 3 — 3D Topology Optimization Engine (SIMP + OC & MMA + Stress) ✅ Done
- **Formulation & Filtering**:
  - Modified SIMP interpolation ($E_{\min} = 10^{-9} E_0$), multi-loadcase weighted compliance objective, sparse `cKDTree` cone density filter with exact adjoint chain-rule sensitivities, optional Smoothed Heaviside projection, and penalty continuation.
  - Non-design passive solid and passive void domains (`DesignZone`).
- **Optimizers & Stress Constraints**:
  - Optimality Criteria (**OC**) for fast single-volume-constraint compliance minimization.
  - Method of Moving Asymptotes (**MMA2007**, adapted strictly from MIT-licensed `pyMOTO` with preserved attribution) supporting multiple constraints and **P-norm Von Mises stress aggregation** (`StressConstraintConfig`) with adaptive scaling and exact adjoint sensitivities.
- **Live Streaming & Watertight Reconstruction**:
  - Real-time per-iteration WebSocket telemetry (`topopt.iteration`) and packed little-endian `Float32` density binary downloads.
  - 1-voxel zero-halo Marching Cubes (`scikit-image`) isosurface extraction + volume-preserving pure-SciPy Taubin smoothing + watertightness audit exporting `.STL` ready for manufacturing/CAD.
- **Benchmarks**:
  - FD sensitivity verification for filters & P-norm stress adjoint, analytical KKT quadratic verification for MMA, 3D cantilever OC convergence + watertight `.STL`, MMA stress-constrained + `PASSIVE_SOLID`, and multi-loadcase mirror-symmetry bridge benchmarks.

---

## Phase 4 — Multi-Format CAD, Binary Exchange Formats & Decoupled Web Frontend ✅ Done
- **Multi-Format Surface/CAD Importers (`CompositeGeometryImporter`)**:
  - Native MIT `.STL`, `.OBJ`, and `.PLY` ingestion (`TrimeshSurfaceImporter`) plus external `Gmsh` CLI subprocess adapter for `.STEP`/`.STP` (`GmshStepImporter`) preserving strict MIT core licensing.
- **Binary Scientific Exchange Formats (`src/topo_logic/infrastructure/exporters/`)**:
  - Pure-Python MIT compressed VTK XML writers (`.vtp` exterior FEM/surface PolyData for VTK.js, `.vti` 1-voxel zero-halo Fortran ImageData for TopOpt, `.vtu` full volumetric UnstructuredGrid for ParaView) and `.glb` glTF 2.0 previews.
- **Web Frontend (`frontend/` via `pnpm`)**:
  - **React 19 + TypeScript + Vite 7 + Tailwind CSS v4 + shadcn/ui + Lucide** with CAE Dark/Light theme and ES/EN i18n.
  - Off-React `SceneResourceRegistry` (LRU + `.dispose()`/`.delete()`), BVH dihedral flood-fill picking in **React Three Fiber / Three.js**, **VTK.js** scientific post-processing (colapsable XYZ clipping, 60 FPS `Float32` deformation warp + ghost wireframe, point probe, `vtkImageMarchingCubes`), synchronized camera bridge + Split Compare, TanStack Query + Zustand + WebSocket streaming, **Recharts** live/historical convergence + multi-simulation comparison, and **Vitest + RTL + Playwright** verification.

---

## Phase 5 — Autodesk Fusion 360 Add-In & Cloud Infrastructure 📋 Planned
- **Autodesk Fusion 360 Add-In (`integrations/fusion360/`) — Hybrid API Mode**:
  - Thin Python add-in (`adsk.core` / `adsk.fusion`) connecting to either an auto-launched local `topo-logic serve` daemon or a remote `Topo_Logic` server (avoiding dependency clashes inside Fusion's embedded Python).
  - Native B-Rep face selection mapped to `CadFaceTagSelector`, automatic `.STEP`/`.STL` export with unit metadata, embedded HTML Palette for study configuration and live WebSocket iteration monitoring, and direct re-import of reconstructed watertight `.STL` results as a Fusion `MeshBody`.
- **Cloud-Ready Infrastructure Adapters**:
  - Drop-in `ArtifactStoragePort` (S3/MinIO), repository adapters (PostgreSQL), `JobQueuePort` (Celery/Redis workers), and `EventPublisherPort` (Redis Pub/Sub).
- **Additive Manufacturing Extensions**:
  - Optional overhang constraints, symmetry planes, and minimum member thickness controls.
