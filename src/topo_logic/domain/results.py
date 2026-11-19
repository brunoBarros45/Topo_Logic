"""Result summary value objects for FEM post-processing and TopOpt iteration streaming."""

from __future__ import annotations

import math
from dataclasses import dataclass

from topo_logic.domain.exceptions import DomainValidationError
from topo_logic.domain.materials import IsotropicMaterial
from topo_logic.domain.units import UnitSystem


@dataclass(frozen=True)
class EquilibriumCheck:
    """Global static equilibrium balance check between applied loads and reactions."""

    force_residual_norm: float
    applied_force_norm: float
    relative_force_error: float
    moment_residual_norm: float
    is_balanced: bool


@dataclass(frozen=True)
class FieldStats:
    """Scalar field range summary in explicit physical units."""

    min_value: float
    max_value: float
    mean_value: float
    unit: str


@dataclass(frozen=True)
class LoadCaseFemSummary:
    """Post-processed FEM summary for a single load case."""

    load_case_id: str
    compliance: float
    displacement_stats: FieldStats
    von_mises_stats: FieldStats
    min_safety_factor: float
    equilibrium: EquilibriumCheck


@dataclass(frozen=True)
class FemResultSummary:
    """Complete FEM study output summary referencing binary Float32 field artifacts."""

    job_id: str
    load_case_results: tuple[LoadCaseFemSummary, ...]
    fields_artifact_key: str
    mesh_id: str | None = None


@dataclass(frozen=True)
class TopOptIterationEvent:
    """Lightweight per-iteration progress update streamed during optimization."""

    job_id: str
    iteration: int
    compliance: float
    volume_fraction: float
    max_density_change: float
    max_von_mises: float | None = None
    preview_artifact_key: str | None = None
    strain_energy: float | None = None
    remaining_mass_kg: float | None = None


@dataclass(frozen=True)
class WeightSavingsMetrics:
    """Mass comparison and percentage reduction between original and optimized designs."""

    original_mass_kg: float
    optimized_mass_kg: float
    mass_saved_kg: float
    original_mass_g: float
    optimized_mass_g: float
    mass_saved_g: float
    mass_reduction_percent: float

    def __post_init__(self) -> None:
        values = (
            self.original_mass_kg,
            self.optimized_mass_kg,
            self.mass_saved_kg,
            self.original_mass_g,
            self.optimized_mass_g,
            self.mass_saved_g,
            self.mass_reduction_percent,
        )
        if not all(math.isfinite(val) for val in values):
            raise DomainValidationError("Weight savings metrics must all be finite.")
        if self.original_mass_kg <= 0.0 or self.original_mass_g <= 0.0:
            raise DomainValidationError(
                "Original mass must be strictly positive.",
                details={"original_mass_kg": self.original_mass_kg},
            )
        if self.optimized_mass_kg < 0.0 or self.optimized_mass_g < 0.0:
            raise DomainValidationError(
                "Optimized mass must be non-negative.",
                details={"optimized_mass_kg": self.optimized_mass_kg},
            )

    @classmethod
    def from_volumes_and_material(
        cls,
        *,
        original_volume: float,
        optimized_volume: float,
        material: IsotropicMaterial,
    ) -> WeightSavingsMetrics:
        """Compute unit-consistent original, optimized, and saved mass in kg, g, and %."""
        if not math.isfinite(original_volume) or original_volume <= 0.0:
            raise DomainValidationError(
                "Original volume must be finite and strictly positive.",
                details={"original_volume": original_volume},
            )
        if not math.isfinite(optimized_volume) or optimized_volume < 0.0:
            raise DomainValidationError(
                "Optimized volume must be finite and non-negative.",
                details={"optimized_volume": optimized_volume},
            )

        kg_factor = 1000.0 if material.unit_system is UnitSystem.MM_N_MPA else 1.0
        original_mass_kg = original_volume * material.density * kg_factor
        optimized_mass_kg = optimized_volume * material.density * kg_factor
        mass_saved_kg = original_mass_kg - optimized_mass_kg

        original_mass_g = original_mass_kg * 1000.0
        optimized_mass_g = optimized_mass_kg * 1000.0
        mass_saved_g = mass_saved_kg * 1000.0
        mass_reduction_percent = (mass_saved_kg / original_mass_kg) * 100.0

        return cls(
            original_mass_kg=original_mass_kg,
            optimized_mass_kg=optimized_mass_kg,
            mass_saved_kg=mass_saved_kg,
            original_mass_g=original_mass_g,
            optimized_mass_g=optimized_mass_g,
            mass_saved_g=mass_saved_g,
            mass_reduction_percent=mass_reduction_percent,
        )


@dataclass(frozen=True)
class TopOptResultSummary:
    """Final topology optimization outcome and reconstructed geometry artifact keys."""

    job_id: str
    iterations_completed: int
    converged: bool
    final_compliance: float
    final_volume_fraction: float
    reconstructed_stl_key: str
    density_field_key: str
    weight_savings: WeightSavingsMetrics | None = None
    mesh_id: str | None = None
    history_artifact_key: str | None = None
