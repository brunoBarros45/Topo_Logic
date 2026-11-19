# AGENTS.md — `Topo_Logic` Workspace Rules

**`Topo_Logic`** is an Open-Source (**MIT**) web application for 3D Finite Element Analysis (FEM) and 3D Topology Optimization supporting uploaded `.STL`, `.OBJ`, `.PLY`, and `.STEP` models.

---

## 1. Repository & Reference Library Rules

- **`references/` is strictly read-only and gitignored**: Never edit, format, or commit any file inside `c:\AppWebFem\references\`.
- **Keep third-party skills out of Git**: The 15 downloaded community skills under `.agents/skills/` are active locally for agent assistance and ignored by `.gitignore`. Only commit original `Topo_Logic` project code, docs, and the 3 workspace-specific skills (`stl-obj-mesh-pipeline`, `fem-topopt-engine`, `threejs-fem-viewport`).

---

## 2. Strict Open-Source (MIT) License Hygiene

- **Permissive reuse allowed (preserve copyright & attribution)**:
  - `references/topy` (**MIT**)
  - `references/topy-wiki` (**MIT**)
  - `references/PyTopo3D` (**MIT**)
  - `references/pyMOTO` (**MIT**)
  - `references/scikit-fem` (**BSD-3-Clause**)
- **Algorithmic study ONLY — NEVER copy-paste code or add copyleft dependencies**:
  - `references/TopOpt-MMA-Python` (no explicit LICENSE file; depends on `mmapy`, which is **GPL-3.0**)
  - `references/TopOpt_in_PETSc` (**LGPL-2.1**)
  - `.agents/skills/parametric-3d-printing` (`flowful-ai/cad-skill`, **PolyForm Noncommercial 1.0.0**)

---

## 3. Active MCP & Skill Routing

- **Documentation & Reasoning MCPs**:
  - Use `context7_context7` (`resolve-library-id` / `query-docs`) for up-to-date FastAPI, NumPy, SciPy, Three.js, React Three Fiber, and Gmsh API docs.
  - Use `sequential-thinking` for complex numerical pipeline design, coordinate/unit audits, and multi-step debugging.
  - Use `github` MCP for GitHub repo/PR/issue workflows (once authenticated).
- **CAD / Geometry Inspection MCPs**:
  - `freecad-mcp-pro` (live FreeCAD 1.0 + CalculiX FEM verification) and `freecad-mcp` (offline FreeCAD Python API docs).
  - `blender` (`mcp-for-blender`, mesh inspection/export when Blender is active).
- **Workspace Skills (`.agents/skills/`)**:
  - **Mesh Ingestion, Repair & Gmsh**: `stl-obj-mesh-pipeline`, `hpc-gmsh`.
  - **FEM & Topology Optimization Engine**: `fem-topopt-engine` (and its `references/reference-codebase-catalog.md`), `topo2stl`, `hpc-calculix`, `hpc-fenics`, `hpc-paraview`.
  - **3D Web Viewport & R3F**: `threejs-fem-viewport`, `threejs-fundamentals`, `threejs-geometry`, `threejs-loaders`, `threejs-materials`, `threejs-shaders`, `threejs-interaction`, `threejs-performance`, `threejs-react-three-fiber`, plus `modern-web-guidance`.
  - **Parametric CAD Test Fixtures**: `freecad-scripts` (avoid copying noncommercial `parametric-3d-printing` files into repo source).

---

## 4. Git Workflow (`main` + `develop` + Conventional Commits)

- **Permanent Branches**:
  - `main`: Stable releases only. **NEVER commit or push directly to `main`**; updates arrive exclusively via GitHub Pull Request from `develop` (plus annotated SemVer release tag, e.g. `v0.2.0-alpha`).
  - `develop`: Parallel active integration branch where all completed work converges.
- **Topic / Feature Branches**:
  - Always branch from up-to-date `develop` using prefixes: `feat/<name>`, `fix/<name>`, `docs/<name>`, `refactor/<name>`, `chore/<name>`, or `ci/<name>`.
- **Atomic Conventional Commits**:
  - Format: `<type>(<scope>): <imperative English summary>`.
  - Allowed types: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`, `chore`.
  - Standard scopes: `project`, `domain`, `application`, `mesh`, `fem`, `topopt`, `storage`, `api`, `cli`, `docs`, `ci`, `workflow`, `frontend`, `fusion360`.
- **Milestone / Change Closure Cadence**:
  - Run `ruff check src tests`, `mypy src/topo_logic`, and `pytest -v` before merging.
  - Merge topic branch into `develop` with `--no-ff`, delete the temporary topic branch, and run `git push origin develop` after every milestone or major change.
