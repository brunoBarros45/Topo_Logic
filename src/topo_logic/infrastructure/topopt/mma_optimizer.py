"""Method of Moving Asymptotes (MMA2007) optimizer for multi-constraint TopOpt.

Adapted from pyMOTO (https://github.com/aatmdelissen/pyMOTO),
Copyright (c) 2023 Arnoud Delissen, MIT License.
Reference: Svanberg, K. (2007), "MMA and GCMMA - two methods for nonlinear optimization".
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from topo_logic.domain.exceptions import DomainValidationError


class MmaOptimizer:
    """Primal-dual Method of Moving Asymptotes (MMA2007) for bound-constrained problems."""

    def __init__(
        self,
        n_vars: int,
        n_constraints: int,
        *,
        move: float = 0.2,
        xmin: float = 0.0,
        xmax: float = 1.0,
        c_coef: float = 1e3,
        epsimin: float = 1e-9,
    ) -> None:
        if n_vars < 1:
            raise DomainValidationError("MmaOptimizer requires at least 1 design variable.")
        if n_constraints < 0:
            raise DomainValidationError("n_constraints must be non-negative.")

        self._n = n_vars
        self._m = max(1, n_constraints)
        self._has_dummy_constraint = n_constraints == 0
        self._move = move
        self._xmin = np.full(n_vars, xmin, dtype=np.float64)
        self._xmax = np.full(n_vars, xmax, dtype=np.float64)
        self._dx = self._xmax - self._xmin

        self._albefa = 0.1
        self._asyinit = 0.5
        self._asyincr = 1.2
        self._asydecr = 0.7
        self._asybound = 10.0
        self._epsimin = epsimin

        self._a0 = 1.0
        self._a = np.zeros(self._m, dtype=np.float64)
        self._c = np.full(self._m, c_coef, dtype=np.float64)
        self._d = np.ones(self._m, dtype=np.float64)

        self._offset = np.full(n_vars, self._asyinit, dtype=np.float64)
        self._xold1: NDArray[np.float64] | None = None
        self._xold2: NDArray[np.float64] | None = None

    def step(
        self,
        *,
        x: NDArray[np.float64],
        f0: float,
        df0: NDArray[np.float64],
        g: NDArray[np.float64] | None = None,
        dg: NDArray[np.float64] | None = None,
    ) -> NDArray[np.float64]:
        """Compute one MMA2007 update given objective f0 and constraints g <= 0."""
        xval = np.asarray(x, dtype=np.float64)
        if xval.shape != (self._n,) or df0.shape != (self._n,):
            raise DomainValidationError("MMA design or objective gradient shape mismatch.")

        if self._has_dummy_constraint:
            g_stack = np.array([f0, -1.0], dtype=np.float64)
            dg_stack = np.vstack([df0[None, :], np.zeros((1, self._n), dtype=np.float64)])
        else:
            if g is None or dg is None:
                raise DomainValidationError("MMA constraints g and dg are required.")
            if g.shape != (self._m,) or dg.shape != (self._m, self._n):
                raise DomainValidationError("MMA constraint value or Jacobian shape mismatch.")
            g_stack = np.concatenate([np.array([f0], dtype=np.float64), g])
            dg_stack = np.vstack([df0[None, :], dg])

        if self._xold1 is not None and self._xold2 is not None:
            zzz = (xval - self._xold1) * (self._xold1 - self._xold2)
            self._offset[zzz > 0.0] *= self._asyincr
            self._offset[zzz < 0.0] *= self._asydecr
            self._offset = np.clip(
                self._offset, 1.0 / (self._asybound**2), self._asybound
            )

        shift = self._offset * self._dx
        low = xval - shift
        upp = xval + shift

        alfa = np.maximum.reduce(
            [low + self._albefa * shift, xval - self._move * self._dx, self._xmin]
        )
        beta = np.minimum.reduce(
            [upp - self._albefa * shift, xval + self._move * self._dx, self._xmax]
        )

        dg_plus = np.maximum(dg_stack, 0.0)
        dg_min = np.maximum(-dg_stack, 0.0)
        dx2 = shift * shift
        rho_term = 1e-5 / self._dx
        p_mat = dx2 * (1.001 * dg_plus + 0.001 * dg_min + rho_term)
        q_mat = dx2 * (0.001 * dg_plus + 1.001 * dg_min + rho_term)

        inv_shift = 1.0 / shift
        rhs = (p_mat @ inv_shift) + (q_mat @ inv_shift) - g_stack
        epsimin_scaled = self._epsimin * math.sqrt(self._m + self._n)

        xnew = _subsolv(
            epsimin=epsimin_scaled,
            low=low,
            upp=upp,
            alfa=alfa,
            beta=beta,
            p_mat=p_mat,
            q_mat=q_mat,
            a0=self._a0,
            a=self._a,
            b=rhs[1:],
            c=self._c,
            d=self._d,
            x0=xval,
        )

        self._xold2 = self._xold1
        self._xold1 = xval.copy()
        return np.clip(xnew, self._xmin, self._xmax)


def _subsolv(
    *,
    epsimin: float,
    low: NDArray[np.float64],
    upp: NDArray[np.float64],
    alfa: NDArray[np.float64],
    beta: NDArray[np.float64],
    p_mat: NDArray[np.float64],
    q_mat: NDArray[np.float64],
    a0: float,
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    c: NDArray[np.float64],
    d: NDArray[np.float64],
    x0: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Primal-dual interior-point Newton solver for the convex MMA subproblem."""
    n, m = len(alfa), len(a)
    epsi = 1.0
    max_newton = 200
    x = np.clip(x0.copy(), alfa + 1e-10, beta - 1e-10)
    y = np.ones(m, dtype=np.float64)
    z = 1.0
    lam = np.ones(m, dtype=np.float64)
    gg = np.empty((m, n), dtype=np.float64)

    xsi = np.maximum(1.0 / np.maximum(x - alfa, 1e-12), 1.0)
    eta = np.maximum(1.0 / np.maximum(beta - x, 1e-12), 1.0)
    mu = np.maximum(1.0, 0.5 * c)
    zet = 1.0
    s = np.ones(m, dtype=np.float64)
    bb = np.empty(m + 1, dtype=np.float64)
    aa = np.empty((m + 1, m + 1), dtype=np.float64)

    p0 = np.ascontiguousarray(p_mat[0, :])
    q0 = np.ascontiguousarray(q_mat[0, :])
    p1 = np.ascontiguousarray(p_mat[1:, :])
    q1 = np.ascontiguousarray(q_mat[1:, :])

    def _compute_residual() -> tuple[float, float]:
        ux1 = upp - x
        xl1 = x - low
        plam = p0 + lam @ p1
        qlam = q0 + lam @ q1
        gvec = (p1 @ (1.0 / ux1)) + (q1 @ (1.0 / xl1))
        dpsidx = plam / (ux1 * ux1) - qlam / (xl1 * xl1)
        residu = np.concatenate(
            [
                dpsidx - xsi + eta,
                c + d * y - mu - lam,
                np.array([a0 - zet - float(np.dot(a, lam))], dtype=np.float64),
                gvec - a * z - y + s - b,
                xsi * (x - alfa) - epsi,
                eta * (beta - x) - epsi,
                mu * y - epsi,
                np.array([zet * z - epsi], dtype=np.float64),
                lam * s - epsi,
            ]
        )
        resi2 = residu * residu
        return float(resi2.sum()), float(resi2.max())

    while epsi > epsimin:
        residunorm, residumax = _compute_residual()
        ittt = 0
        while residumax > (0.9 * epsi) ** 2 and ittt < max_newton:
            ittt += 1
            ux1 = upp - x
            xl1 = x - low
            ux2 = ux1 * ux1
            xl2 = xl1 * xl1
            uxinv1 = 1.0 / ux1
            xlinv1 = 1.0 / xl1
            uxinv2 = 1.0 / ux2
            xlinv2 = 1.0 / xl2

            plam = p0 + lam @ p1
            qlam = q0 + lam @ q1
            gvec = (p1 @ uxinv1) + (q1 @ xlinv1)
            gg[:, :] = p1 * uxinv2 - q1 * xlinv2
            dpsidx = plam * uxinv2 - qlam * xlinv2

            delx = dpsidx - epsi / (x - alfa) + epsi / (beta - x)
            dely = c + d * y - lam - epsi / y
            delz = a0 - float(np.dot(a, lam)) - epsi / z
            dellam = gvec - a * z - y - b + epsi / lam

            diagx = (
                2.0 * (plam / (ux1 * ux2) + qlam / (xl1 * xl2))
                + xsi / (x - alfa)
                + eta / (beta - x)
            )
            diagy = d + mu / y
            diaglamyi = s / lam + 1.0 / diagy

            bb[:-1] = dellam + dely / diagy - gg @ (delx / diagx)
            bb[-1] = delz

            aa[:-1, :-1] = np.diag(diaglamyi) + (gg / diagx) @ gg.T
            aa[-1, :-1] = a
            aa[:-1, -1] = a
            aa[-1, -1] = -zet / z

            solut = np.linalg.solve(aa, bb)
            dlam = solut[:m]
            dz = float(solut[m])
            dx = -delx / diagx - (dlam @ gg) / diagx
            dy = -dely / diagy + dlam / diagy
            dxsi = -xsi + epsi / (x - alfa) - (xsi * dx) / (x - alfa)
            deta = -eta + epsi / (beta - x) + (eta * dx) / (beta - x)
            dmu = -mu + epsi / y - (mu * dy) / y
            dzet = -zet + epsi / z - (zet * dz) / z
            ds = -s + epsi / lam - (s * dlam) / lam

            stmxx = max(
                float(-1.01 * np.min(dy / y)),
                -1.01 * dz / z,
                float(-1.01 * np.min(dlam / lam)),
                float(-1.01 * np.min(dxsi / xsi)),
                float(-1.01 * np.min(deta / eta)),
                float(-1.01 * np.min(dmu / mu)),
                -1.01 * dzet / zet,
                float(-1.01 * np.min(ds / s)),
            )
            stmalfa = float(-1.01 * np.min(dx / (x - alfa)))
            stmbeta = float(1.01 * np.max(dx / (beta - x)))
            steg = 1.0 / max(stmalfa, stmbeta, stmxx, 1.0)

            xold, yold, zold = x.copy(), y.copy(), z
            lamold, xsiold, etaold = lam.copy(), xsi.copy(), eta.copy()
            muold, zetold, sold = mu.copy(), zet, s.copy()

            for _ in range(40):
                x[:] = xold + steg * dx
                y[:] = yold + steg * dy
                z = zold + steg * dz
                lam[:] = lamold + steg * dlam
                xsi[:] = xsiold + steg * dxsi
                eta[:] = etaold + steg * deta
                mu[:] = muold + steg * dmu
                zet = zetold + steg * dzet
                s[:] = sold + steg * ds

                next_norm, next_max = _compute_residual()
                if next_norm < residunorm:
                    residunorm = next_norm
                    residumax = next_max
                    break
                steg *= 0.5
            else:
                residunorm, residumax = _compute_residual()

        epsi *= 0.1

    return x
