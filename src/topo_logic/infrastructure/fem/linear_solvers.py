"""Sparse linear elasticity solvers: Direct LU (splu) and PyAMG/Jacobi PCG."""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from numpy.typing import NDArray

from topo_logic.domain.exceptions import UnderconstrainedModelError
from topo_logic.domain.study import SolverKind

_DIRECT_DOF_THRESHOLD = 80_000


def _build_pcg_preconditioner(k_csr: sp.csr_matrix) -> spla.LinearOperator:
    try:
        import pyamg

        ml = pyamg.smoothed_aggregation_solver(k_csr)
        precond: spla.LinearOperator = ml.aspreconditioner(cycle="V")
        return precond
    except Exception:
        diag = k_csr.diagonal().astype(np.float64)
        safe_diag = np.where(np.abs(diag) > 1e-18, diag, 1.0)
        inv_diag = 1.0 / safe_diag
        n = k_csr.shape[0]
        return spla.LinearOperator(
            shape=(n, n),
            dtype=np.float64,
            matvec=lambda x: inv_diag * x,
        )


def solve_reduced_systems(
    k_ff: sp.csc_matrix,
    rhs_list: list[NDArray[np.float64]],
    *,
    solver_kind: SolverKind,
    x0_list: list[NDArray[np.float64]] | None = None,
) -> list[NDArray[np.float64]]:
    """Solve K_ff * u_f = f_f across multiple load-case RHS vectors."""
    n_free = int(k_ff.shape[0])
    if n_free == 0:
        return [np.empty(0, dtype=np.float64) for _ in rhs_list]

    diag = k_ff.diagonal()
    if np.any(diag <= 0.0) or not bool(np.all(np.isfinite(diag))):
        raise UnderconstrainedModelError(
            "Reduced stiffness matrix has non-positive diagonal pivots (rigid-body mode or "
            "disconnected component)."
        )

    effective_kind = solver_kind
    if effective_kind is SolverKind.AUTO:
        effective_kind = (
            SolverKind.DIRECT if n_free < _DIRECT_DOF_THRESHOLD else SolverKind.PCG_AMG
        )

    solutions: list[NDArray[np.float64]] = []
    if effective_kind is SolverKind.DIRECT:
        try:
            factor = spla.splu(k_ff.tocsc())
        except RuntimeError as exc:
            raise UnderconstrainedModelError(
                f"Direct sparse factorization failed (singular stiffness matrix): {exc}"
            ) from exc

        for rhs in rhs_list:
            sol = np.asarray(factor.solve(rhs), dtype=np.float64)
            if not bool(np.all(np.isfinite(sol))):
                raise UnderconstrainedModelError(
                    "Direct sparse solve produced non-finite displacements."
                )
            solutions.append(sol)
        return solutions

    # PCG with Algebraic Multigrid (PyAMG) or Jacobi fallback
    k_csr = k_ff.tocsr()
    precond = _build_pcg_preconditioner(k_csr)
    for idx, rhs in enumerate(rhs_list):
        if float(np.linalg.norm(rhs)) == 0.0:
            solutions.append(np.zeros(n_free, dtype=np.float64))
            continue
        x0 = None if x0_list is None else x0_list[idx]
        sol, info = spla.cg(k_csr, rhs, x0=x0, rtol=1e-9, atol=0.0, maxiter=5000, M=precond)
        if info != 0 or not bool(np.all(np.isfinite(sol))):
            raise UnderconstrainedModelError(
                f"PCG solver failed to converge cleanly (scipy info={info})."
            )
        solutions.append(np.asarray(sol, dtype=np.float64))
    return solutions
