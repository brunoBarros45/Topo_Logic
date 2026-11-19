"""FEM and Topology Optimization study configurations and engineering invariants."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from topo_logic.domain.boundary import BoundaryRegion, DesignZone, LoadCase, SupportBC
from topo_logic.domain.exceptions import DomainValidationError
from topo_logic.domain.geometry import ElementType
from topo_logic.domain.materials import IsotropicMaterial


class StudyType(StrEnum):
    """Simulation study categories."""

    STATIC_FEM = "static_fem"
    TOPOLOGY_OPTIMIZATION = "topology_optimization"


class SolverKind(StrEnum):
    """Linear elasticity solver selection strategy."""

    AUTO = "auto"
    DIRECT = "direct"
    PCG_AMG = "pcg_amg"


class OptimizerKind(StrEnum):
    """Topology optimization update algorithm."""

    OC = "oc"
    MMA = "mma"


class FilterKind(StrEnum):
    """Density/sensitivity filtering strategy to avoid checkerboarding."""

    CONE_DENSITY = "cone_density"
    HEAVISIDE_PROJECTION = "heaviside_projection"


@dataclass(frozen=True)
class StressConstraintConfig:
    """Optional P-norm aggregated Von Mises stress constraint configuration."""

    enabled: bool = False
    max_von_mises: float | None = None
    p_norm_exponent: float = 8.0
    use_adaptive_scaling: bool = True

    def __post_init__(self) -> None:
        if not self.enabled:
            return
        if (
            self.max_von_mises is None
            or not math.isfinite(self.max_von_mises)
            or self.max_von_mises <= 0.0
        ):
            raise DomainValidationError(
                "StressConstraintConfig requires a finite positive max_von_mises when enabled."
            )
        if not math.isfinite(self.p_norm_exponent) or self.p_norm_exponent < 2.0:
            raise DomainValidationError(
                "StressConstraintConfig p_norm_exponent must be >= 2.0 when enabled."
            )


@dataclass(frozen=True)
class FemStudyConfig:
    """Complete specification for a multi-loadcase 3D linear static FEM study."""

    geometry_id: str
    material: IsotropicMaterial
    regions: tuple[BoundaryRegion, ...]
    supports: tuple[SupportBC, ...]
    load_cases: tuple[LoadCase, ...]
    element_type: ElementType = ElementType.H8
    solver_kind: SolverKind = SolverKind.AUTO

    def __post_init__(self) -> None:
        if not self.geometry_id.strip():
            raise DomainValidationError("FemStudyConfig geometry_id must not be empty.")
        if not self.supports:
            raise DomainValidationError("FemStudyConfig requires at least one SupportBC.")
        if not self.load_cases:
            raise DomainValidationError("FemStudyConfig requires at least one LoadCase.")

        region_ids = [region.id for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise DomainValidationError("BoundaryRegion IDs within a study must be unique.")
        known_regions = set(region_ids)

        for support in self.supports:
            if support.region_id not in known_regions:
                raise DomainValidationError(
                    f"SupportBC references unknown region_id '{support.region_id}'."
                )

        load_case_ids = [lc.id for lc in self.load_cases]
        if len(load_case_ids) != len(set(load_case_ids)):
            raise DomainValidationError("LoadCase IDs within a study must be unique.")

        for load_case in self.load_cases:
            for load in load_case.loads:
                if load.region_id not in known_regions:
                    raise DomainValidationError(
                        f"Load '{load_case.id}' references unknown region_id '{load.region_id}'."
                    )


@dataclass(frozen=True)
class TopOptStudyConfig:
    """Complete specification for a 3D SIMP Topology Optimization study."""

    fem_config: FemStudyConfig
    target_volume_fraction: float
    penalty: float = 3.0
    e_min_ratio: float = 1e-9
    filter_kind: FilterKind = FilterKind.CONE_DENSITY
    filter_radius_ratio: float = 1.5
    optimizer_kind: OptimizerKind = OptimizerKind.OC
    move_limit: float = 0.2
    max_iterations: int = 80
    convergence_tol: float = 0.01
    use_continuation: bool = True
    stress_constraint: StressConstraintConfig = StressConstraintConfig()
    design_zones: tuple[DesignZone, ...] = ()

    def __post_init__(self) -> None:
        if not (0.05 <= self.target_volume_fraction <= 0.95):
            raise DomainValidationError(
                "target_volume_fraction must be within [0.05, 0.95].",
                details={"target_volume_fraction": self.target_volume_fraction},
            )
        if not math.isfinite(self.penalty) or self.penalty < 1.0:
            raise DomainValidationError("SIMP penalty must be >= 1.0.")
        if not math.isfinite(self.e_min_ratio) or not (0.0 < self.e_min_ratio < 1e-3):
            raise DomainValidationError("e_min_ratio must satisfy 0 < e_min_ratio < 1e-3.")
        if not math.isfinite(self.filter_radius_ratio) or self.filter_radius_ratio < 1.5:
            raise DomainValidationError(
                "filter_radius_ratio must be >= 1.5 to prevent checkerboarding."
            )
        if not math.isfinite(self.move_limit) or not (0.0 < self.move_limit <= 0.5):
            raise DomainValidationError("move_limit must satisfy 0 < move_limit <= 0.5.")
        if self.max_iterations < 1:
            raise DomainValidationError("max_iterations must be >= 1.")
        if not math.isfinite(self.convergence_tol) or self.convergence_tol <= 0.0:
            raise DomainValidationError("convergence_tol must be strictly positive.")

        if self.stress_constraint.enabled and self.optimizer_kind is OptimizerKind.OC:
            raise DomainValidationError(
                "Stress-constrained topology optimization requires OptimizerKind.MMA "
                "(Optimality Criteria only supports a single volume constraint)."
            )

        known_regions = {region.id for region in self.fem_config.regions}
        for zone in self.design_zones:
            if zone.region_id not in known_regions:
                raise DomainValidationError(
                    f"DesignZone references unknown region_id '{zone.region_id}'."
                )
