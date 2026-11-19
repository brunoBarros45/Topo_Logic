"""Sparse cone density filters and smooth Heaviside projection with exact adjoints."""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from topo_logic.domain.exceptions import DomainValidationError
from topo_logic.domain.study import FilterKind


class ConeDensityFilter:
    """Linear spatial cone filter H * rho / Hs built in O(N log N) via cKDTree."""

    def __init__(self, element_centers: NDArray[np.float64], filter_radius: float) -> None:
        if filter_radius <= 0.0:
            raise DomainValidationError("filter_radius must be strictly positive.")
        n_elem = len(element_centers)
        if n_elem == 0:
            raise DomainValidationError("Cannot build density filter for zero elements.")

        tree = cKDTree(element_centers)
        pairs = tree.query_pairs(r=filter_radius, output_type="ndarray")

        diag_idx = np.arange(n_elem, dtype=np.int32)
        diag_vals = np.full(n_elem, filter_radius, dtype=np.float64)

        if len(pairs) > 0:
            diff = element_centers[pairs[:, 0]] - element_centers[pairs[:, 1]]
            dist = np.linalg.norm(diff, axis=1)
            weights = filter_radius - dist
            keep = weights > 0.0
            p0 = pairs[keep, 0].astype(np.int32)
            p1 = pairs[keep, 1].astype(np.int32)
            w_keep = weights[keep]
            rows = np.concatenate([diag_idx, p0, p1])
            cols = np.concatenate([diag_idx, p1, p0])
            vals = np.concatenate([diag_vals, w_keep, w_keep])
        else:
            rows = diag_idx
            cols = diag_idx
            vals = diag_vals

        self._h = sp.coo_matrix((vals, (rows, cols)), shape=(n_elem, n_elem)).tocsr()
        self._hs = np.asarray(self._h.sum(axis=1), dtype=np.float64).ravel()

    @property
    def matrix(self) -> sp.csr_matrix:
        return self._h

    @property
    def row_sums(self) -> NDArray[np.float64]:
        return self._hs

    def apply_forward(self, raw_densities: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.asarray((self._h @ raw_densities) / self._hs, dtype=np.float64)

    def apply_adjoint(self, df_drho_hat: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.asarray(self._h.T @ (df_drho_hat / self._hs), dtype=np.float64)


def heaviside_project(
    rho_hat: NDArray[np.float64], beta: float, eta: float = 0.5
) -> NDArray[np.float64]:
    """Smooth threshold projection pushing intermediate densities toward 0/1."""
    denom = float(np.tanh(beta * eta) + np.tanh(beta * (1.0 - eta)))
    return np.asarray(
        (np.tanh(beta * eta) + np.tanh(beta * (rho_hat - eta))) / denom,
        dtype=np.float64,
    )


def heaviside_derivative(
    rho_hat: NDArray[np.float64], beta: float, eta: float = 0.5
) -> NDArray[np.float64]:
    """Exact derivative d(rho_bar) / d(rho_hat) for adjoint chain rule."""
    denom = float(np.tanh(beta * eta) + np.tanh(beta * (1.0 - eta)))
    tanh_val = np.tanh(beta * (rho_hat - eta))
    sech2 = 1.0 - tanh_val * tanh_val
    return np.asarray((beta * sech2) / denom, dtype=np.float64)


class CompositeDensityFilter:
    """Composes spatial cone filtering with optional smooth Heaviside projection."""

    def __init__(self, cone: ConeDensityFilter, filter_kind: FilterKind) -> None:
        self._cone = cone
        self._kind = filter_kind

    def forward(
        self, raw_densities: NDArray[np.float64], *, beta: float = 1.0
    ) -> NDArray[np.float64]:
        rho_hat = self._cone.apply_forward(raw_densities)
        if self._kind is FilterKind.HEAVISIDE_PROJECTION:
            return heaviside_project(rho_hat, beta=beta)
        return rho_hat

    def adjoint(
        self,
        df_drho_phys: NDArray[np.float64],
        raw_densities: NDArray[np.float64],
        *,
        beta: float = 1.0,
    ) -> NDArray[np.float64]:
        if self._kind is FilterKind.HEAVISIDE_PROJECTION:
            rho_hat = self._cone.apply_forward(raw_densities)
            df_drho_hat = df_drho_phys * heaviside_derivative(rho_hat, beta=beta)
            return self._cone.apply_adjoint(df_drho_hat)
        return self._cone.apply_adjoint(df_drho_phys)
