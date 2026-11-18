# Contributing to `Topo_Logic`

Thank you for helping build **`Topo_Logic`**, an open-source web platform for 3D Finite Element Analysis (FEM) and Topology Optimization!

## Getting Started

1. Fork the repository and create a topic branch from `main` (`feat/...`, `fix/...`, `docs/...`).
2. Keep changes focused, documented, and accompanied by verification tests (especially analytical benchmarks for FEM/TopOpt changes).
3. Open a Pull Request describing the motivation, numerical or UI changes, and test results.

## License Hygiene (Strict Requirement)

`Topo_Logic` is licensed under the **MIT License**. To keep the project legally clean for all downstream users:

- **Do NOT paste or adapt code** from `GPL`, `AGPL`, `LGPL`, non-commercial (e.g., PolyForm Noncommercial), or unlicensed repositories into this codebase.
- Only include or adapt code from **MIT / BSD / Apache-2.0** compatible sources, preserving their original copyright and license headers.
- Never commit third-party reference dumps or large binary simulation outputs (`*.vtu`, `*.msh`, `*.frd`).

## Optional Local Reference & Agent Setup

The project includes workspace guidelines in [`AGENTS.md`](./AGENTS.md) and three project-specific engineering skills under `.agents/skills/`:

- `stl-obj-mesh-pipeline`
- `fem-topopt-engine`
- `threejs-fem-viewport`

If you want to mirror the local read-only study library (`references/`, gitignored), you can clone the reference repositories inside `references/`:

```bash
mkdir references && cd references
git clone --depth 1 https://github.com/williamhunter/topy.git
git clone --depth 1 https://github.com/williamhunter/topy.wiki.git topy-wiki
git clone --depth 1 https://github.com/jihoonkim888/PyTopo3D.git
git clone --depth 1 https://github.com/aatmdelissen/pyMOTO.git
git clone --depth 1 https://github.com/kinnala/scikit-fem.git
```

## Reporting Issues

When filing a bug report for meshing, FEM, or Topology Optimization, please attach:
- Input format and unit system (`mm/MPa` vs `m/Pa`)
- Mesh statistics (node/element count, watertight status)
- Boundary conditions and material properties ($E$, $\nu$)
- Expected vs observed results
