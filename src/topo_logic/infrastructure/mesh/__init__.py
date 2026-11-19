"""Mesh ingestion, surface repair, and volumetric meshing adapters."""

from __future__ import annotations

from topo_logic.infrastructure.mesh.gmsh_cli_mesher import (
    CompositeVolumetricMesher,
    GmshCliMesher,
    extract_tet_boundary_faces,
    extract_tet_boundary_triangles,
    parse_msh2_text,
)
from topo_logic.infrastructure.mesh.stl_importer import TrimeshStlImporter
from topo_logic.infrastructure.mesh.trimesh_repairer import TrimeshSurfaceRepairer
from topo_logic.infrastructure.mesh.volume_mesh import (
    VolumeMeshData,
    deserialize_volume_mesh,
    extract_surface_arrays,
    serialize_volume_mesh,
)
from topo_logic.infrastructure.mesh.voxel_mesher import VoxelH8Mesher

__all__ = [
    "CompositeVolumetricMesher",
    "GmshCliMesher",
    "TrimeshStlImporter",
    "TrimeshSurfaceRepairer",
    "VolumeMeshData",
    "VoxelH8Mesher",
    "deserialize_volume_mesh",
    "extract_surface_arrays",
    "extract_tet_boundary_faces",
    "extract_tet_boundary_triangles",
    "parse_msh2_text",
    "serialize_volume_mesh",
]
