---
name: fem-topopt-engine
description: >-
  Design, implement, and verify 3D linear static Finite Element Analysis (FEM)
  and 3D Topology Optimization (SIMP and BESO) backends with async job
  execution and live iteration streaming. Use when building elasticity solvers,
  boundary-condition assemblers, sensitivity filters, Optimality Criteria or
  MMA updates, isosurface STL extraction, or engineering verification tests.
---

# 3D FEM & Topology Optimization Engine

Build numerically sound, memory-safe 3D linear static FEM and Topology Optimization (SIMP / BESO) services suitable for interactive web applications.

## 1. 3D Linear Static Elasticity Solver

### Element Formulation & Assembly
- **Linear Elasticity**: Isotropic Hooke's law parameterized by Young's modulus $E > 0$ and Poisson's ratio $0 \le \nu < 0.5$. Build the $6 \times 6$ constitutive matrix $\mathbf{D}$ in Voigt notation `[xx, yy, zz, yz, xz, xy]`.
- **Element Selection**:
  - **FEM Stress Analysis**: Prefer quadratic **C3D10** tetrahedra (or **H8** / **H20** hexahedra) to avoid shear/volumetric locking in bending.
  - **Topology Optimization**: Uniform structured **H8** voxel grids allow sharing a single precomputed $24 \times 24$ element stiffness template $\mathbf{K}_0$ scaled by element stiffness $E(\rho_e)$, making assembly orders of magnitude faster; for unstructured tetrahedral domains, vectorize $\mathbf{K}_e$ assembly using NumPy/SciPy COO->CSR sparse builders (never Python `for` loops assembling into dense matrices).
- **Boundary Conditions & Loads**:
  - **Dirichlet (Fixed / Displacement / Symmetry)**: Apply by DOF elimination or symmetric row/column zeroing with diagonal $1$ (keeping $\mathbf{K}$ symmetric positive definite so CG/Cholesky solvers work). Check for zero-pivot / insufficient constraints (at least 6 independent DOFs restrained in 3D to prevent rigid-body modes).
  - **Neumann (Force / Pressure / Bearing)**: Total force distributed across selected surface nodes by tributary triangle area $\frac{1}{3} A_f$ (or consistent shape-function nodal integration for quadratic faces), never unweighted division by node count on non-uniform meshes.

### Linear Solvers & Performance
- **Small/Medium (< ~80k DOFs)**: Sparse direct solver (`scipy.sparse.linalg.spsolve`, `Pardiso`/`MUMPS`/`SuiteSparse` if available).
- **Large 3D Meshes (> ~80k DOFs)**: Matrix-free or CSR **Preconditioned Conjugate Gradient (PCG)** with Algebraic Multigrid (`pyamg` smoothed aggregation) or Jacobi preconditioning, warm-started from the previous iteration's displacement vector $\mathbf{u}^{(k-1)}$ during Topology Optimization.

### Post-Processing Fields
Compute and return typed arrays (`Float32Array`-ready binary buffers):
- Nodal displacement $\mathbf{u} = [u_x, u_y, u_z]$ and magnitude $\|\mathbf{u}\|$.
- Cauchy stress $\boldsymbol{\sigma} = \mathbf{D}\mathbf{B}\mathbf{u}^e$ at Gauss points, averaged smoothly to nodes (Zienkiewicz-Zhu or volume-weighted nodal averaging).
- **Von Mises equivalent stress**:
  $$\sigma_{vM} = \sqrt{\frac{1}{2}\left[(\sigma_x-\sigma_y)^2 + (\sigma_y-\sigma_z)^2 + (\sigma_z-\sigma_x)^2 + 6(\tau_{xy}^2 + \tau_{yz}^2 + \tau_{xz}^2)\right]}$$
- **Safety Factor**: $SF = \sigma_{\text{yield}} / \max(\sigma_{vM}, \epsilon)$, compliance $c = \mathbf{u}^T\mathbf{K}\mathbf{u}$, and reaction forces $\mathbf{R} = \mathbf{K}\mathbf{u} - \mathbf{f}_{\text{ext}}$ at constrained DOFs.

## 2. 3D Topology Optimization (SIMP & BESO)

### Modified SIMP Formulation
- **Interpolation**:
  $$E_e(\tilde{\rho}_e) = E_{\min} + \tilde{\rho}_e^p (E_0 - E_{\min}), \quad p = 3.0, \quad E_{\min} = 10^{-9} E_0$$
  (Never use $E_{\min} = 0$, which makes $\mathbf{K}$ singular as densities approach $0$.)
- **Compliance & Sensitivity**:
  $$c(\tilde{\boldsymbol{\rho}}) = \mathbf{u}^T \mathbf{K} \mathbf{u}, \qquad \frac{\partial c}{\partial \tilde{\rho}_e} = -p\,\tilde{\rho}_e^{p-1}(E_0 - E_{\min})\,\mathbf{u}_e^T \mathbf{K}_0 \mathbf{u}_e$$
- **Filtering (Mandatory to prevent checkerboarding & mesh dependence)**:
  - Precompute sparse cone-filter weight matrix $\mathbf{H}$ with filter radius $r_{\min} \ge 1.5 \cdot h_e$ (where $h_e$ is average element size): $H_{ij} = \max(0, r_{\min} - \|\mathbf{x}_i - \mathbf{x}_j\|)$.
  - Apply **density filter** $\tilde{\boldsymbol{\rho}} = (\mathbf{H}\boldsymbol{\rho}) / \mathbf{h}_{\text{sum}}$ and backpropagate the chain rule $\frac{\partial c}{\partial \rho_e} = \sum_i \frac{H_{ie}}{h_{\text{sum}, i}} \frac{\partial c}{\partial \tilde{\rho}_i}$ consistently!
  - Optional continuation: start with $p=1$ for 10 iterations then ramp $p \to 3$, and optionally apply smoothed Heaviside projection ($\beta$ continuation) to obtain crisp $0/1$ boundaries.
- **Design Domains**:
  - **Passive Solid (Non-design)**: Force $\rho_e = 1$ on load application pads, support bosses, and bolt holes so they are never removed.
  - **Passive Void**: Force $\rho_e = 0$ in clearance/keep-out channels.
- **Optimizer Update**: Optimality Criteria (OC) bisection for single volume constraint ($\sum \tilde{\rho}_e v_e \le f_{\text{vol}} V_{\text{design}}$) with move limit $m = 0.2$, or MMA when adding stress/displacement/multi-load-case constraints.
- **Convergence**: Stop when $\max |\rho^{(k)} - \rho^{(k-1)}| < 0.01$ or max iterations reached.

### Watertight Geometry Reconstruction from Densities
1. Pad the 3D density field with a 1-voxel zero halo so Marching Cubes closes outer domain boundaries instead of leaving open boundary cuts.
2. Extract isosurface at threshold $\tau$ matching target volume fraction (e.g., $\tau = 0.5$ or bisection on $\tau$).
3. Apply volume-preserving **Taubin smoothing** (not naive Laplacian alone, which shrinks thin members).
4. Union/preserve exact non-design solid regions (bolt holes, bearing faces) if high geometric precision is required, then audit manifoldness & watertightness before exporting `.STL`/`.OBJ`/`.GLB`.

## 3. Web App Execution & Streaming Architecture

- Run meshing, FEM solves, and TopOpt loops inside **background worker processes** (never blocking the FastAPI/HTTP event loop).
- Enforce job states (`queued` -> `meshing` -> `solving` -> `optimizing` -> `reconstructing` -> `completed` | `failed` | `cancelled`) with cooperative cancellation tokens checked every iteration.
- Stream lightweight progress over WebSocket/SSE: `{ iteration, compliance, volume_fraction, max_change, preview_threshold_mesh_or_densities }`.

## 4. Numerical Verification Benchmarks

Before trusting any solver change, verify against closed-form solutions:
- [ ] **Patch test**: Uniform uniaxial tension on a 3D prism reproduces exact $\sigma_{xx} = F/A$ and lateral contraction $-\nu \varepsilon_{xx}$ within machine/discretization precision.
- [ ] **Cantilever beam**: Tip deflection $\delta = \frac{F L^3}{3 E I}$ (plus Timoshenko shear correction for stubby beams) matches analytical solution within mesh convergence error ($< 5\%$ on refined C3D10).
- [ ] **Static equilibrium**: Sum of reaction forces + applied forces $= \mathbf{0}$ and sum of moments $= \mathbf{0}$ to $< 10^{-6} \|\mathbf{F}\|$.
- [ ] **TopOpt sanity**: Classic 3D MBB / cantilever beam recovers recognizable truss/web topology with monotonically decreasing compliance (after continuation settles) and exact target volume fraction.

## 5. Local Reference Codebase

Before writing custom 3D stiffness templates, filters, MMA/OC optimizers, or benchmark fixtures from scratch, read [reference-codebase-catalog.md](references/reference-codebase-catalog.md) for verified file paths and strict MIT/BSD-3 vs GPL/LGPL license rules across `c:\AppWebFem\references\`.

