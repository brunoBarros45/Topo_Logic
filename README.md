# Topo_Logic

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![Architecture: Hexagonal](https://img.shields.io/badge/Architecture-Hexagonal%20%2F%20Clean-2ea44f.svg)](./docs/arquitectura.md)

**`Topo_Logic`** is an open-source (**MIT**) computational mechanics platform for **3D Finite Element Analysis (FEM)** and **3D Topology Optimization**, architected as a decoupled **Python core engine + FastAPI backend** serving multiple clients (a future Web 3D CAE Viewport, CLI workflows, and a planned **Autodesk Fusion 360 Add-In**).

> **Current Status:** **Milestone 2 Complete (`v0.2.0a0`)** — 3D Linear Static FEM Engine (multi-loadcase `H8` + `C3D4`/`C3D10`, `splu` Direct & `pyamg` PCG solvers, Von Mises / safety factor / equilibrium checks, packed `Float32` binary fields, and analytical patch/cantilever benchmarks) implemented and passing. Phase 3 (3D Topology Optimization SIMP/OC/MMA) is next.

---

## Project Progress Tracker

| Phase | Milestone | Status | Summary |
| :--- | :--- | :--- | :--- |
| **Phase 0** | Repository & Engineering Setup | **Done** | MIT license, `AGENTS.md`, engineering skills, read-only mechanics reference catalog |
| **Phase 1** | **Architecture Foundation & `.STL` Vertical Slice** | **Done** | Hexagonal architecture, pure domain (multi-loadcase FEM + OC/MMA stress TopOpt + `WeightSavingsMetrics`), `.STL` diagnostics & Tier-1 repair, SQLite + LocalFS, FastAPI (`/api/v1/materials`, upload/download, WS) + CLI, Spanish `docs/` + ADRs |
| **Phase 2** | **3D Linear Static FEM Engine** | **Done** | Pure-NumPy `H8` Z-column parity voxelizer & optional `Gmsh` CLI `C3D4`/`C3D10` adapter, consistent `Q4`/`T6`/`T3` traction integration, vectorized sparse assembly, Direct (`splu`) & `pyamg` PCG solvers, Von Mises / displacement / safety factor / equilibrium checks, `Float32` binary field endpoints, and analytical benchmarks (26 tests passing) |
| **Phase 3** | **3D Topology Optimization (SIMP + OC/MMA)** | **Planned** | Cone/Heaviside filtering, multi-loadcase compliance (OC), P-norm stress constraints (MIT MMA), live WebSocket iteration streaming, watertight Marching Cubes + Taubin `.STL` export |
| **Phase 4** | **Multi-Format CAD & Web Frontend** | **Planned** | `.OBJ`, `.PLY`, `.STEP` importers + interactive 3D Web Viewport (flood-fill face picking, colormaps, deformed ghost mesh, XYZ clipping) |
| **Phase 5** | **Fusion 360 Add-In & Cloud Adapters** | **Planned** | Hybrid-API Python Fusion 360 Add-In (`CadFaceTagSelector`, local/remote server mode, live Palette, MeshBody re-import) + S3/Postgres/Redis Cloud adapters |

See [`ROADMAP.md`](./ROADMAP.md) for the full multi-phase technical plan and [`CHANGELOG.md`](./CHANGELOG.md) for release notes.

---

## Architecture Overview

`Topo_Logic` enforces **Clean / Hexagonal Architecture (Ports & Adapters)** with **Local-First, Cloud-Ready** infrastructure:

```mermaid
flowchart TB
    subgraph Clients["Decoupled Clients (OpenAPI + WebSocket + Binary Float32)"]
        WEB["Web Frontend (Phase 4)"]
        FUSION["Fusion 360 Add-In (Phase 5 Roadmap)"]
        CLI["CLI (topo-logic)"]
    end

    subgraph Interfaces["Interfaces Layer"]
        API["FastAPI REST + WebSocket"]
        CLICMD["CLI Entrypoint"]
    end

    subgraph Application["Application Layer"]
        UC["Use Cases: ProjectService | IngestGeometryUseCase | GenerateMeshUseCase | RunStaticFemUseCase | JobService"]
        PORTS["Protocol Ports: Importer | Repairer | Mesher | Solver | Optimizer | Storage | Repo | Queue | EventBus"]
    end

    subgraph Domain["Pure Domain Layer (Zero External Dependencies)"]
        DOM["Units & Scale Guard | Materials | Geometry | Boundary & LoadCases | Study Configs | Job State Machine"]
    end

    subgraph Infrastructure["Infrastructure Layer (Swappable Adapters)"]
        MESH["TrimeshStlImporter | TrimeshSurfaceRepairer | VoxelH8Mesher | GmshCliMesher"]
        FEM["StaticFemSolver (H8/C3D4/C3D10 | splu & pyamg PCG | Float32 Fields)"]
        STORE["LocalFsArtifactStorage | SqliteRepositories (WAL)"]
        EXEC["InMemoryEventBus | LocalJobQueue"]
    end

    WEB & FUSION & CLI --> API
    CLI --> CLICMD
    API & CLICMD --> UC
    UC --> DOM
    UC -.-> PORTS
    MESH & FEM & STORE & EXEC -.implements.-> PORTS
```

---

## Core Engineering Capabilities

- **3D Surface Ingestion & Repair (`.STL` in Phase 1; `.OBJ`/`.PLY`/`.STEP` planned)**:
  - Binary and ASCII `.STL` validation, tolerance-based vertex merging, degenerate/duplicate face cleanup, hole filling, normal/winding repair, watertightness & non-manifold edge audit, and automatic unit-scale sanity checks (`mm_N_MPa` vs. `m_N_Pa`).
- **Client-Agnostic Boundary Conditions & Multi-Loadcase Domain**:
  - `TriangleSetSelector` (Web viewport flood-fill), `PlaneSelector` & `BoundingBoxSelector` (CLI & analytical benchmarks), and `CadFaceTagSelector` (`.STEP` & Fusion 360 B-Rep faces).
  - Supports multiple weighted `LoadCase` definitions and non-design solid/void `DesignZone` tags.
- **3D FEM & SIMP Topology Optimization Domain Contracts**:
  - Isotropic material library (`GET /api/v1/materials`: `Steel AISI 1020`, `Aluminum 6061-T6`, `Titanium Ti-6Al-4V`, `PLA`, `PETG`) with automatic unit conversion.
  - Configured for both **Optimality Criteria (OC)** compliance minimization and **MMA + P-norm Von Mises stress-constrained** optimization, plus unit-consistent `WeightSavingsMetrics` (mass in `g`/`kg` and `%` reduction).

---

## Quickstart (Local Development)

### 1. Create a Virtual Environment & Install (Python 3.11+)

```powershell
# Using Python 3.12
python3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -e ".[dev]"
```

### 2. Inspect CLI & Start the Backend API

```powershell
.\.venv\Scripts\topo-logic.exe info
.\.venv\Scripts\topo-logic.exe serve --host 127.0.0.1 --port 8000
```

Interactive OpenAPI / Swagger documentation is available at `http://127.0.0.1:8000/docs`.

### 3. Run Quality Checks & Tests

```powershell
.\.venv\Scripts\pytest.exe -v
.\.venv\Scripts\mypy.exe src/topo_logic
.\.venv\Scripts\ruff.exe check src tests
```

---

## Technical Documentation (Spanish / Documentación de Mantenimiento)

Comprehensive architecture, mathematical, API, and maintenance guides are maintained in Spanish under [`docs/`](./docs/README.md):

- [`docs/README.md`](./docs/README.md) — Documentation index & onboarding guide
- [`docs/arquitectura.md`](./docs/arquitectura.md) — Hexagonal architecture, design patterns, dependency rules, and Local-to-Cloud migration guide
- [`docs/flujo-ingenieria.md`](./docs/flujo-ingenieria.md) — Unit consistency, `.STL` repair pipeline, 3D FEM, SIMP (OC/MMA + P-norm stress), and watertight reconstruction
- [`docs/contrato-api.md`](./docs/contrato-api.md) — Client-agnostic REST, WebSocket, and binary `Float32` contracts
- [`docs/integracion-fusion360.md`](./docs/integracion-fusion360.md) — Architecture blueprint for the future Hybrid-API Fusion 360 Add-In
- [`docs/guia-mantenimiento.md`](./docs/guia-mantenimiento.md) — Developer handbook & step-by-step extension recipes
- [`docs/adr/`](./docs/adr/0001-arquitectura-hexagonal-python.md) — Architecture Decision Records (`0001`–`0005`)

---

## Inspirational Open-Source Ecosystem & License Hygiene

`Topo_Logic` is released under the [**MIT License**](./LICENSE). To preserve clean MIT licensing for all downstream users, reusable code is adapted solely from permissive **MIT / BSD** libraries (`ToPy`, `PyTopo3D`, `pyMOTO`, `scikit-fem`, `trimesh`, `pyamg`), while copyleft projects (`TopOpt_in_PETSc` LGPL-2.1, `mmapy` GPL-3.0) serve strictly for conceptual algorithmic study. Optional `Gmsh` meshing in Phase 2 runs exclusively as an external CLI subprocess adapter.
