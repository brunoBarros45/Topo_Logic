# Changelog

All notable changes to **`Topo_Logic`** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-alpha] - 2026-11-18 — Milestone 2: 3D Linear Static FEM Engine

### Added
- **Volumetric Meshing (`src/topo_logic/infrastructure/mesh/`)**:
  - `VoxelH8Mesher`: 100% MIT pure-NumPy 2D-projected Z-column parity voxelizer generating structured `H8` meshes and outward-oriented boundary `Q4`/triangle surfaces without optional `rtree` dependencies.
  - `GmshCliMesher` & `CompositeVolumetricMesher`: External Gmsh CLI subprocess adapter (`C3D4` / `C3D10` MSH v2.2 parser with canonical quadratic node remapping), preserving strict MIT licensing of core `Topo_Logic`.
- **3D Linear Static Elasticity Engine (`src/topo_logic/infrastructure/fem/`)**:
  - `elasticity.py`: Isotropic Voigt constitutive matrix, vectorized uniform `H8` stiffness assembly (`2x2x2` Gauss), general `H8`, linear `C3D4`, and quadratic `C3D10` (4-point Hammer/Keast quadrature).
  - `boundary_conditions.py`: Client-agnostic `BoundaryRegion` resolution (`PlaneSelector`, `BoundingBoxSelector`, `TriangleSetSelector`, `CadFaceTagSelector`), rigid-body constraint validation, and consistent `Q4`/`T6`/`T3` Neumann force and pressure integration across multiple `LoadCase`s.
  - `linear_solvers.py`: Reusable `scipy.sparse.linalg.splu` Direct solver (`< 80k` DOFs) and `pyamg` Smoothed-Aggregation Preconditioned Conjugate Gradient (`>= 80k` DOFs or explicit `PCG_AMG`).
  - `postprocess.py` & `static_fem_solver.py`: Volume-weighted nodal Cauchy/Von Mises stress recovery, safety factor, global force & moment static equilibrium residual checks, and packed little-endian `Float32` binary field exports.
- **Application, Persistence & API**:
  - `GenerateMeshUseCase`, `RunStaticFemUseCase`, `SqliteMeshRepository` (`meshes` table).
  - Endpoints: `POST/GET /api/v1/projects/{id}/meshes`, `GET /api/v1/meshes/{id}/surface`, `POST /api/v1/projects/{id}/studies/fem`, `GET /api/v1/jobs/{id}/fem-summary`, and `GET /api/v1/jobs/{id}/fields/{load_case_id}`.
- **Verification & Benchmarks**:
  - Exact analytical uniaxial tension patch tests for both `H8` and `C3D10`, Timoshenko cantilever beam deflection benchmark (`< 5%` error), multi-loadcase Direct vs. `pyamg` PCG parity check, hollow-annulus cavity voxelization test, and end-to-end API/binary-buffer integration test.

## [0.1.0-alpha] - 2026-11-18 — Milestone 1: Architecture Foundation & STL Vertical Slice

### Added
- **Clean Hexagonal Architecture (`src/topo_logic/`)**:
  - `domain/`: Pure Python entities and invariants for units/axis conventions, suspicious-scale guards, isotropic materials, mesh diagnostics, client-agnostic `RegionSelector`s (including `CadFaceTagSelector` for Fusion 360), multi-loadcase `FemStudyConfig`, SIMP/OC/MMA + P-norm `TopOptStudyConfig`, unit-consistent `WeightSavingsMetrics` (mass in `g`/`kg` and `%` reduction), and immutable `JobRecord` state machine.
  - `application/`: `Protocol` ports (`GeometryImporterPort`, `MeshRepairPort`, `VolumetricMesherPort`, `FemSolverPort`, `OptimizerPort`, persistence, queue, event bus) and use cases (`ProjectService`, `IngestGeometryUseCase`, `JobService`).
  - `infrastructure/`: Binary/ASCII `.STL` importer & Tier-1 surface repairer (`trimesh`), local filesystem atomic artifact storage, WAL-mode SQLite repositories, thread-safe cancellation tokens, in-memory async event bus, and background job queue.
  - `interfaces/`: FastAPI REST & WebSocket API (`/api/v1/health`, `/api/v1/materials`, `/projects`, `/geometries/upload`, `/geometries/{id}/download`, `/jobs`, `/ws/jobs/{id}`) and `topo-logic` CLI (`info`, `serve`).
- **Documentation & ADRs**:
  - Comprehensive Spanish engineering, architecture, API contract, Fusion 360 integration, and maintenance documentation plus 5 ADRs under `docs/`.
  - `ROADMAP.md` including the Hybrid-API Fusion 360 Add-In plan.
- **Automated Verification Suite (`tests/`)**:
  - AST-based architectural boundary fitness test enforcing Clean Architecture layer rules.
  - Unit tests for domain invariants, unit conversions, and STL repair pipeline.
  - FastAPI integration tests covering project creation, binary/ASCII STL upload, diagnostics, scale warnings, error envelopes, and WebSocket snapshots.
