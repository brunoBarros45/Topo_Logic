"""Analytical engineering verification benchmarks for the 3D static FEM engine."""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from topo_logic.domain import (
    BoundaryRegion,
    ElementType,
    FemStudyConfig,
    ForceLoad,
    IsotropicMaterial,
    LoadCase,
    PlaneSelector,
    PressureLoad,
    SolverKind,
    SupportBC,
    SupportType,
    UnderconstrainedModelError,
    UnitSystem,
)
from topo_logic.infrastructure.execution import ThreadingCancellationToken
from topo_logic.infrastructure.fem import StaticFemSolver
from topo_logic.infrastructure.fem.postprocess import extract_binary_field
from topo_logic.infrastructure.mesh import (
    VolumeMeshData,
    VoxelH8Mesher,
    extract_tet_boundary_faces,
    serialize_volume_mesh,
)


def _box_stl(lx: float, ly: float, lz: float) -> bytes:
    box = trimesh.creation.box(extents=(lx, ly, lz))
    box.apply_translation((0.5 * lx, 0.5 * ly, 0.5 * lz))
    exported = box.export(file_type="stl")
    return exported if isinstance(exported, bytes) else bytes(exported)


def _build_c3d10_cube_mesh(size: float = 10.0) -> bytes:
    """Create a 6-tetrahedron C3D10 decomposition of [0, size]^3."""
    corners = np.array(
        [
            [0.0, 0.0, 0.0],  # 0
            [size, 0.0, 0.0],  # 1
            [size, size, 0.0],  # 2
            [0.0, size, 0.0],  # 3
            [0.0, 0.0, size],  # 4
            [size, 0.0, size],  # 5
            [size, size, size],  # 6
            [0.0, size, size],  # 7
        ],
        dtype=np.float64,
    )
    # Kuhn triangulation of the cube into 6 positively oriented tetrahedra
    raw_tets = [
        [0, 1, 2, 6],
        [0, 2, 3, 6],
        [0, 3, 7, 6],
        [0, 7, 4, 6],
        [0, 4, 5, 6],
        [0, 5, 1, 6],
    ]
    nodes_list = [row.copy() for row in corners]
    edge_to_mid: dict[tuple[int, int], int] = {}

    def _midpoint(a: int, b: int) -> int:
        key = (a, b) if a < b else (b, a)
        if key not in edge_to_mid:
            mid = 0.5 * (nodes_list[a] + nodes_list[b])
            edge_to_mid[key] = len(nodes_list)
            nodes_list.append(mid)
        return edge_to_mid[key]

    c3d10_rows: list[list[int]] = []
    for c0, c1, c2, c3 in raw_tets:
        c = corners[[c0, c1, c2, c3]]
        det = float(np.dot(c[1] - c[0], np.cross(c[2] - c[0], c[3] - c[0])))
        if det < 0.0:
            c1, c2 = c2, c1
        c3d10_rows.append(
            [
                c0,
                c1,
                c2,
                c3,
                _midpoint(c0, c1),
                _midpoint(c1, c2),
                _midpoint(c2, c0),
                _midpoint(c0, c3),
                _midpoint(c1, c3),
                _midpoint(c2, c3),
            ]
        )

    nodes = np.asarray(nodes_list, dtype=np.float64)
    elements = np.asarray(c3d10_rows, dtype=np.int32)
    surface_tris, surface_t6 = extract_tet_boundary_faces(elements)
    mesh = VolumeMeshData(
        element_type=ElementType.C3D10,
        nodes=nodes,
        elements=elements,
        surface_triangles=surface_tris,
        surface_face_nodes=surface_t6,
    )
    return serialize_volume_mesh(mesh)


@pytest.mark.benchmark
def test_patch_test_uniaxial_tension_h8() -> None:
    lx, ly, lz = 20.0, 10.0, 10.0
    youngs = 200_000.0
    nu = 0.3
    force_x = 10_000.0  # sigma_xx = 10000 / 100 = 100 MPa

    _, mesh_bytes = VoxelH8Mesher().generate_volume_mesh(
        _box_stl(lx, ly, lz),
        geometry_id="patch-h8",
        element_type=ElementType.H8,
        target_element_size=5.0,
    )
    mat = IsotropicMaterial(
        name="Benchmark Steel",
        youngs_modulus=youngs,
        poissons_ratio=nu,
        yield_strength=300.0,
        density=7.85e-9,
        unit_system=UnitSystem.MM_N_MPA,
    )
    regions = (
        BoundaryRegion("x0", "X=0 Symmetry", PlaneSelector((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
        BoundaryRegion("y0", "Y=0 Symmetry", PlaneSelector((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 1e-4)),
        BoundaryRegion("z0", "Z=0 Symmetry", PlaneSelector((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 1e-4)),
        BoundaryRegion("xL", "X=L Tension", PlaneSelector((lx, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
    )
    supports = (
        SupportBC("x0", SupportType.SYMMETRY, restrained_dofs=(True, False, False)),
        SupportBC("y0", SupportType.SYMMETRY, restrained_dofs=(False, True, False)),
        SupportBC("z0", SupportType.SYMMETRY, restrained_dofs=(False, False, True)),
    )
    load_cases = (LoadCase("tension", "Uniaxial", (ForceLoad("xL", (force_x, 0.0, 0.0)),)),)
    study = FemStudyConfig(
        geometry_id="patch-h8",
        material=mat,
        regions=regions,
        supports=supports,
        load_cases=load_cases,
        element_type=ElementType.H8,
        solver_kind=SolverKind.DIRECT,
    )

    summary, bundle = StaticFemSolver().run_static_analysis(
        job_id="bench-patch-h8",
        mesh_payload=mesh_bytes,
        study=study,
        cancellation_token=ThreadingCancellationToken(),
    )
    lc = summary.load_case_results[0]
    sigma_exact = force_x / (ly * lz)
    ux_exact = (sigma_exact / youngs) * lx
    uy_exact = -nu * (sigma_exact / youngs) * ly
    uz_exact = -nu * (sigma_exact / youngs) * lz

    raw_disp, _ = extract_binary_field(
        bundle, load_case_id="tension", field_name="displacement", unit_system=UnitSystem.MM_N_MPA
    )
    disp = np.frombuffer(raw_disp, dtype="<f4").reshape(-1, 3)

    assert float(np.max(disp[:, 0])) == pytest.approx(ux_exact, rel=1e-5)
    assert float(np.min(disp[:, 1])) == pytest.approx(uy_exact, rel=1e-5)
    assert float(np.min(disp[:, 2])) == pytest.approx(uz_exact, rel=1e-5)
    assert lc.von_mises_stats.min_value == pytest.approx(sigma_exact, rel=1e-5)
    assert lc.von_mises_stats.max_value == pytest.approx(sigma_exact, rel=1e-5)
    assert lc.min_safety_factor == pytest.approx(300.0 / sigma_exact, rel=1e-5)
    assert lc.equilibrium.is_balanced is True
    assert lc.equilibrium.relative_force_error < 1e-9


@pytest.mark.benchmark
def test_patch_test_uniaxial_tension_c3d10() -> None:
    size = 10.0
    youngs = 200_000.0
    nu = 0.3
    force_x = 10_000.0
    mesh_bytes = _build_c3d10_cube_mesh(size)

    mat = IsotropicMaterial(
        name="Benchmark Steel",
        youngs_modulus=youngs,
        poissons_ratio=nu,
        yield_strength=300.0,
        density=7.85e-9,
        unit_system=UnitSystem.MM_N_MPA,
    )
    regions = (
        BoundaryRegion("x0", "X=0", PlaneSelector((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-5)),
        BoundaryRegion("y0", "Y=0", PlaneSelector((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 1e-5)),
        BoundaryRegion("z0", "Z=0", PlaneSelector((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 1e-5)),
        BoundaryRegion("xL", "X=L", PlaneSelector((size, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-5)),
    )
    supports = (
        SupportBC("x0", SupportType.SYMMETRY, restrained_dofs=(True, False, False)),
        SupportBC("y0", SupportType.SYMMETRY, restrained_dofs=(False, True, False)),
        SupportBC("z0", SupportType.SYMMETRY, restrained_dofs=(False, False, True)),
    )
    study = FemStudyConfig(
        geometry_id="patch-c3d10",
        material=mat,
        regions=regions,
        supports=supports,
        load_cases=(
            LoadCase("tension", "Uniaxial C3D10", (ForceLoad("xL", (force_x, 0.0, 0.0)),)),
        ),
        element_type=ElementType.C3D10,
        solver_kind=SolverKind.DIRECT,
    )

    summary, bundle = StaticFemSolver().run_static_analysis(
        job_id="bench-patch-c3d10",
        mesh_payload=mesh_bytes,
        study=study,
        cancellation_token=ThreadingCancellationToken(),
    )
    lc = summary.load_case_results[0]
    sigma_exact = force_x / (size * size)
    ux_exact = (sigma_exact / youngs) * size
    uy_exact = -nu * (sigma_exact / youngs) * size

    raw_disp, _ = extract_binary_field(
        bundle, load_case_id="tension", field_name="displacement", unit_system=UnitSystem.MM_N_MPA
    )
    disp = np.frombuffer(raw_disp, dtype="<f4").reshape(-1, 3)

    assert float(np.max(disp[:, 0])) == pytest.approx(ux_exact, rel=1e-5)
    assert float(np.min(disp[:, 1])) == pytest.approx(uy_exact, rel=1e-5)
    assert lc.von_mises_stats.min_value == pytest.approx(sigma_exact, rel=1e-5)
    assert lc.von_mises_stats.max_value == pytest.approx(sigma_exact, rel=1e-5)
    assert lc.equilibrium.is_balanced is True
    assert lc.equilibrium.relative_force_error < 1e-9


@pytest.mark.benchmark
def test_cantilever_beam_deflection_h8() -> None:
    length, width, height = 100.0, 10.0, 10.0
    youngs = 200_000.0
    nu = 0.3
    tip_force = -100.0

    _, mesh_bytes = VoxelH8Mesher().generate_volume_mesh(
        _box_stl(length, width, height),
        geometry_id="cantilever-h8",
        element_type=ElementType.H8,
        target_element_size=2.5,
    )
    mat = IsotropicMaterial(
        name="Steel",
        youngs_modulus=youngs,
        poissons_ratio=nu,
        yield_strength=350.0,
        density=7.87e-9,
        unit_system=UnitSystem.MM_N_MPA,
    )
    study = FemStudyConfig(
        geometry_id="cantilever-h8",
        material=mat,
        regions=(
            BoundaryRegion("root", "Root", PlaneSelector((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
            BoundaryRegion("tip", "Tip", PlaneSelector((length, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
        ),
        supports=(SupportBC("root", SupportType.FIXED),),
        load_cases=(LoadCase("bend", "Tip Load", (ForceLoad("tip", (0.0, 0.0, tip_force)),)),),
        element_type=ElementType.H8,
        solver_kind=SolverKind.DIRECT,
    )

    summary, _ = StaticFemSolver().run_static_analysis(
        job_id="bench-cantilever",
        mesh_payload=mesh_bytes,
        study=study,
        cancellation_token=ThreadingCancellationToken(),
    )
    lc = summary.load_case_results[0]

    # Timoshenko analytical tip deflection
    inertia = (width * (height**3)) / 12.0
    area = width * height
    shear_modulus = youngs / (2.0 * (1.0 + nu))
    kappa = 5.0 / 6.0
    delta_analytical = abs(tip_force) * (length**3) / (3.0 * youngs * inertia) + (
        abs(tip_force) * length / (kappa * shear_modulus * area)
    )

    rel_err = abs(lc.displacement_stats.max_value - delta_analytical) / delta_analytical
    assert rel_err < 0.05
    assert lc.equilibrium.is_balanced is True
    assert lc.equilibrium.relative_force_error < 1e-6


@pytest.mark.benchmark
def test_multi_loadcase_direct_vs_pyamg_pcg_consistency() -> None:
    _, mesh_bytes = VoxelH8Mesher().generate_volume_mesh(
        _box_stl(60.0, 10.0, 10.0),
        geometry_id="multi-lc",
        element_type=ElementType.H8,
        target_element_size=5.0,
    )
    mat = IsotropicMaterial(
        name="Aluminum",
        youngs_modulus=68_900.0,
        poissons_ratio=0.33,
        yield_strength=276.0,
        density=2.7e-9,
        unit_system=UnitSystem.MM_N_MPA,
    )
    regions = (
        BoundaryRegion("root", "Root", PlaneSelector((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
        BoundaryRegion("tip", "Tip", PlaneSelector((60.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
        BoundaryRegion("top", "Top", PlaneSelector((0.0, 0.0, 10.0), (0.0, 0.0, 1.0), 1e-4)),
    )
    load_cases = (
        LoadCase("lc-bend", "Tip Shear", (ForceLoad("tip", (0.0, 0.0, -250.0)),), weight=1.0),
        LoadCase("lc-press", "Top Pressure", (PressureLoad("top", 2.0),), weight=0.5),
    )

    study_direct = FemStudyConfig(
        geometry_id="multi-lc",
        material=mat,
        regions=regions,
        supports=(SupportBC("root", SupportType.FIXED),),
        load_cases=load_cases,
        element_type=ElementType.H8,
        solver_kind=SolverKind.DIRECT,
    )
    study_pcg = FemStudyConfig(
        geometry_id="multi-lc",
        material=mat,
        regions=regions,
        supports=(SupportBC("root", SupportType.FIXED),),
        load_cases=load_cases,
        element_type=ElementType.H8,
        solver_kind=SolverKind.PCG_AMG,
    )

    solver = StaticFemSolver()
    res_direct, _ = solver.run_static_analysis(
        job_id="direct",
        mesh_payload=mesh_bytes,
        study=study_direct,
        cancellation_token=ThreadingCancellationToken(),
    )
    res_pcg, _ = solver.run_static_analysis(
        job_id="pcg",
        mesh_payload=mesh_bytes,
        study=study_pcg,
        cancellation_token=ThreadingCancellationToken(),
    )

    assert len(res_direct.load_case_results) == 2
    for lc_d, lc_p in zip(res_direct.load_case_results, res_pcg.load_case_results, strict=True):
        assert lc_d.compliance == pytest.approx(lc_p.compliance, rel=1e-5)
        assert lc_d.displacement_stats.max_value == pytest.approx(
            lc_p.displacement_stats.max_value, rel=1e-5
        )
        assert lc_d.von_mises_stats.max_value == pytest.approx(
            lc_p.von_mises_stats.max_value, rel=1e-5
        )
        assert lc_p.equilibrium.is_balanced is True


@pytest.mark.unit
def test_underconstrained_model_raises_error() -> None:
    _, mesh_bytes = VoxelH8Mesher().generate_volume_mesh(
        _box_stl(10.0, 10.0, 10.0),
        geometry_id="under",
        element_type=ElementType.H8,
        target_element_size=5.0,
    )
    mat = IsotropicMaterial("Steel", 200_000.0, 0.3, 350.0, 7.8e-9)
    study = FemStudyConfig(
        geometry_id="under",
        material=mat,
        regions=(
            BoundaryRegion("x0", "X=0", PlaneSelector((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
            BoundaryRegion("xL", "X=L", PlaneSelector((10.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1e-4)),
        ),
        # Only UX restrained -> missing UY and UZ rigid-body constraints
        supports=(SupportBC("x0", SupportType.DISPLACEMENT, restrained_dofs=(True, False, False)),),
        load_cases=(LoadCase("lc", "Load", (ForceLoad("xL", (100.0, 0.0, 0.0)),)),),
    )

    with pytest.raises(UnderconstrainedModelError):
        StaticFemSolver().run_static_analysis(
            job_id="fail-rigid",
            mesh_payload=mesh_bytes,
            study=study,
            cancellation_token=ThreadingCancellationToken(),
        )


# Ensure math import referenced if needed cleanly
_ = math.isclose
