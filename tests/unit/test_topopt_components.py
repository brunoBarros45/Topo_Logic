"""Unit tests for TopOpt filters, MMA optimizer, P-norm stress adjoint, and STL reconstruction."""

from __future__ import annotations

import io

import numpy as np
import pytest
import scipy.sparse.linalg as spla
import trimesh

from topo_logic.domain import (
    BoundaryRegion,
    ElementType,
    FilterKind,
    ForceLoad,
    IsotropicMaterial,
    LoadCase,
    PlaneSelector,
    UnitSystem,
)
from topo_logic.infrastructure.fem.boundary_conditions import (
    assemble_load_vector,
    extract_dirichlet_dofs,
    resolve_regions,
)
from topo_logic.infrastructure.fem.elasticity import (
    assemble_global_stiffness,
    h8_b_matrix_at_center,
    h8_brick_stiffness,
    isotropic_constitutive_matrix,
)
from topo_logic.infrastructure.mesh import VoxelH8Mesher, deserialize_volume_mesh
from topo_logic.infrastructure.topopt import (
    CompositeDensityFilter,
    ConeDensityFilter,
    MmaOptimizer,
    WatertightStlReconstructor,
    compute_relaxed_pnorm_stress_and_adjoint,
)
from topo_logic.infrastructure.topopt.simp_engine import _pack_density_payload


@pytest.mark.unit
@pytest.mark.parametrize("filter_kind", [FilterKind.CONE_DENSITY, FilterKind.HEAVISIDE_PROJECTION])
def test_cone_and_heaviside_filter_adjoint_matches_finite_differences(
    filter_kind: FilterKind,
) -> None:
    rng = np.random.default_rng(42)
    centers = np.array(
        [[i + 0.5, j + 0.5, k + 0.5] for i in range(4) for j in range(3) for k in range(2)]
    )
    cone = ConeDensityFilter(centers, filter_radius=1.6)
    filt = CompositeDensityFilter(cone, filter_kind=filter_kind)

    x = rng.uniform(0.15, 0.85, size=len(centers))
    weights = rng.uniform(0.5, 2.5, size=len(centers))
    beta = 4.0

    def _objective(vec: np.ndarray) -> float:
        phys = filt.forward(vec, beta=beta)
        return float(np.sum(weights * (phys**2)))

    phys0 = filt.forward(x, beta=beta)
    grad_analytic = filt.adjoint(2.0 * weights * phys0, x, beta=beta)

    eps = 1e-6
    for idx in (0, 5, 11, 18):
        xp = x.copy()
        xm = x.copy()
        xp[idx] += eps
        xm[idx] -= eps
        fd = (_objective(xp) - _objective(xm)) / (2.0 * eps)
        assert grad_analytic[idx] == pytest.approx(fd, rel=1e-5)


@pytest.mark.unit
def test_pnorm_stress_adjoint_matches_finite_differences() -> None:
    box = trimesh.creation.box(extents=(15.0, 10.0, 10.0))
    box.apply_translation((7.5, 5.0, 5.0))
    stl_raw = box.export(file_type="stl")
    stl_bytes = stl_raw if isinstance(stl_raw, bytes) else bytes(stl_raw)

    _, mesh_payload = VoxelH8Mesher().generate_volume_mesh(
        stl_bytes,
        geometry_id="fd-stress",
        element_type=ElementType.H8,
        target_element_size=5.0,
    )
    mesh = deserialize_volume_mesh(mesh_payload)
    assert mesh.voxel_pitch is not None
    hx, hy, hz = mesh.voxel_pitch

    from topo_logic.domain import SupportBC, SupportType

    mat = IsotropicMaterial("Steel", 200_000.0, 0.3, 350.0, 7.87e-9, UnitSystem.MM_N_MPA)
    regions = (
        BoundaryRegion("root", "Root", PlaneSelector((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
        BoundaryRegion("tip", "Tip", PlaneSelector((15.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
    )
    resolved = resolve_regions(mesh, regions)
    fixed_dofs, _ = extract_dirichlet_dofs(
        mesh, resolved, (SupportBC("root", SupportType.FIXED),)
    )
    ndof = 3 * len(mesh.nodes)
    fixed_mask = np.zeros(ndof, dtype=bool)
    fixed_mask[fixed_dofs] = True
    free_dofs = np.flatnonzero(~fixed_mask).astype(np.int32)
    f_ext = assemble_load_vector(
        mesh, resolved, LoadCase("lc", "Shear", (ForceLoad("tip", (0.0, 0.0, -1000.0)),))
    )
    f_free = f_ext[free_dofs]

    n_elem = len(mesh.elements)
    edof = (
        3 * mesh.elements[:, :, None] + np.arange(3, dtype=np.int32)[None, None, :]
    ).reshape(n_elem, 24)
    d_matrix = isotropic_constitutive_matrix(mat.youngs_modulus, mat.poissons_ratio)
    k0 = h8_brick_stiffness(hx, hy, hz, d_matrix)
    b_center = h8_b_matrix_at_center(hx, hy, hz)

    rng = np.random.default_rng(7)
    rho = rng.uniform(0.3, 0.9, size=n_elem)
    penalty = 3.0
    e_min_ratio = 1e-9

    def _eval_pnorm(r_vec: np.ndarray, *, with_grad: bool = False) -> tuple[float, np.ndarray]:
        scale = e_min_ratio + (r_vec**penalty) * (1.0 - e_min_ratio)
        k_g = assemble_global_stiffness(mesh, mat, element_scale=scale)
        k_ff = k_g[free_dofs, :][:, free_dofs].tocsc()
        factor = spla.splu(k_ff)
        u_global = np.zeros(ndof, dtype=np.float64)
        u_global[free_dofs] = factor.solve(f_free)
        if not with_grad:
            res_only = compute_relaxed_pnorm_stress_and_adjoint(
                edof=edof,
                d_matrix=d_matrix,
                b_center=b_center,
                k0=k0,
                rho_phys=r_vec,
                u_list=[u_global],
                free_dofs=free_dofs,
                ndof=ndof,
                solve_free_rhs=lambda rhs_l: [np.zeros(len(free_dofs))],
                max_von_mises=50.0,
                p_norm=6.0,
                simp_penalty=penalty,
                e_min_ratio=e_min_ratio,
            )
            return res_only.pnorm_ratio, np.empty(0)

        res = compute_relaxed_pnorm_stress_and_adjoint(
            edof=edof,
            d_matrix=d_matrix,
            b_center=b_center,
            k0=k0,
            rho_phys=r_vec,
            u_list=[u_global],
            free_dofs=free_dofs,
            ndof=ndof,
            solve_free_rhs=lambda rhs_l: [
                np.asarray(factor.solve(r), dtype=np.float64) for r in rhs_l
            ],
            max_von_mises=50.0,
            p_norm=6.0,
            simp_penalty=penalty,
            e_min_ratio=e_min_ratio,
        )
        return res.pnorm_ratio, res.dpnorm_drho_phys

    _, grad_analytic = _eval_pnorm(rho, with_grad=True)
    eps = 1e-6
    for idx in (0, 3, 7, 10):
        rp = rho.copy()
        rm = rho.copy()
        rp[idx] += eps
        rm[idx] -= eps
        fp, _ = _eval_pnorm(rp)
        fm, _ = _eval_pnorm(rm)
        fd = (fp - fm) / (2.0 * eps)
        assert grad_analytic[idx] == pytest.approx(fd, rel=1e-4)


@pytest.mark.unit
def test_mma_optimizer_solves_constrained_quadratic() -> None:
    # Minimize x0^2 + x1^2 subject to 1.2 - x0 - x1 <= 0 on [0, 1]^2 -> KKT optimum (0.6, 0.6)
    mma = MmaOptimizer(n_vars=2, n_constraints=1, move=0.25, xmin=0.0, xmax=1.0)
    x = np.array([0.85, 0.90], dtype=np.float64)
    for _ in range(30):
        f0 = float(np.sum(x**2))
        df0 = 2.0 * x
        g = np.array([1.2 - float(np.sum(x))], dtype=np.float64)
        dg = np.array([[-1.0, -1.0]], dtype=np.float64)
        x = mma.step(x=x, f0=f0, df0=df0, g=g, dg=dg)

    assert x[0] == pytest.approx(0.6, abs=1e-3)
    assert x[1] == pytest.approx(0.6, abs=1e-3)


@pytest.mark.unit
def test_watertight_stl_reconstructor_zero_halo_and_bounds() -> None:
    box = trimesh.creation.box(extents=(30.0, 20.0, 20.0))
    box.apply_translation((15.0, 10.0, 10.0))
    stl_raw = box.export(file_type="stl")
    stl_bytes = stl_raw if isinstance(stl_raw, bytes) else bytes(stl_raw)

    _, mesh_payload = VoxelH8Mesher().generate_volume_mesh(
        stl_bytes,
        geometry_id="recon-test",
        element_type=ElementType.H8,
        target_element_size=5.0,
    )
    mesh = deserialize_volume_mesh(mesh_payload)
    densities = np.ones(len(mesh.elements), dtype=np.float64)
    payload = _pack_density_payload(
        densities_phys=densities,
        densities_raw=densities,
        mesh=mesh,
        original_volume=12_000.0,
    )

    reconstructor = WatertightStlReconstructor(taubin_iterations=6)
    reconstructed = reconstructor.reconstruct_watertight_stl(
        density_payload=payload,
        target_volume_fraction=1.0,
    )
    assert reconstructed.is_watertight is True
    assert reconstructed.volume > 8_000.0

    parsed = trimesh.load(io.BytesIO(reconstructed.stl_bytes), file_type="stl", force="mesh")
    assert isinstance(parsed, trimesh.Trimesh)
    assert parsed.is_watertight
    bounds = np.asarray(parsed.bounds)
    assert np.all(bounds[0] >= -1.0)
    assert np.all(bounds[1] <= [31.0, 21.0, 21.0])
