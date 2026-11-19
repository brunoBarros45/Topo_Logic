"""3D SIMP Topology Optimization engine supporting OC and MIT MMA + P-norm stress."""

from __future__ import annotations

import io
from collections.abc import Callable

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from numpy.typing import NDArray

from topo_logic.application.ports.execution import CancellationToken
from topo_logic.domain.boundary import BoundingBoxSelector, DesignZoneType
from topo_logic.domain.exceptions import DomainValidationError, JobCancelledError
from topo_logic.domain.geometry import ElementType
from topo_logic.domain.results import (
    TopOptIterationEvent,
    TopOptResultSummary,
    WeightSavingsMetrics,
)
from topo_logic.domain.study import FilterKind, OptimizerKind, SolverKind, TopOptStudyConfig
from topo_logic.infrastructure.fem.boundary_conditions import (
    ResolvedRegion,
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
from topo_logic.infrastructure.fem.linear_solvers import solve_reduced_systems
from topo_logic.infrastructure.mesh.volume_mesh import VolumeMeshData, deserialize_volume_mesh
from topo_logic.infrastructure.topopt.filters import CompositeDensityFilter, ConeDensityFilter
from topo_logic.infrastructure.topopt.mma_optimizer import MmaOptimizer
from topo_logic.infrastructure.topopt.oc_optimizer import oc_update
from topo_logic.infrastructure.topopt.stress_aggregation import (
    compute_relaxed_pnorm_stress_and_adjoint,
)


class SimpTopologyOptimizer:
    """Multi-loadcase 3D SIMP optimizer implementing OptimizerPort (OC & MMA)."""

    def optimizer_kind(self) -> OptimizerKind:
        return OptimizerKind.OC

    def run_optimization(
        self,
        *,
        job_id: str,
        mesh_payload: bytes,
        study: TopOptStudyConfig,
        cancellation_token: CancellationToken,
        on_iteration: Callable[[TopOptIterationEvent], None],
    ) -> tuple[TopOptResultSummary, bytes]:
        if cancellation_token.is_cancelled():
            raise JobCancelledError("TopOpt job cancelled before initialization.")

        mesh = deserialize_volume_mesh(mesh_payload)
        if (
            mesh.element_type is not ElementType.H8
            or mesh.voxel_pitch is None
            or mesh.voxel_shape is None
            or mesh.voxel_origin is None
            or mesh.active_voxel_ijk is None
        ):
            raise DomainValidationError(
                "3D SIMP optimization currently requires a structured H8 voxel mesh."
            )

        fem_cfg = study.fem_config
        resolved_regions = resolve_regions(mesh, fem_cfg.regions)
        fixed_dofs, prescribed_vals = extract_dirichlet_dofs(
            mesh, resolved_regions, fem_cfg.supports
        )
        if np.any(prescribed_vals != 0.0):
            raise DomainValidationError(
                "Topology Optimization supports homogeneous zero-displacement constraints."
            )

        ndof = 3 * len(mesh.nodes)
        fixed_mask = np.zeros(ndof, dtype=bool)
        fixed_mask[fixed_dofs] = True
        free_dofs = np.flatnonzero(~fixed_mask).astype(np.int32)

        f_free_list: list[NDArray[np.float64]] = []
        weights: list[float] = []
        for lc in fem_cfg.load_cases:
            f_ext = assemble_load_vector(mesh, resolved_regions, lc)
            f_free_list.append(f_ext[free_dofs])
            weights.append(lc.weight)

        n_elem = len(mesh.elements)
        hx, hy, hz = mesh.voxel_pitch
        elem_vol = hx * hy * hz
        elem_volumes = np.full(n_elem, elem_vol, dtype=np.float64)

        edof = (
            3 * mesh.elements[:, :, None] + np.arange(3, dtype=np.int32)[None, None, :]
        ).reshape(n_elem, 24)
        elem_centers = mesh.nodes[mesh.elements].mean(axis=1)

        passive_solid, passive_void = _resolve_passive_masks(
            mesh=mesh,
            elem_centers=elem_centers,
            regions=fem_cfg.regions,
            resolved_regions=resolved_regions,
            design_zones=study.design_zones,
        )
        free_elem_mask = ~(passive_solid | passive_void)
        if not np.any(free_elem_mask):
            raise DomainValidationError(
                "Passive design zones leave zero free design elements to optimize."
            )

        design_mask = ~passive_void
        v_design = float(np.sum(elem_volumes[design_mask]))
        v_solid = float(np.sum(elem_volumes[passive_solid]))
        target_vol = study.target_volume_fraction * v_design
        if target_vol <= v_solid:
            raise DomainValidationError(
                "Target volume is smaller than or equal to the mandatory PASSIVE_SOLID volume.",
                details={"target_volume": target_vol, "passive_solid_volume": v_solid},
            )

        h_avg = (hx * hy * hz) ** (1.0 / 3.0)
        filter_radius = study.filter_radius_ratio * h_avg
        cone = ConeDensityFilter(elem_centers, filter_radius=filter_radius)
        density_filter = CompositeDensityFilter(cone, study.filter_kind)

        mat = fem_cfg.material
        d_matrix = isotropic_constitutive_matrix(mat.youngs_modulus, mat.poissons_ratio)
        k0 = h8_brick_stiffness(hx, hy, hz, d_matrix)
        b_center = h8_b_matrix_at_center(hx, hy, hz)

        # Initialize design variables at feasible target fraction inside active region
        v_free_total = float(np.sum(elem_volumes[free_elem_mask]))
        init_free_frac = float(np.clip((target_vol - v_solid) / v_free_total, 0.05, 0.95))
        x = np.full(n_elem, init_free_frac, dtype=np.float64)
        x[passive_solid] = 1.0
        x[passive_void] = 0.0

        free_elem_idx = np.flatnonzero(free_elem_mask)
        n_constraints = 2 if study.stress_constraint.enabled else 1
        mma: MmaOptimizer | None = None
        if study.optimizer_kind is OptimizerKind.MMA:
            mma = MmaOptimizer(
                n_vars=len(free_elem_idx),
                n_constraints=n_constraints,
                move=study.move_limit,
                xmin=1e-4,
                xmax=1.0,
            )

        prev_u_free: list[NDArray[np.float64]] | None = None
        c0_scale: float | None = None
        stress_scale_factor = 1.0
        converged = False
        final_compliance = 0.0
        final_vol_frac = init_free_frac
        rho_phys = x.copy()
        iters_done = 0

        for it in range(1, study.max_iterations + 1):
            if cancellation_token.is_cancelled():
                raise JobCancelledError(f"TopOpt cancelled at iteration {it}.")

            penalty, beta = _continuation_schedule(
                iteration=it,
                max_iterations=study.max_iterations,
                target_penalty=study.penalty,
                use_continuation=study.use_continuation,
                filter_kind=study.filter_kind,
            )

            rho_phys = density_filter.forward(x, beta=beta)
            rho_phys[passive_solid] = 1.0
            rho_phys[passive_void] = 0.0

            stiffness_scale = study.e_min_ratio + (rho_phys**penalty) * (
                1.0 - study.e_min_ratio
            )
            k_global = assemble_global_stiffness(mesh, mat, element_scale=stiffness_scale)
            k_ff = k_global[free_dofs, :][:, free_dofs].tocsc()

            solve_free_rhs, u_free_list = _solve_and_reuse_factorization(
                k_ff=k_ff,
                rhs_list=f_free_list,
                solver_kind=fem_cfg.solver_kind,
                x0_list=prev_u_free,
            )
            prev_u_free = u_free_list

            u_global_list: list[NDArray[np.float64]] = []
            total_compliance = 0.0
            dc_drho_phys = np.zeros(n_elem, dtype=np.float64)
            dscale_drho = penalty * (rho_phys ** (penalty - 1.0)) * (1.0 - study.e_min_ratio)

            for w_lc, u_free in zip(weights, u_free_list, strict=True):
                u_global = np.zeros(ndof, dtype=np.float64)
                u_global[free_dofs] = u_free
                u_global_list.append(u_global)

                u_elem = u_global[edof]
                ce = np.sum((u_elem @ k0) * u_elem, axis=1)
                total_compliance += w_lc * float(np.sum(stiffness_scale * ce))
                dc_drho_phys -= w_lc * dscale_drho * ce

            dc_dx = density_filter.adjoint(dc_drho_phys, x, beta=beta)
            dv_drho_phys = elem_volumes.copy()
            dv_drho_phys[passive_void] = 0.0
            dv_dx = density_filter.adjoint(dv_drho_phys, x, beta=beta)

            max_vm: float | None = None
            dg_stress_dx: NDArray[np.float64] | None = None
            stress_constraint_val: float | None = None
            if (
                study.stress_constraint.enabled
                and study.stress_constraint.max_von_mises is not None
            ):
                stress_res = compute_relaxed_pnorm_stress_and_adjoint(
                    edof=edof,
                    d_matrix=d_matrix,
                    b_center=b_center,
                    k0=k0,
                    rho_phys=rho_phys,
                    u_list=u_global_list,
                    free_dofs=free_dofs,
                    ndof=ndof,
                    solve_free_rhs=solve_free_rhs,
                    max_von_mises=study.stress_constraint.max_von_mises,
                    p_norm=study.stress_constraint.p_norm_exponent,
                    simp_penalty=penalty,
                    e_min_ratio=study.e_min_ratio,
                )
                max_vm = stress_res.max_von_mises
                if study.stress_constraint.use_adaptive_scaling:
                    raw_scale = (
                        max_vm / study.stress_constraint.max_von_mises
                    ) / max(stress_res.pnorm_ratio, 1e-12)
                    stress_scale_factor = (
                        raw_scale if it == 1 else 0.5 * stress_scale_factor + 0.5 * raw_scale
                    )
                else:
                    stress_scale_factor = 1.0

                stress_constraint_val = stress_scale_factor * stress_res.pnorm_ratio - 1.0
                dg_stress_dx = density_filter.adjoint(
                    stress_scale_factor * stress_res.dpnorm_drho_phys,
                    x,
                    beta=beta,
                )

            if study.optimizer_kind is OptimizerKind.OC:
                x_new = oc_update(
                    x=x,
                    dc=dc_dx,
                    dv=dv_dx,
                    target_volume=target_vol,
                    elem_volumes=elem_volumes,
                    filter_fn=_bind_density_filter(density_filter, beta),
                    passive_solid=passive_solid,
                    passive_void=passive_void,
                    move_limit=study.move_limit,
                )
            else:
                assert mma is not None
                if c0_scale is None:
                    c0_scale = max(abs(total_compliance), 1e-12)
                f0 = 10.0 * total_compliance / c0_scale
                df0 = 10.0 * dc_dx[free_elem_idx] / c0_scale

                design_vol = float(np.dot(elem_volumes[design_mask], rho_phys[design_mask]))
                g_vol = (design_vol - target_vol) / target_vol
                dg_vol = dv_dx[free_elem_idx] / target_vol

                if dg_stress_dx is not None and stress_constraint_val is not None:
                    g_vec = np.array([g_vol, stress_constraint_val], dtype=np.float64)
                    dg_mat = np.vstack([dg_vol, dg_stress_dx[free_elem_idx]])
                else:
                    g_vec = np.array([g_vol], dtype=np.float64)
                    dg_mat = dg_vol[None, :]

                x_free_new = mma.step(
                    x=x[free_elem_idx],
                    f0=f0,
                    df0=df0,
                    g=g_vec,
                    dg=dg_mat,
                )
                x_new = x.copy()
                x_new[free_elem_idx] = x_free_new
                x_new[passive_solid] = 1.0
                x_new[passive_void] = 0.0

            max_change = float(np.max(np.abs(x_new - x)))
            x = x_new

            # Re-evaluate physical densities for accurate reported volume fraction
            rho_phys = density_filter.forward(x, beta=beta)
            rho_phys[passive_solid] = 1.0
            rho_phys[passive_void] = 0.0

            current_vol = float(np.dot(elem_volumes[design_mask], rho_phys[design_mask]))
            final_vol_frac = current_vol / v_design
            final_compliance = total_compliance
            iters_done = it

            on_iteration(
                TopOptIterationEvent(
                    job_id=job_id,
                    iteration=it,
                    compliance=final_compliance,
                    volume_fraction=final_vol_frac,
                    max_density_change=max_change,
                    max_von_mises=max_vm,
                )
            )

            settled = (not study.use_continuation) or (
                abs(penalty - study.penalty) < 1e-9 and it >= min(10, study.max_iterations)
            )
            if settled and it >= 5 and max_change < study.convergence_tol:
                converged = True
                break

        original_total_volume = float(np.sum(elem_volumes))
        optimized_solid_volume = float(np.sum(elem_volumes * rho_phys))
        weight_savings = WeightSavingsMetrics.from_volumes_and_material(
            original_volume=original_total_volume,
            optimized_volume=optimized_solid_volume,
            material=mat,
        )

        density_payload = _pack_density_payload(
            densities_phys=rho_phys,
            densities_raw=x,
            mesh=mesh,
            original_volume=original_total_volume,
        )
        summary = TopOptResultSummary(
            job_id=job_id,
            iterations_completed=iters_done,
            converged=converged,
            final_compliance=final_compliance,
            final_volume_fraction=final_vol_frac,
            reconstructed_stl_key="",
            density_field_key="",
            weight_savings=weight_savings,
        )
        return summary, density_payload


def _continuation_schedule(
    *,
    iteration: int,
    max_iterations: int,
    target_penalty: float,
    use_continuation: bool,
    filter_kind: FilterKind,
) -> tuple[float, float]:
    if not use_continuation:
        beta = 8.0 if filter_kind is FilterKind.HEAVISIDE_PROJECTION else 1.0
        return target_penalty, beta

    if max_iterations >= 15:
        if iteration <= 3:
            penalty = min(1.0, target_penalty)
        elif iteration <= 7:
            penalty = min(2.0, target_penalty)
        else:
            penalty = target_penalty
    else:
        penalty = target_penalty

    if filter_kind is FilterKind.HEAVISIDE_PROJECTION:
        progress = iteration / max(1, max_iterations)
        if progress < 0.35:
            beta = 1.0
        elif progress < 0.60:
            beta = 2.0
        elif progress < 0.80:
            beta = 4.0
        else:
            beta = 8.0
    else:
        beta = 1.0
    return penalty, beta


def _resolve_passive_masks(
    *,
    mesh: VolumeMeshData,
    elem_centers: NDArray[np.float64],
    regions: tuple[object, ...],
    resolved_regions: dict[str, ResolvedRegion],
    design_zones: tuple[object, ...],
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    from topo_logic.domain.boundary import BoundaryRegion, DesignZone

    n_elem = len(mesh.elements)
    n_nodes = len(mesh.nodes)
    passive_solid = np.zeros(n_elem, dtype=bool)
    passive_void = np.zeros(n_elem, dtype=bool)

    region_map: dict[str, BoundaryRegion] = {}
    for reg in regions:
        if isinstance(reg, BoundaryRegion):
            region_map[reg.id] = reg

    for zone in design_zones:
        if not isinstance(zone, DesignZone):
            continue
        reg = region_map[zone.region_id]
        res = resolved_regions[zone.region_id]

        if isinstance(reg.selector, BoundingBoxSelector):
            lo = np.asarray(reg.selector.min_corner, dtype=np.float64)
            hi = np.asarray(reg.selector.max_corner, dtype=np.float64)
            elem_mask = np.all((elem_centers >= lo) & (elem_centers <= hi), axis=1)
            if not np.any(elem_mask):
                node_flag = np.zeros(n_nodes, dtype=bool)
                node_flag[res.node_indices] = True
                elem_mask = np.any(node_flag[mesh.elements], axis=1)
        else:
            node_flag = np.zeros(n_nodes, dtype=bool)
            node_flag[res.node_indices] = True
            elem_mask = np.any(node_flag[mesh.elements], axis=1)

        if zone.zone_type is DesignZoneType.PASSIVE_SOLID:
            passive_solid |= elem_mask
        elif zone.zone_type is DesignZoneType.PASSIVE_VOID:
            passive_void |= elem_mask

    # PASSIVE_SOLID takes precedence if overlapping
    passive_void &= ~passive_solid
    return passive_solid, passive_void


def _solve_and_reuse_factorization(
    *,
    k_ff: sp.csc_matrix,
    rhs_list: list[NDArray[np.float64]],
    solver_kind: SolverKind,
    x0_list: list[NDArray[np.float64]] | None,
) -> tuple[
    Callable[[list[NDArray[np.float64]]], list[NDArray[np.float64]]],
    list[NDArray[np.float64]],
]:
    n_free = int(k_ff.shape[0])
    use_direct = solver_kind is SolverKind.DIRECT or (
        solver_kind is SolverKind.AUTO and n_free < 80_000
    )
    if use_direct and n_free > 0:
        factor = spla.splu(k_ff)
        primal = [np.asarray(factor.solve(rhs), dtype=np.float64) for rhs in rhs_list]

        def _reuse_lu(adj_rhs: list[NDArray[np.float64]]) -> list[NDArray[np.float64]]:
            return [np.asarray(factor.solve(rhs), dtype=np.float64) for rhs in adj_rhs]

        return _reuse_lu, primal

    primal = solve_reduced_systems(
        k_ff, rhs_list, solver_kind=solver_kind, x0_list=x0_list
    )

    def _pcg_solve(adj_rhs: list[NDArray[np.float64]]) -> list[NDArray[np.float64]]:
        return solve_reduced_systems(k_ff, adj_rhs, solver_kind=solver_kind)

    return _pcg_solve, primal


def _pack_density_payload(
    *,
    densities_phys: NDArray[np.float64],
    densities_raw: NDArray[np.float64],
    mesh: VolumeMeshData,
    original_volume: float,
) -> bytes:
    assert mesh.voxel_shape is not None
    assert mesh.voxel_origin is not None
    assert mesh.voxel_pitch is not None
    assert mesh.active_voxel_ijk is not None

    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        densities_phys=np.ascontiguousarray(densities_phys, dtype=np.float32),
        densities_raw=np.ascontiguousarray(densities_raw, dtype=np.float32),
        voxel_shape=np.asarray(mesh.voxel_shape, dtype=np.int32),
        voxel_origin=np.asarray(mesh.voxel_origin, dtype=np.float64),
        voxel_pitch=np.asarray(mesh.voxel_pitch, dtype=np.float64),
        active_voxel_ijk=np.asarray(mesh.active_voxel_ijk, dtype=np.int32),
        original_volume=np.asarray([original_volume], dtype=np.float64),
    )
    return buf.getvalue()


def _bind_density_filter(
    density_filter: CompositeDensityFilter,
    beta: float,
) -> Callable[[NDArray[np.float64]], NDArray[np.float64]]:
    def _apply(candidate: NDArray[np.float64]) -> NDArray[np.float64]:
        return density_filter.forward(candidate, beta=beta)

    return _apply
