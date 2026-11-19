"""Unit tests for pure-NumPy H8 voxel mesher and external Gmsh CLI adapter."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from tests.fixtures_stl import make_cube_stl_bytes, make_single_triangle_hole_stl_bytes
from topo_logic.domain import (
    DomainValidationError,
    ElementType,
    NonWatertightMeshError,
)
from topo_logic.infrastructure.mesh import (
    GmshCliMesher,
    VoxelH8Mesher,
    deserialize_volume_mesh,
    parse_msh2_text,
)


@pytest.mark.unit
def test_voxel_mesher_box_and_outward_surface_normals() -> None:
    box = trimesh.creation.box(extents=(20.0, 10.0, 10.0))
    box.apply_translation((10.0, 5.0, 5.0))
    stl_raw = box.export(file_type="stl")
    stl_bytes = stl_raw if isinstance(stl_raw, bytes) else bytes(stl_raw)

    mesher = VoxelH8Mesher()
    summary, payload = mesher.generate_volume_mesh(
        stl_bytes,
        project_id="proj-1",
        geometry_id="geom-1",
        element_type=ElementType.H8,
        target_element_size=5.0,
    )
    assert summary.element_type is ElementType.H8
    assert summary.element_count == 16  # 4 x 2 x 2
    assert summary.node_count == 45  # 5 x 3 x 3
    assert summary.total_volume == pytest.approx(2000.0)
    assert summary.min_scaled_jacobian == pytest.approx(1.0)

    mesh_data = deserialize_volume_mesh(payload)
    assert mesh_data.voxel_shape == (4, 2, 2)
    assert len(mesh_data.surface_triangles) == 2 * (2 * (4 * 2 + 4 * 2 + 2 * 2))

    # Every boundary triangle normal must point away from box center (10, 5, 5)
    center = np.array([10.0, 5.0, 5.0])
    tris = mesh_data.nodes[mesh_data.surface_triangles]
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    centroids = tris.mean(axis=1)
    dots = np.sum(normals * (centroids - center), axis=1)
    assert np.all(dots > 0.0)


@pytest.mark.unit
def test_voxel_mesher_hollow_annulus_carves_interior_cavity() -> None:
    annulus = trimesh.creation.annulus(r_min=4.0, r_max=10.0, height=10.0, sections=32)
    stl_raw = annulus.export(file_type="stl")
    stl_bytes = stl_raw if isinstance(stl_raw, bytes) else bytes(stl_raw)

    mesher = VoxelH8Mesher()
    summary, payload = mesher.generate_volume_mesh(
        stl_bytes,
        geometry_id="geom-annulus",
        element_type=ElementType.H8,
        target_element_size=1.0,
    )
    assert summary.element_count > 100
    mesh_data = deserialize_volume_mesh(payload)
    assert mesh_data.voxel_origin is not None
    assert mesh_data.voxel_pitch is not None
    assert mesh_data.active_voxel_ijk is not None

    origin = np.array(mesh_data.voxel_origin)
    pitch = np.array(mesh_data.voxel_pitch)
    centers = origin + (mesh_data.active_voxel_ijk + 0.5) * pitch
    radii = np.hypot(centers[:, 0], centers[:, 1])

    # Center hole (r < 3.5) must contain zero solid voxels; solid ring (5 <= r <= 9) must be filled
    assert not np.any(radii < 3.5)
    assert np.any((radii >= 5.0) & (radii <= 9.0))


@pytest.mark.unit
def test_voxel_mesher_rejects_open_mesh() -> None:
    mesher = VoxelH8Mesher()
    with pytest.raises(NonWatertightMeshError):
        mesher.generate_volume_mesh(
            make_single_triangle_hole_stl_bytes(10.0),
            geometry_id="geom-open",
            element_type=ElementType.H8,
            target_element_size=2.5,
        )


@pytest.mark.unit
def test_gmsh_cli_missing_binary_and_msh2_c3d10_parser() -> None:
    gmsh = GmshCliMesher(gmsh_executable="definitely_nonexistent_gmsh_binary_xyz")
    with pytest.raises(DomainValidationError, match="Gmsh CLI binary was not found"):
        gmsh.generate_volume_mesh(
            make_cube_stl_bytes(10.0),
            geometry_id="geom-1",
            element_type=ElementType.C3D10,
            target_element_size=5.0,
        )

    # Synthetic C3D10 tetrahedron in Gmsh MSH v2.2 format (node 8 is 2-3, node 9 is 1-3)
    msh2_sample = "\n".join(
        [
            "$MeshFormat",
            "2.2 0 8",
            "$EndMeshFormat",
            "$Nodes",
            "10",
            "1 0 0 0",
            "2 1 0 0",
            "3 0 1 0",
            "4 0 0 1",
            "5 0.5 0 0",
            "6 0.5 0.5 0",
            "7 0 0.5 0",
            "8 0 0 0.5",
            "9 0 0.5 0.5",
            "10 0.5 0 0.5",
            "$EndNodes",
            "$Elements",
            "1",
            "1 11 2 1 1 1 2 3 4 5 6 7 8 9 10",
            "$EndElements",
        ]
    )
    summary, payload = parse_msh2_text(
        msh2_sample,
        geometry_id="geom-tet",
        element_type=ElementType.C3D10,
    )
    assert summary.element_type is ElementType.C3D10
    assert summary.element_count == 1
    assert summary.node_count == 10
    assert summary.total_volume == pytest.approx(1.0 / 6.0)
    assert summary.min_scaled_jacobian > 0.0

    mesh_data = deserialize_volume_mesh(payload)
    # Canonical index 8 must be edge (1, 3) -> midpoint (0.5, 0, 0.5)
    assert np.allclose(mesh_data.nodes[mesh_data.elements[0, 8]], [0.5, 0.0, 0.5])
    # Canonical index 9 must be edge (2, 3) -> midpoint (0, 0.5, 0.5)
    assert np.allclose(mesh_data.nodes[mesh_data.elements[0, 9]], [0.0, 0.5, 0.5])
