"""Optimality Criteria (OC) update scheme with bisection for 3D SIMP compliance."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray


def oc_update(
    *,
    x: NDArray[np.float64],
    dc: NDArray[np.float64],
    dv: NDArray[np.float64],
    target_volume: float,
    elem_volumes: NDArray[np.float64],
    filter_fn: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    passive_solid: NDArray[np.bool_],
    passive_void: NDArray[np.bool_],
    move_limit: float = 0.2,
    xmin: float = 1e-4,
) -> NDArray[np.float64]:
    """Update design variables via Optimality Criteria bisection on volume constraint."""
    free_mask = ~(passive_solid | passive_void)
    if not np.any(free_mask):
        return x.copy()

    x_free = x[free_mask]
    # Compliance sensitivity is negative; guard tiny positive numerical noise cleanly
    ratio = np.maximum(1e-30, -dc[free_mask] / np.maximum(dv[free_mask], 1e-30))
    b_sqrt_base = np.sqrt(ratio)

    lo_bound = np.maximum(xmin, x_free - move_limit)
    hi_bound = np.minimum(1.0, x_free + move_limit)

    def _candidate(lam: float) -> NDArray[np.float64]:
        cand = x.copy()
        cand_free = np.clip(x_free * b_sqrt_base / np.sqrt(lam), lo_bound, hi_bound)
        cand[free_mask] = cand_free
        cand[passive_solid] = 1.0
        cand[passive_void] = 0.0
        return cand

    def _volume_of(cand: NDArray[np.float64]) -> float:
        phys = filter_fn(cand)
        phys[passive_solid] = 1.0
        phys[passive_void] = 0.0
        return float(np.dot(elem_volumes, phys))

    l1, l2 = 1e-12, 1e12
    # Ensure bracket covers target volume when achievable within move limits
    while _volume_of(_candidate(l1)) < target_volume and l1 > 1e-30:
        l1 *= 1e-3
    while _volume_of(_candidate(l2)) > target_volume and l2 < 1e30:
        l2 *= 1e3

    x_new = x.copy()
    for _ in range(80):
        if (l2 - l1) / (l1 + l2) <= 1e-5:
            break
        lmid = 0.5 * (l1 + l2)
        x_new = _candidate(lmid)
        if _volume_of(x_new) > target_volume:
            l1 = lmid
        else:
            l2 = lmid

    return x_new
