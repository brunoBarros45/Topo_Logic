"""3D linear static FEM engine infrastructure package."""

from __future__ import annotations

from topo_logic.infrastructure.fem.postprocess import extract_binary_field
from topo_logic.infrastructure.fem.static_fem_solver import StaticFemSolver

__all__ = [
    "StaticFemSolver",
    "extract_binary_field",
]
