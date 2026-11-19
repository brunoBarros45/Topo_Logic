"""Relaxed P-norm Von Mises stress aggregation and exact adjoint sensitivity.

Adaptive scaling and P-norm aggregation concepts adapted from pyMOTO
(https://github.com/aatmdelissen/pyMOTO), Copyright (c) 2023 Arnoud Delissen, MIT License.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

_VON_MISES_V: NDArray[np.float64] = np.array(
    [
        [1.0, -0.5, -0.5, 0.0, 0.0, 0.0],
        [-0.5, 1.0, -0.5, 0.0, 0.0, 0.0],
        [-0.5, -0.5, 1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 3.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 3.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 3.0],
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class StressAggregationResult:
    """Normalized P-norm stress ratio, peak Von Mises stress, and physical density gradient."""

    pnorm_ratio: float
    max_von_mises: float
    dpnorm_drho_phys: NDArray[np.float64]


def compute_relaxed_pnorm_stress_and_adjoint(
    *,
    edof: NDArray[np.int32],
    d_matrix: NDArray[np.float64],
    b_center: NDArray[np.float64],
    k0: NDArray[np.float64],
    rho_phys: NDArray[np.float64],
    u_list: list[NDArray[np.float64]],
    free_dofs: NDArray[np.int32],
    ndof: int,
    solve_free_rhs: Callable[[list[NDArray[np.float64]]], list[NDArray[np.float64]]],
    max_von_mises: float,
    p_norm: float,
    simp_penalty: float,
    e_min_ratio: float,
    relax_q: float = 0.5,
) -> StressAggregationResult:
    """Compute relaxed P-norm Von Mises stress (sigma / sigma_max) and exact adjoint gradient."""
    n_elem = len(rho_phys)
    db = d_matrix @ b_center  # (6, 24)
    rho_safe = np.maximum(rho_phys, 1e-8)
    relax = rho_safe**relax_q
    drelax_drho = relax_q * (rho_safe ** (relax_q - 1.0))

    eps_stress = 1e-8 * max_von_mises
    sigma0_list: list[NDArray[np.float64]] = []
    sigma_hat_list: list[NDArray[np.float64]] = []
    vm_list: list[NDArray[np.float64]] = []

    max_vm = 0.0
    for u_global in u_list:
        u_elem = u_global[edof]  # (n_elem, 24)
        sigma0 = u_elem @ db.T  # (n_elem, 6)
        sigma_hat = relax[:, None] * sigma0
        v_sigma = sigma_hat @ _VON_MISES_V
        vm_sq = np.sum(sigma_hat * v_sigma, axis=1) + (eps_stress * eps_stress)
        vm = np.sqrt(np.maximum(vm_sq, eps_stress * eps_stress))
        max_vm = max(max_vm, float(np.max(vm)))
        sigma0_list.append(sigma0)
        sigma_hat_list.append(sigma_hat)
        vm_list.append(vm)

    r_peak = max(max_vm / max_von_mises, 1e-12)
    s_sum = 0.0
    for vm in vm_list:
        r_scaled = (vm / max_von_mises) / r_peak
        s_sum += float(np.sum(r_scaled**p_norm))

    pnorm_ratio = r_peak * (s_sum ** (1.0 / p_norm))
    s_pow = s_sum ** ((1.0 / p_norm) - 1.0)

    dpnorm_drho_explicit = np.zeros(n_elem, dtype=np.float64)
    adj_rhs_free_list: list[NDArray[np.float64]] = []

    for sigma0, sigma_hat, vm in zip(sigma0_list, sigma_hat_list, vm_list, strict=True):
        r_scaled = (vm / max_von_mises) / r_peak
        dpnorm_dvm = (1.0 / max_von_mises) * s_pow * (r_scaled ** (p_norm - 1.0))
        v_sigma = sigma_hat @ _VON_MISES_V
        dpnorm_dsigma_hat = (dpnorm_dvm / vm)[:, None] * v_sigma  # (n_elem, 6)

        dpnorm_drho_explicit += (
            np.sum(dpnorm_dsigma_hat * sigma0, axis=1) * drelax_drho
        )

        # Element adjoint load vector f_adj_e = rho_safe^q * (DB)^T * dpnorm_dsigma_hat
        f_adj_elem = (relax[:, None] * dpnorm_dsigma_hat) @ db  # (n_elem, 24)
        f_adj_global = np.zeros(ndof, dtype=np.float64)
        np.add.at(f_adj_global, edof, f_adj_elem)
        adj_rhs_free_list.append(f_adj_global[free_dofs])

    lam_free_list = solve_free_rhs(adj_rhs_free_list)
    dk_factor = simp_penalty * (rho_safe ** (simp_penalty - 1.0)) * (1.0 - e_min_ratio)

    dpnorm_drho_adjoint = np.zeros(n_elem, dtype=np.float64)
    for u_global, lam_free in zip(u_list, lam_free_list, strict=True):
        lam_global = np.zeros(ndof, dtype=np.float64)
        lam_global[free_dofs] = lam_free
        lam_elem = lam_global[edof]
        u_elem = u_global[edof]
        elem_dot = np.sum((lam_elem @ k0) * u_elem, axis=1)
        dpnorm_drho_adjoint -= dk_factor * elem_dot

    return StressAggregationResult(
        pnorm_ratio=pnorm_ratio,
        max_von_mises=max_vm,
        dpnorm_drho_phys=dpnorm_drho_explicit + dpnorm_drho_adjoint,
    )
