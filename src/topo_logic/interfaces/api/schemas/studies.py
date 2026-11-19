"""Pydantic schemas for FEM study submissions and post-processed result summaries."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from topo_logic.domain.boundary import (
    BoundaryRegion,
    BoundingBoxSelector,
    CadFaceTagSelector,
    DesignZone,
    DesignZoneType,
    ForceLoad,
    LoadCase,
    LoadDefinition,
    PlaneSelector,
    PressureLoad,
    RegionSelector,
    SupportBC,
    SupportType,
    TriangleSetSelector,
)
from topo_logic.domain.exceptions import DomainValidationError, ResourceNotFoundError
from topo_logic.domain.geometry import ElementType
from topo_logic.domain.materials import MATERIAL_PRESETS_MM, IsotropicMaterial
from topo_logic.domain.results import (
    EquilibriumCheck,
    FemResultSummary,
    FieldStats,
    LoadCaseFemSummary,
    TopOptResultSummary,
    WeightSavingsMetrics,
)
from topo_logic.domain.study import (
    FemStudyConfig,
    FilterKind,
    OptimizerKind,
    SolverKind,
    StressConstraintConfig,
    TopOptStudyConfig,
)
from topo_logic.domain.units import UnitSystem


class TriangleSetSelectorSchema(BaseModel):
    kind: Literal["triangle_set"] = "triangle_set"
    triangle_indices: list[int] = Field(min_length=1)


class PlaneSelectorSchema(BaseModel):
    kind: Literal["plane"] = "plane"
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    tolerance: float = Field(gt=0.0)


class BoundingBoxSelectorSchema(BaseModel):
    kind: Literal["bounding_box"] = "bounding_box"
    min_corner: tuple[float, float, float]
    max_corner: tuple[float, float, float]


class CadFaceTagSelectorSchema(BaseModel):
    kind: Literal["cad_face_tag"] = "cad_face_tag"
    face_tags: list[str] = Field(min_length=1)


RegionSelectorSchema = Annotated[
    TriangleSetSelectorSchema
    | PlaneSelectorSchema
    | BoundingBoxSelectorSchema
    | CadFaceTagSelectorSchema,
    Field(discriminator="kind"),
]


class BoundaryRegionSchema(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    selector: RegionSelectorSchema

    def to_domain(self) -> BoundaryRegion:
        sel: RegionSelector
        if isinstance(self.selector, TriangleSetSelectorSchema):
            sel = TriangleSetSelector(tuple(self.selector.triangle_indices))
        elif isinstance(self.selector, PlaneSelectorSchema):
            sel = PlaneSelector(
                point=self.selector.point,
                normal=self.selector.normal,
                tolerance=self.selector.tolerance,
            )
        elif isinstance(self.selector, BoundingBoxSelectorSchema):
            sel = BoundingBoxSelector(
                min_corner=self.selector.min_corner,
                max_corner=self.selector.max_corner,
            )
        else:
            sel = CadFaceTagSelector(tuple(self.selector.face_tags))
        return BoundaryRegion(id=self.id, name=self.name, selector=sel)


class SupportBCSchema(BaseModel):
    region_id: str = Field(min_length=1)
    support_type: SupportType = SupportType.FIXED
    restrained_dofs: tuple[bool, bool, bool] = (True, True, True)
    prescribed_displacement: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def to_domain(self) -> SupportBC:
        return SupportBC(
            region_id=self.region_id,
            support_type=self.support_type,
            restrained_dofs=self.restrained_dofs,
            prescribed_displacement=self.prescribed_displacement,
        )


class ForceLoadSchema(BaseModel):
    kind: Literal["force"] = "force"
    region_id: str = Field(min_length=1)
    force_vector: tuple[float, float, float]


class PressureLoadSchema(BaseModel):
    kind: Literal["pressure"] = "pressure"
    region_id: str = Field(min_length=1)
    magnitude: float


LoadDefinitionSchema = Annotated[
    ForceLoadSchema | PressureLoadSchema,
    Field(discriminator="kind"),
]


class LoadCaseSchema(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    loads: list[LoadDefinitionSchema] = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0.0)

    def to_domain(self) -> LoadCase:
        domain_loads: list[LoadDefinition] = []
        for load in self.loads:
            if isinstance(load, ForceLoadSchema):
                domain_loads.append(
                    ForceLoad(region_id=load.region_id, force_vector=load.force_vector)
                )
            else:
                domain_loads.append(
                    PressureLoad(region_id=load.region_id, magnitude=load.magnitude)
                )
        return LoadCase(
            id=self.id,
            name=self.name,
            loads=tuple(domain_loads),
            weight=self.weight,
        )


class MaterialInputSchema(BaseModel):
    """Select an engineering preset by ID or supply custom isotropic constants."""

    preset_id: str | None = None
    name: str | None = None
    youngs_modulus: float | None = Field(default=None, gt=0.0)
    poissons_ratio: float | None = Field(default=None, ge=0.0, lt=0.5)
    yield_strength: float | None = Field(default=None, gt=0.0)
    density: float | None = Field(default=None, gt=0.0)

    def to_domain(self, unit_system: UnitSystem) -> IsotropicMaterial:
        if self.preset_id is not None:
            preset = MATERIAL_PRESETS_MM.get(self.preset_id)
            if preset is None:
                raise ResourceNotFoundError(
                    f"Material preset '{self.preset_id}' was not found.",
                    details={"preset_id": self.preset_id},
                )
            return preset.to_unit_system(unit_system)

        if (
            self.name is None
            or self.youngs_modulus is None
            or self.poissons_ratio is None
            or self.yield_strength is None
            or self.density is None
        ):
            raise DomainValidationError(
                "Custom material requires name, youngs_modulus, poissons_ratio, "
                "yield_strength, and density when preset_id is omitted."
            )
        return IsotropicMaterial(
            name=self.name,
            youngs_modulus=self.youngs_modulus,
            poissons_ratio=self.poissons_ratio,
            yield_strength=self.yield_strength,
            density=self.density,
            unit_system=unit_system,
        )


class FemStudyCreateRequest(BaseModel):
    """Request payload to submit a multi-loadcase 3D linear static FEM job."""

    geometry_id: str = Field(min_length=1)
    mesh_id: str = Field(min_length=1)
    unit_system: UnitSystem = UnitSystem.MM_N_MPA
    material: MaterialInputSchema
    regions: list[BoundaryRegionSchema] = Field(min_length=1)
    supports: list[SupportBCSchema] = Field(min_length=1)
    load_cases: list[LoadCaseSchema] = Field(min_length=1)
    element_type: ElementType = ElementType.H8
    solver_kind: SolverKind = SolverKind.AUTO

    def to_domain(self) -> FemStudyConfig:
        return FemStudyConfig(
            geometry_id=self.geometry_id,
            material=self.material.to_domain(self.unit_system),
            regions=tuple(r.to_domain() for r in self.regions),
            supports=tuple(s.to_domain() for s in self.supports),
            load_cases=tuple(lc.to_domain() for lc in self.load_cases),
            element_type=self.element_type,
            solver_kind=self.solver_kind,
        )


class EquilibriumCheckResponse(BaseModel):
    force_residual_norm: float
    applied_force_norm: float
    relative_force_error: float
    moment_residual_norm: float
    is_balanced: bool

    @classmethod
    def from_domain(cls, eq: EquilibriumCheck) -> EquilibriumCheckResponse:
        return cls(
            force_residual_norm=eq.force_residual_norm,
            applied_force_norm=eq.applied_force_norm,
            relative_force_error=eq.relative_force_error,
            moment_residual_norm=eq.moment_residual_norm,
            is_balanced=eq.is_balanced,
        )


class FieldStatsResponse(BaseModel):
    min_value: float
    max_value: float
    mean_value: float
    unit: str

    @classmethod
    def from_domain(cls, stats: FieldStats) -> FieldStatsResponse:
        return cls(
            min_value=stats.min_value,
            max_value=stats.max_value,
            mean_value=stats.mean_value,
            unit=stats.unit,
        )


class LoadCaseFemSummaryResponse(BaseModel):
    load_case_id: str
    compliance: float
    displacement_stats: FieldStatsResponse
    von_mises_stats: FieldStatsResponse
    min_safety_factor: float
    equilibrium: EquilibriumCheckResponse

    @classmethod
    def from_domain(cls, lc: LoadCaseFemSummary) -> LoadCaseFemSummaryResponse:
        return cls(
            load_case_id=lc.load_case_id,
            compliance=lc.compliance,
            displacement_stats=FieldStatsResponse.from_domain(lc.displacement_stats),
            von_mises_stats=FieldStatsResponse.from_domain(lc.von_mises_stats),
            min_safety_factor=lc.min_safety_factor,
            equilibrium=EquilibriumCheckResponse.from_domain(lc.equilibrium),
        )


class FemResultSummaryResponse(BaseModel):
    job_id: str
    load_case_results: list[LoadCaseFemSummaryResponse]

    @classmethod
    def from_domain(cls, summary: FemResultSummary) -> FemResultSummaryResponse:
        return cls(
            job_id=summary.job_id,
            load_case_results=[
                LoadCaseFemSummaryResponse.from_domain(item) for item in summary.load_case_results
            ],
        )


class DesignZoneSchema(BaseModel):
    region_id: str = Field(min_length=1)
    zone_type: DesignZoneType

    def to_domain(self) -> DesignZone:
        return DesignZone(region_id=self.region_id, zone_type=self.zone_type)


class StressConstraintSchema(BaseModel):
    enabled: bool = False
    max_von_mises: float | None = Field(default=None, gt=0.0)
    p_norm_exponent: float = Field(default=8.0, ge=2.0)
    use_adaptive_scaling: bool = True

    def to_domain(self) -> StressConstraintConfig:
        return StressConstraintConfig(
            enabled=self.enabled,
            max_von_mises=self.max_von_mises,
            p_norm_exponent=self.p_norm_exponent,
            use_adaptive_scaling=self.use_adaptive_scaling,
        )


class TopOptStudyCreateRequest(BaseModel):
    """Request payload to submit a 3D SIMP Topology Optimization job."""

    geometry_id: str = Field(min_length=1)
    mesh_id: str = Field(min_length=1)
    unit_system: UnitSystem = UnitSystem.MM_N_MPA
    material: MaterialInputSchema
    regions: list[BoundaryRegionSchema] = Field(min_length=1)
    supports: list[SupportBCSchema] = Field(min_length=1)
    load_cases: list[LoadCaseSchema] = Field(min_length=1)
    element_type: ElementType = ElementType.H8
    solver_kind: SolverKind = SolverKind.AUTO

    target_volume_fraction: float = Field(ge=0.05, le=0.95)
    penalty: float = Field(default=3.0, ge=1.0)
    e_min_ratio: float = Field(default=1e-9, gt=0.0, lt=1e-3)
    filter_kind: FilterKind = FilterKind.CONE_DENSITY
    filter_radius_ratio: float = Field(default=1.5, ge=1.5)
    optimizer_kind: OptimizerKind = OptimizerKind.OC
    move_limit: float = Field(default=0.2, gt=0.0, le=0.5)
    max_iterations: int = Field(default=80, ge=1)
    convergence_tol: float = Field(default=0.01, gt=0.0)
    use_continuation: bool = True
    stress_constraint: StressConstraintSchema = Field(default_factory=StressConstraintSchema)
    design_zones: list[DesignZoneSchema] = Field(default_factory=list)

    def to_domain(self) -> TopOptStudyConfig:
        fem_config = FemStudyConfig(
            geometry_id=self.geometry_id,
            material=self.material.to_domain(self.unit_system),
            regions=tuple(r.to_domain() for r in self.regions),
            supports=tuple(s.to_domain() for s in self.supports),
            load_cases=tuple(lc.to_domain() for lc in self.load_cases),
            element_type=self.element_type,
            solver_kind=self.solver_kind,
        )
        return TopOptStudyConfig(
            fem_config=fem_config,
            target_volume_fraction=self.target_volume_fraction,
            penalty=self.penalty,
            e_min_ratio=self.e_min_ratio,
            filter_kind=self.filter_kind,
            filter_radius_ratio=self.filter_radius_ratio,
            optimizer_kind=self.optimizer_kind,
            move_limit=self.move_limit,
            max_iterations=self.max_iterations,
            convergence_tol=self.convergence_tol,
            use_continuation=self.use_continuation,
            stress_constraint=self.stress_constraint.to_domain(),
            design_zones=tuple(z.to_domain() for z in self.design_zones),
        )


class WeightSavingsResponse(BaseModel):
    original_mass_kg: float
    optimized_mass_kg: float
    mass_saved_kg: float
    original_mass_g: float
    optimized_mass_g: float
    mass_saved_g: float
    mass_reduction_percent: float

    @classmethod
    def from_domain(cls, metrics: WeightSavingsMetrics) -> WeightSavingsResponse:
        return cls(
            original_mass_kg=metrics.original_mass_kg,
            optimized_mass_kg=metrics.optimized_mass_kg,
            mass_saved_kg=metrics.mass_saved_kg,
            original_mass_g=metrics.original_mass_g,
            optimized_mass_g=metrics.optimized_mass_g,
            mass_saved_g=metrics.mass_saved_g,
            mass_reduction_percent=metrics.mass_reduction_percent,
        )


class TopOptResultSummaryResponse(BaseModel):
    job_id: str
    iterations_completed: int
    converged: bool
    final_compliance: float
    final_volume_fraction: float
    weight_savings: WeightSavingsResponse | None = None

    @classmethod
    def from_domain(cls, summary: TopOptResultSummary) -> TopOptResultSummaryResponse:
        return cls(
            job_id=summary.job_id,
            iterations_completed=summary.iterations_completed,
            converged=summary.converged,
            final_compliance=summary.final_compliance,
            final_volume_fraction=summary.final_volume_fraction,
            weight_savings=(
                WeightSavingsResponse.from_domain(summary.weight_savings)
                if summary.weight_savings is not None
                else None
            ),
        )
