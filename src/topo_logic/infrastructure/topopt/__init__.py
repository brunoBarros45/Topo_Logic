"""3D Topology Optimization engine (SIMP, Cone/Heaviside filters, OC & MIT MMA, Taubin STL)."""

from __future__ import annotations

from topo_logic.infrastructure.topopt.filters import (
    CompositeDensityFilter,
    ConeDensityFilter,
    heaviside_derivative,
    heaviside_project,
)
from topo_logic.infrastructure.topopt.mma_optimizer import MmaOptimizer
from topo_logic.infrastructure.topopt.oc_optimizer import oc_update
from topo_logic.infrastructure.topopt.reconstruction import (
    WatertightStlReconstructor,
    extract_binary_densities,
)
from topo_logic.infrastructure.topopt.simp_engine import SimpTopologyOptimizer
from topo_logic.infrastructure.topopt.stress_aggregation import (
    StressAggregationResult,
    compute_relaxed_pnorm_stress_and_adjoint,
)

__all__ = [
    "CompositeDensityFilter",
    "ConeDensityFilter",
    "MmaOptimizer",
    "SimpTopologyOptimizer",
    "StressAggregationResult",
    "WatertightStlReconstructor",
    "compute_relaxed_pnorm_stress_and_adjoint",
    "extract_binary_densities",
    "heaviside_derivative",
    "heaviside_project",
    "oc_update",
]
