"""Unit tests for binary/ASCII STL ingestion, repair, diagnostics, and scale checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures_stl import (
    make_cube_stl_bytes,
    make_inverted_cube_stl_bytes,
    make_single_triangle_hole_stl_bytes,
)
from topo_logic.application.use_cases import IngestGeometryUseCase, ProjectService
from topo_logic.domain import (
    AxisConvention,
    InvalidGeometryError,
    UnitSystem,
    UnsupportedFormatError,
)
from topo_logic.infrastructure.mesh import TrimeshStlImporter, TrimeshSurfaceRepairer
from topo_logic.infrastructure.storage import (
    LocalFsArtifactStorage,
    SqliteDatabase,
    SqliteGeometryRepository,
    SqliteProjectRepository,
)


def _build_ingest_use_case(tmp_path: Path) -> tuple[ProjectService, IngestGeometryUseCase]:
    db = SqliteDatabase(tmp_path / "test.db")
    storage = LocalFsArtifactStorage(tmp_path / "artifacts")
    project_repo = SqliteProjectRepository(db)
    geom_repo = SqliteGeometryRepository(db)
    projects = ProjectService(project_repo)
    ingest = IngestGeometryUseCase(
        project_repo=project_repo,
        geometry_repo=geom_repo,
        artifact_storage=storage,
        importer=TrimeshStlImporter(),
        repairer=TrimeshSurfaceRepairer(),
    )
    return projects, ingest


@pytest.mark.unit
def test_ingest_binary_and_ascii_stl_cubes(tmp_path: Path) -> None:
    projects, ingest = _build_ingest_use_case(tmp_path)
    proj = projects.create_project(name="Bracket Test")

    bin_asset = ingest.execute(
        project_id=proj.id,
        filename="cube_20mm.stl",
        raw_bytes=make_cube_stl_bytes(20.0, binary=True),
        unit_system=UnitSystem.MM_N_MPA,
        axis_convention=AxisConvention.Z_UP,
        auto_repair=True,
    )
    assert bin_asset.diagnostics.is_watertight is True
    assert bin_asset.diagnostics.vertex_count == 8
    assert bin_asset.diagnostics.triangle_count == 12
    assert bin_asset.diagnostics.volume == pytest.approx(8000.0, rel=1e-4)
    assert bin_asset.diagnostics.scale_guard.is_suspicious is False
    assert bin_asset.repair_report.merged_vertices_count > 0

    ascii_asset = ingest.execute(
        project_id=proj.id,
        filename="cube_ascii.STL",
        raw_bytes=make_cube_stl_bytes(20.0, binary=False),
        unit_system=UnitSystem.MM_N_MPA,
        auto_repair=True,
    )
    assert ascii_asset.diagnostics.is_watertight is True
    assert ascii_asset.diagnostics.vertex_count == 8
    assert ascii_asset.diagnostics.volume == pytest.approx(8000.0, rel=1e-4)


@pytest.mark.unit
def test_repair_inverted_normals_and_single_hole(tmp_path: Path) -> None:
    projects, ingest = _build_ingest_use_case(tmp_path)
    proj = projects.create_project(name="Repair Test")

    inverted = ingest.execute(
        project_id=proj.id,
        filename="inverted.stl",
        raw_bytes=make_inverted_cube_stl_bytes(10.0),
        auto_repair=True,
    )
    assert inverted.diagnostics.is_watertight is True
    assert inverted.diagnostics.volume == pytest.approx(1000.0, rel=1e-4)
    assert inverted.repair_report.normals_fixed is True

    hole_raw = make_single_triangle_hole_stl_bytes(10.0)
    unrepaired = ingest.execute(
        project_id=proj.id,
        filename="open.stl",
        raw_bytes=hole_raw,
        auto_repair=False,
    )
    assert unrepaired.diagnostics.is_watertight is False
    assert unrepaired.diagnostics.boundary_edge_count > 0
    assert unrepaired.repaired_artifact_key is None

    repaired = ingest.execute(
        project_id=proj.id,
        filename="closed.stl",
        raw_bytes=hole_raw,
        auto_repair=True,
    )
    assert repaired.repair_report.filled_holes is True
    assert repaired.diagnostics.is_watertight is True
    assert repaired.diagnostics.volume == pytest.approx(1000.0, rel=1e-4)


@pytest.mark.unit
def test_scale_guard_warning_and_format_errors(tmp_path: Path) -> None:
    projects, ingest = _build_ingest_use_case(tmp_path)
    proj = projects.create_project(name="Scale Test")

    suspicious = ingest.execute(
        project_id=proj.id,
        filename="big_in_meters.stl",
        raw_bytes=make_cube_stl_bytes(100.0, binary=True),
        unit_system=UnitSystem.M_N_PA,
    )
    assert suspicious.diagnostics.scale_guard.is_suspicious is True
    assert suspicious.diagnostics.scale_guard.suggested_scale_factor == 0.001
    assert any("meters" in warning for warning in suspicious.diagnostics.warnings)

    with pytest.raises(UnsupportedFormatError):
        ingest.execute(
            project_id=proj.id,
            filename="model.obj",
            raw_bytes=b"v 0 0 0\n",
        )

    with pytest.raises(InvalidGeometryError):
        ingest.execute(
            project_id=proj.id,
            filename="corrupt.stl",
            raw_bytes=b"not a valid stl",
        )
