"""FEM stress recovery, global equilibrium verification, and Float32 binary field packing."""

from __future__ import annotations

import io

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray

from topo_logic.domain.geometry import ElementType
from topo_logic.domain.materials import IsotropicMaterial
from topo_logic.domain.results import EquilibriumCheck, FieldStats
from topo_logic.domain.units import UnitSystem
from topo_logic.infrastructure.fem.elasticity import (
    c3d4_element_stiffness_and_b,
    c3d10_element_stiffness_and_b,
    h8_b_matrix_at_center,
    h8_general_stiffness_and_center_b,
    isotropic_constitutive_matrix,
)
from topo_logic.infrastructure.mesh.volume_mesh import VolumeMeshData


def compute_von_mises(stress_voigt: NDArray[np.float64]) -> NDArray[np.float64]:
    """Compute Von Mises stress from Voigt [xx, yy, zz, yz, xz, xy] stress rows."""
    sx = stress_voigt[..., 0]
    sy = stress_voigt[..., 1]
    sz = stress_voigt[..., 2]
    tyz = stress_voigt[..., 3]
    txz = stress_voigt[..., 4]
    txy = stress_voigt[..., 5]
    val = 0.5 * (
        (sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2 + 6.0 * (txy**2 + tyz**2 + txz**2)
    )
    return np.sqrt(np.maximum(val, 0.0))


def recover_nodal_stresses(
    mesh: VolumeMeshData,
    material: IsotropicMaterial,
    u_global: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Recover volume-averaged nodal Cauchy stresses and Von Mises equivalent stress."""
    n_nodes = len(mesh.nodes)
    n_elem = len(mesh.elements)
    d_matrix = isotropic_constitutive_matrix(material.youngs_modulus, material.poissons_ratio)
    dofs_per_elem = 3 * mesh.elements.shape[1]
    edof = (
        3 * mesh.elements[:, :, None] + np.arange(3, dtype=np.int32)[None, None, :]
    ).reshape(n_elem, dofs_per_elem)
    u_elem = u_global[edof]  # (N_elem, dofs_per_elem)

    nodal_stress_acc = np.zeros((n_nodes, 6), dtype=np.float64)
    nodal_vol_acc = np.zeros(n_nodes, dtype=np.float64)

    if mesh.element_type is ElementType.H8 and mesh.voxel_pitch is not None:
        hx, hy, hz = mesh.voxel_pitch
        b_center = h8_b_matrix_at_center(hx, hy, hz)
        elem_vol = hx * hy * hz
        db = d_matrix @ b_center  # (6, 24)
        elem_stress = u_elem @ db.T  # (N_elem, 6)
        weighted = elem_stress * elem_vol
        for local_node in range(8):
            node_ids = mesh.elements[:, local_node]
            np.add.at(nodal_stress_acc, node_ids, weighted)
            np.add.at(nodal_vol_acc, node_ids, elem_vol)
    else:
        for e_idx in range(n_elem):
            elem_nodes = mesh.elements[e_idx]
            coords = mesh.nodes[elem_nodes]
            ue = u_elem[e_idx]
            if mesh.element_type is ElementType.H8:
                _, b_mat, vol = h8_general_stiffness_and_center_b(coords, d_matrix)
                elem_stress = d_matrix @ (b_mat @ ue)
            elif mesh.element_type is ElementType.C3D4:
                _, b_mat, vol = c3d4_element_stiffness_and_b(coords, d_matrix)
                elem_stress = d_matrix @ (b_mat @ ue)
            else:
                _, b_gauss, dv_gauss, vol = c3d10_element_stiffness_and_b(coords, d_matrix)
                sigma_g = np.einsum("ij,gjk,k->gi", d_matrix, b_gauss, ue)
                elem_stress = np.sum(sigma_g * dv_gauss[:, None], axis=0) / vol

            nodal_stress_acc[elem_nodes] += elem_stress * vol
            nodal_vol_acc[elem_nodes] += vol

    safe_vol = np.where(nodal_vol_acc > 0.0, nodal_vol_acc, 1.0)
    nodal_stress = nodal_stress_acc / safe_vol[:, None]
    nodal_vm = compute_von_mises(nodal_stress)
    return nodal_stress, nodal_vm


def compute_equilibrium_check(
    mesh: VolumeMeshData,
    k_global: sp.csc_matrix,
    u_global: NDArray[np.float64],
    f_ext: NDArray[np.float64],
    fixed_dofs: NDArray[np.int32],
) -> EquilibriumCheck:
    """Verify global force and moment static equilibrium R + f_ext == 0."""
    residual_all = np.asarray(k_global @ u_global - f_ext, dtype=np.float64)
    reactions = np.zeros_like(residual_all)
    reactions[fixed_dofs] = residual_all[fixed_dofs]

    # Applied nodal forces on free DOFs + prescribed external loads
    # Note: external forces on fixed DOFs are absorbed into reactions when reporting R + f_ext.
    # On free DOFs: K_ff*u_f + K_fc*u_c = f_f; on fixed DOFs: R_c = (K*u)_c - f_c.
    # Thus R_c + f_c = (K*u)_c and 0 + f_f = (K*u)_f within solver tolerance.
    total_nodal = (reactions + f_ext).reshape(-1, 3)
    force_residual_vec = np.sum(total_nodal, axis=0)
    force_residual_norm = float(np.linalg.norm(force_residual_vec))

    # Measure applied load magnitude on free DOFs (or total external force norm if non-zero)
    f_nodal = f_ext.reshape(-1, 3)
    applied_force_norm = float(np.linalg.norm(f_ext))
    if applied_force_norm == 0.0:
        applied_force_norm = float(np.linalg.norm(total_nodal))

    relative_error = (
        force_residual_norm / applied_force_norm if applied_force_norm > 0.0 else 0.0
    )

    moments = np.cross(mesh.nodes, total_nodal)
    moment_residual_norm = float(np.linalg.norm(np.sum(moments, axis=0)))
    if np.sum(np.linalg.norm(f_nodal, axis=1)) == 0.0 and relative_error == 0.0:
        is_balanced = True
    else:
        is_balanced = relative_error < 1e-6

    return EquilibriumCheck(
        force_residual_norm=force_residual_norm,
        applied_force_norm=applied_force_norm,
        relative_force_error=relative_error,
        moment_residual_norm=moment_residual_norm,
        is_balanced=is_balanced,
    )


def summarize_field(values: NDArray[np.float64], unit: str) -> FieldStats:
    return FieldStats(
        min_value=float(np.min(values)),
        max_value=float(np.max(values)),
        mean_value=float(np.mean(values)),
        unit=unit,
    )


def pack_fem_fields_bundle(fields_by_case: dict[str, dict[str, NDArray[np.float32]]]) -> bytes:
    """Pack per-loadcase Float32 arrays into a single compressed .npz bundle."""
    flat: dict[str, object] = {}
    for lc_id, fields in fields_by_case.items():
        for name, arr in fields.items():
            flat[f"{lc_id}__{name}"] = np.ascontiguousarray(arr, dtype="<f4")
    buf = io.BytesIO()
    np.savez_compressed(buf, **flat)  # type: ignore[arg-type]
    return buf.getvalue()


def extract_binary_field(
    bundle_bytes: bytes,
    *,
    load_case_id: str,
    field_name: str,
    unit_system: UnitSystem,
) -> tuple[bytes, dict[str, str]]:
    """Extract raw little-endian Float32 buffer and metadata headers for client visualization."""
    key = f"{load_case_id}__{field_name}"
    with np.load(io.BytesIO(bundle_bytes), allow_pickle=False) as archive:
        if key not in archive:
            raise KeyError(key)
        arr = np.ascontiguousarray(archive[key], dtype="<f4")

    length_unit = "mm" if unit_system is UnitSystem.MM_N_MPA else "m"
    stress_unit = "MPa" if unit_system is UnitSystem.MM_N_MPA else "Pa"
    unit_map = {
        "displacement": length_unit,
        "displacement_magnitude": length_unit,
        "von_mises": stress_unit,
        "safety_factor": "ratio",
    }
    shape_str = ",".join(str(dim) for dim in arr.shape)
    headers = {
        "X-Topo-Dtype": "float32",
        "X-Topo-Shape": shape_str,
        "X-Topo-Unit": unit_map.get(field_name, ""),
        "X-Topo-Min": f"{float(np.min(arr)):.9g}",
        "X-Topo-Max": f"{float(np.max(arr)):.9g}",
    }
    return arr.tobytes(), headers
