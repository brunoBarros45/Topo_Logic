"""3D linear elasticity constitutive models, element formulations, and sparse assembly."""

from __future__ import annotations

import math

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray

from topo_logic.domain.exceptions import DomainValidationError, InvalidGeometryError
from topo_logic.domain.geometry import ElementType
from topo_logic.domain.materials import IsotropicMaterial
from topo_logic.infrastructure.mesh.volume_mesh import VolumeMeshData

_H8_CORNERS: NDArray[np.float64] = np.array(
    [
        [-1.0, -1.0, -1.0],
        [1.0, -1.0, -1.0],
        [1.0, 1.0, -1.0],
        [-1.0, 1.0, -1.0],
        [-1.0, -1.0, 1.0],
        [1.0, -1.0, 1.0],
        [1.0, 1.0, 1.0],
        [-1.0, 1.0, 1.0],
    ],
    dtype=np.float64,
)


def isotropic_constitutive_matrix(
    youngs_modulus: float, poissons_ratio: float
) -> NDArray[np.float64]:
    """Build 6x6 Hooke's law matrix D in Voigt notation [xx, yy, zz, yz, xz, xy]."""
    lam = (
        youngs_modulus
        * poissons_ratio
        / ((1.0 + poissons_ratio) * (1.0 - 2.0 * poissons_ratio))
    )
    mu = youngs_modulus / (2.0 * (1.0 + poissons_ratio))
    diag_n = lam + 2.0 * mu
    return np.array(
        [
            [diag_n, lam, lam, 0.0, 0.0, 0.0],
            [lam, diag_n, lam, 0.0, 0.0, 0.0],
            [lam, lam, diag_n, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, mu, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, mu, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, mu],
        ],
        dtype=np.float64,
    )


def _assemble_b_from_dnds(dnds: NDArray[np.float64]) -> NDArray[np.float64]:
    """Build (6, 3*N) strain-displacement matrix B from (3, N) shape derivatives."""
    n_nodes = dnds.shape[1]
    b_mat = np.zeros((6, 3 * n_nodes), dtype=np.float64)
    idx_u = np.arange(0, 3 * n_nodes, 3)
    idx_v = idx_u + 1
    idx_w = idx_u + 2

    dn_dx = dnds[0, :]
    dn_dy = dnds[1, :]
    dn_dz = dnds[2, :]

    b_mat[0, idx_u] = dn_dx
    b_mat[1, idx_v] = dn_dy
    b_mat[2, idx_w] = dn_dz

    # Voigt engineering shears: [gamma_yz, gamma_xz, gamma_xy]
    b_mat[3, idx_v] = dn_dz
    b_mat[3, idx_w] = dn_dy

    b_mat[4, idx_u] = dn_dz
    b_mat[4, idx_w] = dn_dx

    b_mat[5, idx_u] = dn_dy
    b_mat[5, idx_v] = dn_dx
    return b_mat


def _h8_shape_derivatives(
    xi: float, eta: float, zeta: float, hx: float, hy: float, hz: float
) -> NDArray[np.float64]:
    """Return (3, 8) spatial derivatives dN/d(x,y,z) for an orthogonal H8 brick."""
    xi_c = _H8_CORNERS[:, 0]
    eta_c = _H8_CORNERS[:, 1]
    zeta_c = _H8_CORNERS[:, 2]

    dn_dxi = 0.125 * xi_c * (1.0 + eta_c * eta) * (1.0 + zeta_c * zeta)
    dn_deta = 0.125 * (1.0 + xi_c * xi) * eta_c * (1.0 + zeta_c * zeta)
    dn_dzeta = 0.125 * (1.0 + xi_c * xi) * (1.0 + eta_c * eta) * zeta_c

    return np.vstack(
        [
            (2.0 / hx) * dn_dxi,
            (2.0 / hy) * dn_deta,
            (2.0 / hz) * dn_dzeta,
        ]
    )


def h8_b_matrix_at_center(hx: float, hy: float, hz: float) -> NDArray[np.float64]:
    """Evaluate (6, 24) strain-displacement matrix B at the H8 brick centroid."""
    return _assemble_b_from_dnds(_h8_shape_derivatives(0.0, 0.0, 0.0, hx, hy, hz))


def h8_brick_stiffness(
    hx: float, hy: float, hz: float, d_matrix: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Compute exact 24x24 H8 brick stiffness matrix via 2x2x2 Gauss-Legendre integration."""
    gp = 1.0 / math.sqrt(3.0)
    det_j = (hx * hy * hz) / 8.0
    ke = np.zeros((24, 24), dtype=np.float64)
    for xi in (-gp, gp):
        for eta in (-gp, gp):
            for zeta in (-gp, gp):
                b_mat = _assemble_b_from_dnds(_h8_shape_derivatives(xi, eta, zeta, hx, hy, hz))
                ke += (b_mat.T @ d_matrix @ b_mat) * det_j
    return 0.5 * (ke + ke.T)


def h8_general_stiffness_and_center_b(
    coords: NDArray[np.float64], d_matrix: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
    """Compute isoparametric 24x24 stiffness, centroid B-matrix, and volume for arbitrary H8."""
    gp = 1.0 / math.sqrt(3.0)
    xi_c = _H8_CORNERS[:, 0]
    eta_c = _H8_CORNERS[:, 1]
    zeta_c = _H8_CORNERS[:, 2]

    def _dnds_ref(xi: float, eta: float, zeta: float) -> NDArray[np.float64]:
        return np.vstack(
            [
                0.125 * xi_c * (1.0 + eta_c * eta) * (1.0 + zeta_c * zeta),
                0.125 * (1.0 + xi_c * xi) * eta_c * (1.0 + zeta_c * zeta),
                0.125 * (1.0 + xi_c * xi) * (1.0 + eta_c * eta) * zeta_c,
            ]
        )

    ke = np.zeros((24, 24), dtype=np.float64)
    volume = 0.0
    for xi in (-gp, gp):
        for eta in (-gp, gp):
            for zeta in (-gp, gp):
                dn_ref = _dnds_ref(xi, eta, zeta)
                jac = dn_ref @ coords
                det_j = float(np.linalg.det(jac))
                if det_j <= 0.0:
                    raise InvalidGeometryError("Degenerate or inverted H8 element encountered.")
                dnds = np.linalg.solve(jac, dn_ref)
                b_mat = _assemble_b_from_dnds(dnds)
                ke += (b_mat.T @ d_matrix @ b_mat) * det_j
                volume += det_j

    dn_center = _dnds_ref(0.0, 0.0, 0.0)
    jac_c = dn_center @ coords
    b_center = _assemble_b_from_dnds(np.linalg.solve(jac_c, dn_center))
    return 0.5 * (ke + ke.T), b_center, volume


def c3d4_element_stiffness_and_b(
    coords: NDArray[np.float64], d_matrix: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
    """Compute exact 12x12 stiffness, (6, 12) B-matrix, and volume for a linear C3D4 tet."""
    mat = np.column_stack([np.ones(4, dtype=np.float64), coords])
    det = float(np.linalg.det(mat))
    volume = det / 6.0
    if volume <= 0.0:
        raise InvalidGeometryError("Degenerate or inverted C3D4 tetrahedron encountered.")
    inv_m = np.linalg.inv(mat)
    dnds = inv_m[1:4, :]
    b_mat = _assemble_b_from_dnds(dnds)
    ke = (b_mat.T @ d_matrix @ b_mat) * volume
    return 0.5 * (ke + ke.T), b_mat, volume


def _c3d10_ref_derivatives(r: float, s: float, t: float) -> NDArray[np.float64]:
    """Return (3, 10) derivatives dN/d(r, s, t) for canonical C3D10 quadratic tet."""
    l0 = 1.0 - r - s - t
    # dL / d(r, s, t): L0=(-1,-1,-1), L1=(1,0,0), L2=(0,1,0), L3=(0,0,1)
    dl = np.array(
        [
            [-1.0, 1.0, 0.0, 0.0],
            [-1.0, 0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    l_vals = np.array([l0, r, s, t], dtype=np.float64)

    dnds = np.zeros((3, 10), dtype=np.float64)
    for a in range(4):
        dnds[:, a] = (4.0 * l_vals[a] - 1.0) * dl[:, a]

    mid_pairs = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))
    for offset, (i, j) in enumerate(mid_pairs, start=4):
        dnds[:, offset] = 4.0 * (l_vals[j] * dl[:, i] + l_vals[i] * dl[:, j])
    return dnds


def c3d10_element_stiffness_and_b(
    coords: NDArray[np.float64], d_matrix: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], float]:
    """Compute 30x30 stiffness, (4, 6, 30) B-matrices, Gauss dV, and volume for C3D10."""
    alpha = (5.0 + 3.0 * math.sqrt(5.0)) / 20.0
    beta = (5.0 - math.sqrt(5.0)) / 20.0
    gauss_pts = (
        (beta, beta, beta),
        (alpha, beta, beta),
        (beta, alpha, beta),
        (beta, beta, alpha),
    )
    weight = 1.0 / 24.0

    ke = np.zeros((30, 30), dtype=np.float64)
    b_list: list[NDArray[np.float64]] = []
    dv_list: list[float] = []

    for r, s, t in gauss_pts:
        dn_ref = _c3d10_ref_derivatives(r, s, t)
        jac = dn_ref @ coords
        det_j = float(np.linalg.det(jac))
        if det_j <= 0.0:
            raise InvalidGeometryError("Degenerate or inverted C3D10 tetrahedron encountered.")
        dnds = np.linalg.solve(jac, dn_ref)
        b_mat = _assemble_b_from_dnds(dnds)
        dv = weight * det_j
        ke += (b_mat.T @ d_matrix @ b_mat) * dv
        b_list.append(b_mat)
        dv_list.append(dv)

    dv_arr = np.asarray(dv_list, dtype=np.float64)
    return 0.5 * (ke + ke.T), np.stack(b_list, axis=0), dv_arr, float(np.sum(dv_arr))


def assemble_global_stiffness(
    mesh: VolumeMeshData,
    material: IsotropicMaterial,
    element_scale: NDArray[np.float64] | None = None,
) -> sp.csc_matrix:
    """Assemble global sparse symmetric stiffness matrix K in CSC format."""
    n_nodes = len(mesh.nodes)
    n_elem = len(mesh.elements)
    ndof = 3 * n_nodes
    if n_elem == 0:
        raise DomainValidationError("Cannot assemble stiffness matrix for an empty mesh.")

    if element_scale is not None and len(element_scale) != n_elem:
        raise DomainValidationError(
            "element_scale length must match number of volumetric elements."
        )

    d_matrix = isotropic_constitutive_matrix(material.youngs_modulus, material.poissons_ratio)
    nodes_per_elem = mesh.elements.shape[1]
    dofs_per_elem = 3 * nodes_per_elem

    edof = (
        3 * mesh.elements[:, :, None] + np.arange(3, dtype=np.int32)[None, None, :]
    ).reshape(n_elem, dofs_per_elem)

    # Fast vectorized assembly path for uniform H8 voxel grids
    if mesh.element_type is ElementType.H8 and mesh.voxel_pitch is not None:
        hx, hy, hz = mesh.voxel_pitch
        k0 = h8_brick_stiffness(hx, hy, hz, d_matrix)
        scales = (
            np.ones(n_elem, dtype=np.float64)
            if element_scale is None
            else np.asarray(element_scale, dtype=np.float64)
        )
        rows = np.repeat(edof, dofs_per_elem, axis=1).ravel()
        cols = np.tile(edof, (1, dofs_per_elem)).ravel()
        vals = (scales[:, None] * k0.ravel()[None, :]).ravel()
        return sp.coo_matrix((vals, (rows, cols)), shape=(ndof, ndof)).tocsc()

    rows = np.repeat(edof, dofs_per_elem, axis=1).ravel()
    cols = np.tile(edof, (1, dofs_per_elem)).ravel()
    vals = np.empty(n_elem * dofs_per_elem * dofs_per_elem, dtype=np.float64)
    block_size = dofs_per_elem * dofs_per_elem

    for e_idx in range(n_elem):
        coords = mesh.nodes[mesh.elements[e_idx]]
        if mesh.element_type is ElementType.H8:
            ke, _, _ = h8_general_stiffness_and_center_b(coords, d_matrix)
        elif mesh.element_type is ElementType.C3D4:
            ke, _, _ = c3d4_element_stiffness_and_b(coords, d_matrix)
        elif mesh.element_type is ElementType.C3D10:
            ke, _, _, _ = c3d10_element_stiffness_and_b(coords, d_matrix)
        else:
            raise DomainValidationError(f"Unsupported element type '{mesh.element_type.value}'.")

        scale = 1.0 if element_scale is None else float(element_scale[e_idx])
        start = e_idx * block_size
        vals[start : start + block_size] = (scale * ke).ravel()

    return sp.coo_matrix((vals, (rows, cols)), shape=(ndof, ndof)).tocsc()
