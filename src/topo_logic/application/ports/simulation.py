"""Strategy ports for Phase 2/3 FEM solvers, TopOpt optimizers, and STL reconstruction."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from topo_logic.application.ports.execution import CancellationToken
from topo_logic.domain.results import (
    FemResultSummary,
    TopOptIterationEvent,
    TopOptResultSummary,
)
from topo_logic.domain.study import (
    FemStudyConfig,
    FilterKind,
    OptimizerKind,
    SolverKind,
    TopOptStudyConfig,
)


class LinearSystemSolverPort(Protocol):
    """Strategy port for solving sparse symmetric positive definite K * u = f systems."""

    def solver_kind(self) -> SolverKind:
        ...

    def solve(self, system_payload: bytes) -> bytes:
        ...


class FemSolverPort(Protocol):
    """Port for running multi-loadcase 3D linear static FEM studies."""

    def run_static_analysis(
        self,
        *,
        job_id: str,
        mesh_payload: bytes,
        study: FemStudyConfig,
        cancellation_token: CancellationToken,
    ) -> tuple[FemResultSummary, bytes]:
        """Solve all load cases and return summary metadata + packed binary Float32 fields."""
        ...


class DensityFilterPort(Protocol):
    """Strategy port for sensitivity/density filtering (Cone or Heaviside projection)."""

    def filter_kind(self) -> FilterKind:
        ...

    def apply_forward(self, raw_densities: bytes) -> bytes:
        ...

    def apply_adjoint(self, filtered_sensitivities: bytes) -> bytes:
        ...


class OptimizerPort(Protocol):
    """Strategy port for Topology Optimization updates (OC vs MMA)."""

    def optimizer_kind(self) -> OptimizerKind:
        ...

    def run_optimization(
        self,
        *,
        job_id: str,
        mesh_payload: bytes,
        study: TopOptStudyConfig,
        cancellation_token: CancellationToken,
        on_iteration: Callable[[TopOptIterationEvent], None],
    ) -> tuple[TopOptResultSummary, bytes]:
        """Run iterative optimization loop and return summary + final density field buffer."""
        ...


class SurfaceReconstructorPort(Protocol):
    """Port for converting density fields into smooth, watertight STL/OBJ meshes."""

    def reconstruct_watertight_stl(
        self,
        *,
        density_payload: bytes,
        target_volume_fraction: float,
    ) -> bytes:
        """Extract zero-halo isosurface, apply Taubin smoothing, and export binary STL."""
        ...
