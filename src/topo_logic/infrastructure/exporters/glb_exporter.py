"""Binary glTF 2.0 (.glb) exporters backed by trimesh (MIT)."""

from __future__ import annotations

import io

import numpy as np
import trimesh

from topo_logic.domain.exceptions import InvalidGeometryError
from topo_logic.infrastructure.mesh.volume_mesh import VolumeMeshData


def export_stl_to_glb(stl_bytes: bytes) -> bytes:
    """Convert binary or ASCII STL bytes into a binary glTF 2.0 (.glb) payload."""
    if not stl_bytes:
        raise InvalidGeometryError("Cannot convert empty STL payload to GLB.")
    try:
        mesh = trimesh.load(
            io.BytesIO(stl_bytes),
            file_type="stl",
            force="mesh",
            process=True,
        )
    except Exception as exc:
        raise InvalidGeometryError(f"Failed to parse STL for GLB conversion: {exc}") from exc

    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise InvalidGeometryError("STL did not yield a valid non-empty triangle mesh for GLB.")

    mesh.fix_normals()
    exported = mesh.export(file_type="glb")
    if not isinstance(exported, bytes):
        raise InvalidGeometryError("Expected binary GLB bytes from trimesh export.")
    return exported


def export_volume_surface_to_glb(mesh: VolumeMeshData) -> bytes:
    """Export exterior boundary surface of VolumeMeshData to binary .glb preserving vertex order."""
    if len(mesh.surface_triangles) == 0 or len(mesh.nodes) == 0:
        raise InvalidGeometryError("Volume mesh has no surface triangles to export as GLB.")

    used_nodes = np.unique(mesh.surface_triangles)
    remap = np.full(len(mesh.nodes), -1, dtype=np.int32)
    remap[used_nodes] = np.arange(len(used_nodes), dtype=np.int32)
    surface_vertices = np.asarray(mesh.nodes[used_nodes], dtype=np.float64)
    surface_faces = np.asarray(remap[mesh.surface_triangles], dtype=np.int32)

    surface_mesh = trimesh.Trimesh(vertices=surface_vertices, faces=surface_faces, process=False)
    exported = surface_mesh.export(file_type="glb")
    if not isinstance(exported, bytes):
        raise InvalidGeometryError("Expected binary GLB bytes from trimesh export.")
    return exported
