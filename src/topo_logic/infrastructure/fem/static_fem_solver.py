"""Concrete FemSolverPort implementation for multi-loadcase 3D linear static FEM."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from topo_logic.application.ports.execution import CancellationToken
from topo_logic.domain.exceptions import JobCancelledError
from topo_logic.domain.results import FemResultSummary, LoadCaseFemSummary
from topo_logic.domain.study import FemStudyConfig
from topo_logic.domain.units import UnitSystem
from topo_logic.infrastructure.fem.boundary_conditions import (
    assemble_load_vector,
    extract_dirichlet_dofs,
    resolve_regions,
)
from topo_logic.infrastructure.fem.elasticity import assemble_global_stiffness
from topo_logic.infrastructure.fem.linear_solvers import solve_reduced_systems
from topo_logic.infrastructure.fem.postprocess import (
    compute_equilibrium_check,
    pack_fem_fields_bundle,
    recover_nodal_stresses,
    summarize_field,
)
from topo_logic.infrastructure.mesh.volume_mesh import deserialize_volume_mesh


class StaticFemSolver:
    """Multi-loadcase 3D linear static elasticity solver implementing FemSolverPort."""

    def run_static_analysis(
        self,
        *,
        job_id: str,
        mesh_payload: bytes,
        study: FemStudyConfig,
        cancellation_token: CancellationToken,
    ) -> tuple[FemResultSummary, bytes]:
        if cancellation_token.is_cancelled():
            raise JobCancelledError("FEM job cancelled before assembly.")

        mesh = deserialize_volume_mesh(mesh_payload)
        resolved_regions = resolve_regions(mesh, study.regions)
        fixed_dofs, prescribed_vals = extract_dirichlet_dofs(
            mesh, resolved_regions, study.supports
        )

        ndof = 3 * len(mesh.nodes)
        fixed_mask = np.zeros(ndof, dtype=bool)
        fixed_mask[fixed_dofs] = True
        free_dofs = np.flatnonzero(~fixed_mask).astype(np.int32)

        k_global = assemble_global_stiffness(mesh, study.material)
        k_ff = k_global[free_dofs, :][:, free_dofs].tocsc()
        k_fc = k_global[free_dofs, :][:, fixed_dofs].tocsc()

        has_nonzero_prescribed = bool(np.any(prescribed_vals != 0.0))
        k_fc_uc = (
            np.asarray(k_fc @ prescribed_vals, dtype=np.float64)
            if has_nonzero_prescribed
            else np.zeros(len(free_dofs), dtype=np.float64)
        )

        f_ext_list: list[NDArray[np.float64]] = []
        rhs_list: list[NDArray[np.float64]] = []
        for load_case in study.load_cases:
            if cancellation_token.is_cancelled():
                raise JobCancelledError("FEM job cancelled during load assembly.")
            f_ext = assemble_load_vector(mesh, resolved_regions, load_case)
            f_ext_list.append(f_ext)
            rhs_list.append(f_ext[free_dofs] - k_fc_uc)

        if cancellation_token.is_cancelled():
            raise JobCancelledError("FEM job cancelled before linear solve.")

        u_free_list = solve_reduced_systems(
            k_ff, rhs_list, solver_kind=study.solver_kind
        )

        length_unit = "mm" if study.material.unit_system is UnitSystem.MM_N_MPA else "m"
        stress_unit = "MPa" if study.material.unit_system is UnitSystem.MM_N_MPA else "Pa"

        case_summaries: list[LoadCaseFemSummary] = []
        fields_by_case: dict[str, dict[str, NDArray[np.float32]]] = {}

        for idx, load_case in enumerate(study.load_cases):
            if cancellation_token.is_cancelled():
                raise JobCancelledError("FEM job cancelled during post-processing.")

            u_global = np.zeros(ndof, dtype=np.float64)
            u_global[free_dofs] = u_free_list[idx]
            u_global[fixed_dofs] = prescribed_vals

            f_ext = f_ext_list[idx]
            compliance = float(np.dot(u_global, k_global @ u_global))

            u_nodal = u_global.reshape(-1, 3)
            disp_mag = np.linalg.norm(u_nodal, axis=1)

            _, nodal_vm = recover_nodal_stresses(mesh, study.material, u_global)
            eps_stress = 1e-12 * study.material.yield_strength
            safety_factor = study.material.yield_strength / np.maximum(nodal_vm, eps_stress)
            min_sf = float(np.min(safety_factor))

            equilibrium = compute_equilibrium_check(
                mesh, k_global, u_global, f_ext, fixed_dofs
            )

            case_summaries.append(
                LoadCaseFemSummary(
                    load_case_id=load_case.id,
                    compliance=compliance,
                    displacement_stats=summarize_field(disp_mag, length_unit),
                    von_mises_stats=summarize_field(nodal_vm, stress_unit),
                    min_safety_factor=min_sf,
                    equilibrium=equilibrium,
                )
            )
            fields_by_case[load_case.id] = {
                "displacement": np.asarray(u_nodal, dtype=np.float32),
                "displacement_magnitude": np.asarray(disp_mag, dtype=np.float32),
                "von_mises": np.asarray(nodal_vm, dtype=np.float32),
                "safety_factor": np.asarray(safety_factor, dtype=np.float32),
            }

        bundle_bytes = pack_fem_fields_bundle(fields_by_case)
        summary = FemResultSummary(
            job_id=job_id,
            load_case_results=tuple(case_summaries),
            fields_artifact_key="",
        )
        return summary, bundle_bytes
