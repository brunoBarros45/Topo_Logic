"""Unit tests for pure domain models, invariants, unit conversions, and job states."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from topo_logic.domain import (
    MATERIAL_PRESETS_MM,
    BoundaryRegion,
    BoundingBoxSelector,
    CadFaceTagSelector,
    DesignZone,
    DesignZoneType,
    DomainValidationError,
    FemStudyConfig,
    ForceLoad,
    InvalidJobTransitionError,
    IsotropicMaterial,
    JobRecord,
    JobStatus,
    LoadCase,
    OptimizerKind,
    PlaneSelector,
    PressureLoad,
    StressConstraintConfig,
    StudyType,
    SupportBC,
    SupportType,
    TopOptResultSummary,
    TopOptStudyConfig,
    TriangleSetSelector,
    UnitSystem,
    WeightSavingsMetrics,
    evaluate_scale_guard,
)


@pytest.mark.unit
def test_scale_guard_detects_mm_vs_meters_mismatch() -> None:
    warn_m = evaluate_scale_guard(150.0, UnitSystem.M_N_PA)
    assert warn_m.is_suspicious is True
    assert warn_m.suggested_scale_factor == 0.001
    assert warn_m.suggested_unit_system is UnitSystem.MM_N_MPA

    warn_mm = evaluate_scale_guard(0.25, UnitSystem.MM_N_MPA)
    assert warn_mm.is_suspicious is True
    assert warn_mm.suggested_scale_factor == 1000.0
    assert warn_mm.suggested_unit_system is UnitSystem.M_N_PA

    ok_mm = evaluate_scale_guard(120.0, UnitSystem.MM_N_MPA)
    assert ok_mm.is_suspicious is False
    assert ok_mm.suggested_scale_factor is None

    with pytest.raises(DomainValidationError):
        evaluate_scale_guard(0.0, UnitSystem.MM_N_MPA)


@pytest.mark.unit
def test_isotropic_material_validation_and_unit_roundtrip() -> None:
    steel = MATERIAL_PRESETS_MM["steel_aisi_1020"]
    steel_si = steel.to_unit_system(UnitSystem.M_N_PA)
    assert steel_si.unit_system is UnitSystem.M_N_PA
    assert steel_si.youngs_modulus == pytest.approx(205e9)
    assert steel_si.density == pytest.approx(7870.0)
    assert steel_si.to_unit_system(UnitSystem.MM_N_MPA).youngs_modulus == pytest.approx(
        steel.youngs_modulus
    )

    with pytest.raises(DomainValidationError):
        IsotropicMaterial(
            name="Invalid",
            youngs_modulus=1000.0,
            poissons_ratio=0.5,
            yield_strength=100.0,
            density=1e-9,
        )


@pytest.mark.unit
def test_multi_loadcase_and_stress_constrained_topopt_rules() -> None:
    steel = MATERIAL_PRESETS_MM["steel_aisi_1020"]
    regions = (
        BoundaryRegion("r-fix", "Base Clamp", PlaneSelector((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.1)),
        BoundaryRegion("r-web", "Web Face", TriangleSetSelector((0, 1, 2))),
        BoundaryRegion("r-cad", "Fusion Bore", CadFaceTagSelector(("FACE_42",))),
        BoundaryRegion("r-void", "Keep-Out", BoundingBoxSelector((1.0, 1.0, 1.0), (5.0, 5.0, 5.0))),
    )
    supports = (SupportBC("r-fix", SupportType.FIXED),)
    load_cases = (
        LoadCase("lc-1", "Bending", (ForceLoad("r-web", (0.0, 0.0, -500.0)),), weight=1.0),
        LoadCase("lc-2", "Bearing", (PressureLoad("r-cad", 12.5),), weight=0.5),
    )

    fem = FemStudyConfig(
        geometry_id="geom-1",
        material=steel,
        regions=regions,
        supports=supports,
        load_cases=load_cases,
    )

    with pytest.raises(DomainValidationError):
        TopOptStudyConfig(
            fem_config=fem,
            target_volume_fraction=0.35,
            optimizer_kind=OptimizerKind.OC,
            stress_constraint=StressConstraintConfig(enabled=True, max_von_mises=220.0),
        )

    valid_topopt = TopOptStudyConfig(
        fem_config=fem,
        target_volume_fraction=0.35,
        optimizer_kind=OptimizerKind.MMA,
        stress_constraint=StressConstraintConfig(enabled=True, max_von_mises=220.0),
        design_zones=(
            DesignZone("r-cad", DesignZoneType.PASSIVE_SOLID),
            DesignZone("r-void", DesignZoneType.PASSIVE_VOID),
        ),
    )
    assert valid_topopt.optimizer_kind is OptimizerKind.MMA
    assert len(valid_topopt.fem_config.load_cases) == 2


@pytest.mark.unit
def test_job_state_machine_enforces_legal_transitions() -> None:
    now = datetime.now(UTC)
    job = JobRecord(
        id="job-1",
        project_id="proj-1",
        study_type=StudyType.STATIC_FEM,
        status=JobStatus.QUEUED,
        progress=0.0,
        message="Queued",
        error_message=None,
        result_artifact_key=None,
        created_at=now,
        updated_at=now,
    )

    meshing = job.transition_to(JobStatus.MESHING, progress=0.2, message="Meshing")
    solving = meshing.transition_to(JobStatus.SOLVING, progress=0.6, message="Solving")
    completed = solving.transition_to(JobStatus.COMPLETED, message="Done")
    assert completed.progress == 1.0
    assert completed.is_terminal is True

    with pytest.raises(InvalidJobTransitionError):
        completed.transition_to(JobStatus.CANCELLED)

    with pytest.raises(InvalidJobTransitionError):
        job.transition_to(JobStatus.COMPLETED)


@pytest.mark.unit
def test_weight_savings_metrics_unit_consistency() -> None:
    steel_mm = MATERIAL_PRESETS_MM["steel_aisi_1020"]
    # 100 mm cube = 1e6 mm^3 -> 7.87 kg (7870 g); optimized to 30% = 3e5 mm^3 -> 2.361 kg
    metrics_mm = WeightSavingsMetrics.from_volumes_and_material(
        original_volume=1_000_000.0,
        optimized_volume=300_000.0,
        material=steel_mm,
    )
    assert metrics_mm.original_mass_kg == pytest.approx(7.87)
    assert metrics_mm.optimized_mass_kg == pytest.approx(2.361)
    assert metrics_mm.mass_saved_kg == pytest.approx(5.509)
    assert metrics_mm.original_mass_g == pytest.approx(7870.0)
    assert metrics_mm.optimized_mass_g == pytest.approx(2361.0)
    assert metrics_mm.mass_saved_g == pytest.approx(5509.0)
    assert metrics_mm.mass_reduction_percent == pytest.approx(70.0)

    steel_m = steel_mm.to_unit_system(UnitSystem.M_N_PA)
    metrics_m = WeightSavingsMetrics.from_volumes_and_material(
        original_volume=1e-3,
        optimized_volume=3e-4,
        material=steel_m,
    )
    assert metrics_m.original_mass_kg == pytest.approx(metrics_mm.original_mass_kg)
    assert metrics_m.optimized_mass_g == pytest.approx(metrics_mm.optimized_mass_g)
    assert metrics_m.mass_reduction_percent == pytest.approx(70.0)

    summary = TopOptResultSummary(
        job_id="job-topopt-1",
        iterations_completed=42,
        converged=True,
        final_compliance=12.4,
        final_volume_fraction=0.30,
        reconstructed_stl_key="projects/p1/jobs/j1/reconstructed.stl",
        density_field_key="projects/p1/jobs/j1/densities.bin",
        weight_savings=metrics_mm,
    )
    assert summary.weight_savings is not None
    assert summary.weight_savings.mass_reduction_percent == pytest.approx(70.0)

    with pytest.raises(DomainValidationError):
        WeightSavingsMetrics.from_volumes_and_material(
            original_volume=0.0,
            optimized_volume=10.0,
            material=steel_mm,
        )

    with pytest.raises(DomainValidationError):
        WeightSavingsMetrics.from_volumes_and_material(
            original_volume=100.0,
            optimized_volume=-5.0,
            material=steel_mm,
        )
