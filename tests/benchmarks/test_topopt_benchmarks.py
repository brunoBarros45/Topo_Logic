"""Engineering verification benchmarks for 3D SIMP Topology Optimization (OC & MMA)."""

from __future__ import annotations

import io

import numpy as np
import pytest
import trimesh

from topo_logic.domain import (
    MATERIAL_PRESETS_MM,
    BoundaryRegion,
    BoundingBoxSelector,
    DesignZone,
    DesignZoneType,
    ElementType,
    FemStudyConfig,
    FilterKind,
    ForceLoad,
    LoadCase,
    OptimizerKind,
    PlaneSelector,
    SolverKind,
    StressConstraintConfig,
    SupportBC,
    SupportType,
    TopOptIterationEvent,
    TopOptStudyConfig,
)
from topo_logic.infrastructure.execution import ThreadingCancellationToken
from topo_logic.infrastructure.mesh import VoxelH8Mesher
from topo_logic.infrastructure.topopt import SimpTopologyOptimizer, WatertightStlReconstructor


def _box_stl(lx: float, ly: float, lz: float) -> bytes:
    box = trimesh.creation.box(extents=(lx, ly, lz))
    box.apply_translation((0.5 * lx, 0.5 * ly, 0.5 * lz))
    exported = box.export(file_type="stl")
    return exported if isinstance(exported, bytes) else bytes(exported)


@pytest.mark.benchmark
def test_topopt_3d_cantilever_oc_convergence_and_watertight_stl() -> None:
    lx, ly, lz = 60.0, 20.0, 30.0
    _, mesh_payload = VoxelH8Mesher().generate_volume_mesh(
        _box_stl(lx, ly, lz),
        geometry_id="bench-oc",
        element_type=ElementType.H8,
        target_element_size=5.0,  # 12 x 4 x 6 = 288 elements
    )
    fem_cfg = FemStudyConfig(
        geometry_id="bench-oc",
        material=MATERIAL_PRESETS_MM["aluminum_6061_t6"],
        regions=(
            BoundaryRegion("root", "Root", PlaneSelector((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
            BoundaryRegion(
                "tip",
                "Tip Load",
                BoundingBoxSelector((lx - 0.1, 5.0, 0.0), (lx + 0.1, 15.0, 5.0)),
            ),
        ),
        supports=(SupportBC("root", SupportType.FIXED),),
        load_cases=(LoadCase("bend", "Bending", (ForceLoad("tip", (0.0, 0.0, -500.0)),)),),
        element_type=ElementType.H8,
        solver_kind=SolverKind.DIRECT,
    )
    study = TopOptStudyConfig(
        fem_config=fem_cfg,
        target_volume_fraction=0.40,
        penalty=3.0,
        filter_kind=FilterKind.CONE_DENSITY,
        filter_radius_ratio=1.5,
        optimizer_kind=OptimizerKind.OC,
        max_iterations=28,
        convergence_tol=0.01,
        use_continuation=True,
    )

    events: list[TopOptIterationEvent] = []
    summary, density_payload = SimpTopologyOptimizer().run_optimization(
        job_id="bench-topopt-oc",
        mesh_payload=mesh_payload,
        study=study,
        cancellation_token=ThreadingCancellationToken(),
        on_iteration=events.append,
    )

    assert len(events) >= 10
    assert summary.final_volume_fraction == pytest.approx(0.40, abs=0.02)
    # After continuation reaches p=3 at iteration 8, compliance must decrease smoothly
    settled_compliances = [ev.compliance for ev in events if ev.iteration >= 8]
    assert settled_compliances[-1] < settled_compliances[0]

    assert summary.weight_savings is not None
    assert summary.weight_savings.mass_reduction_percent == pytest.approx(60.0, abs=2.0)
    assert summary.weight_savings.mass_saved_g > 0.0

    reconstructed = WatertightStlReconstructor().reconstruct_watertight_stl(
        density_payload=density_payload,
        target_volume_fraction=study.target_volume_fraction,
    )
    assert reconstructed.is_watertight is True
    assert reconstructed.volume > 0.0
    parsed = trimesh.load(io.BytesIO(reconstructed.stl_bytes), file_type="stl", force="mesh")
    assert isinstance(parsed, trimesh.Trimesh)
    assert parsed.is_watertight


@pytest.mark.benchmark
def test_topopt_3d_cantilever_mma_stress_constrained_with_passive_solid() -> None:
    lx, ly, lz = 50.0, 20.0, 20.0
    _, mesh_payload = VoxelH8Mesher().generate_volume_mesh(
        _box_stl(lx, ly, lz),
        geometry_id="bench-mma",
        element_type=ElementType.H8,
        target_element_size=5.0,  # 10 x 4 x 4 = 160 elements
    )
    fem_cfg = FemStudyConfig(
        geometry_id="bench-mma",
        material=MATERIAL_PRESETS_MM["steel_aisi_1020"],
        regions=(
            BoundaryRegion("root", "Root", PlaneSelector((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
            BoundaryRegion(
                "load_pad",
                "Tip Pad",
                BoundingBoxSelector((lx - 5.1, 5.0, 0.0), (lx + 0.1, 15.0, 5.0)),
            ),
        ),
        supports=(SupportBC("root", SupportType.FIXED),),
        load_cases=(LoadCase("bend", "Tip Load", (ForceLoad("load_pad", (0.0, 0.0, -800.0)),)),),
        element_type=ElementType.H8,
        solver_kind=SolverKind.DIRECT,
    )
    study = TopOptStudyConfig(
        fem_config=fem_cfg,
        target_volume_fraction=0.45,
        penalty=3.0,
        filter_kind=FilterKind.HEAVISIDE_PROJECTION,
        filter_radius_ratio=1.5,
        optimizer_kind=OptimizerKind.MMA,
        move_limit=0.15,
        max_iterations=25,
        convergence_tol=0.01,
        use_continuation=True,
        stress_constraint=StressConstraintConfig(
            enabled=True,
            max_von_mises=60.0,
            p_norm_exponent=8.0,
            use_adaptive_scaling=True,
        ),
        design_zones=(DesignZone("load_pad", DesignZoneType.PASSIVE_SOLID),),
    )

    events: list[TopOptIterationEvent] = []
    summary, density_payload = SimpTopologyOptimizer().run_optimization(
        job_id="bench-topopt-mma",
        mesh_payload=mesh_payload,
        study=study,
        cancellation_token=ThreadingCancellationToken(),
        on_iteration=events.append,
    )

    assert len(events) >= 10
    assert all(ev.max_von_mises is not None and np.isfinite(ev.max_von_mises) for ev in events)
    assert summary.final_volume_fraction <= 0.48

    reconstructed = WatertightStlReconstructor().reconstruct_watertight_stl(
        density_payload=density_payload,
        target_volume_fraction=study.target_volume_fraction,
    )
    assert reconstructed.is_watertight is True
    assert reconstructed.volume > 0.0


@pytest.mark.benchmark
def test_topopt_multi_loadcase_symmetric_bridge() -> None:
    lx, ly, lz = 60.0, 20.0, 20.0
    _, mesh_payload = VoxelH8Mesher().generate_volume_mesh(
        _box_stl(lx, ly, lz),
        geometry_id="bench-sym",
        element_type=ElementType.H8,
        target_element_size=5.0,  # 12 x 4 x 4
    )
    fem_cfg = FemStudyConfig(
        geometry_id="bench-sym",
        material=MATERIAL_PRESETS_MM["aluminum_6061_t6"],
        regions=(
            BoundaryRegion("root", "Root", PlaneSelector((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
            BoundaryRegion("tip", "Tip", PlaneSelector((lx, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
        ),
        supports=(SupportBC("root", SupportType.FIXED),),
        load_cases=(
            LoadCase("left", "Push +Y", (ForceLoad("tip", (0.0, 500.0, 0.0)),), weight=1.0),
            LoadCase("right", "Push -Y", (ForceLoad("tip", (0.0, -500.0, 0.0)),), weight=1.0),
        ),
        element_type=ElementType.H8,
        solver_kind=SolverKind.DIRECT,
    )
    study = TopOptStudyConfig(
        fem_config=fem_cfg,
        target_volume_fraction=0.45,
        optimizer_kind=OptimizerKind.OC,
        max_iterations=22,
        use_continuation=False,
    )

    events: list[TopOptIterationEvent] = []
    summary, density_payload = SimpTopologyOptimizer().run_optimization(
        job_id="bench-sym",
        mesh_payload=mesh_payload,
        study=study,
        cancellation_token=ThreadingCancellationToken(),
        on_iteration=events.append,
    )

    assert events[-1].compliance < events[0].compliance
    assert summary.final_volume_fraction == pytest.approx(0.45, abs=0.02)

    with np.load(io.BytesIO(density_payload), allow_pickle=False) as archive:
        dens = np.asarray(archive["densities_phys"], dtype=np.float64).reshape(12, 4, 4)

    # Mirror symmetry across y-midplane (ny=4 -> slice 0 vs 3, slice 1 vs 2)
    assert np.allclose(dens, dens[:, ::-1, :], atol=1e-2)
