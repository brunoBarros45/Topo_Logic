"""Volumetric mesh container, compressed serialization, and surface extraction helpers."""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from topo_logic.domain.exceptions import InvalidGeometryError
from topo_logic.domain.geometry import ElementType


@dataclass(frozen=True)
class VolumeMeshData:
    """In-memory volumetric finite element mesh with indexed exterior surface triangles."""

    element_type: ElementType
    nodes: NDArray[np.float64]
    elements: NDArray[np.int32]
    surface_triangles: NDArray[np.int32]
    voxel_shape: tuple[int, int, int] | None = None
    voxel_origin: tuple[float, float, float] | None = None
    voxel_pitch: tuple[float, float, float] | None = None
    active_voxel_ijk: NDArray[np.int32] | None = None
    surface_face_tags: NDArray[np.str_] | None = None
    surface_quads: NDArray[np.int32] | None = None
    surface_tri_to_quad: NDArray[np.int32] | None = None
    surface_face_nodes: NDArray[np.int32] | None = None


def serialize_volume_mesh(mesh: VolumeMeshData) -> bytes:
    """Serialize a VolumeMeshData structure into a compressed numpy archive."""
    payload: dict[str, object] = {
        "element_type": np.array(mesh.element_type.value),
        "nodes": np.asarray(mesh.nodes, dtype=np.float64),
        "elements": np.asarray(mesh.elements, dtype=np.int32),
        "surface_triangles": np.asarray(mesh.surface_triangles, dtype=np.int32),
    }
    if mesh.voxel_shape is not None:
        payload["voxel_shape"] = np.asarray(mesh.voxel_shape, dtype=np.int32)
    if mesh.voxel_origin is not None:
        payload["voxel_origin"] = np.asarray(mesh.voxel_origin, dtype=np.float64)
    if mesh.voxel_pitch is not None:
        payload["voxel_pitch"] = np.asarray(mesh.voxel_pitch, dtype=np.float64)
    if mesh.active_voxel_ijk is not None:
        payload["active_voxel_ijk"] = np.asarray(mesh.active_voxel_ijk, dtype=np.int32)
    if mesh.surface_face_tags is not None:
        payload["surface_face_tags"] = np.asarray(mesh.surface_face_tags, dtype=np.str_)
    if mesh.surface_quads is not None:
        payload["surface_quads"] = np.asarray(mesh.surface_quads, dtype=np.int32)
    if mesh.surface_tri_to_quad is not None:
        payload["surface_tri_to_quad"] = np.asarray(mesh.surface_tri_to_quad, dtype=np.int32)
    if mesh.surface_face_nodes is not None:
        payload["surface_face_nodes"] = np.asarray(mesh.surface_face_nodes, dtype=np.int32)

    buf = io.BytesIO()
    np.savez_compressed(buf, **payload)  # type: ignore[arg-type]
    return buf.getvalue()


def deserialize_volume_mesh(raw_bytes: bytes) -> VolumeMeshData:
    """Load a VolumeMeshData instance from a compressed numpy archive."""
    try:
        with np.load(io.BytesIO(raw_bytes), allow_pickle=False) as archive:
            element_type = ElementType(str(archive["element_type"].item()))
            nodes = np.asarray(archive["nodes"], dtype=np.float64)
            elements = np.asarray(archive["elements"], dtype=np.int32)
            surface_triangles = np.asarray(archive["surface_triangles"], dtype=np.int32)

            voxel_shape_arr = archive.get("voxel_shape")
            voxel_origin_arr = archive.get("voxel_origin")
            voxel_pitch_arr = archive.get("voxel_pitch")
            active_ijk = (
                np.asarray(archive["active_voxel_ijk"], dtype=np.int32)
                if "active_voxel_ijk" in archive
                else None
            )
            face_tags = (
                np.asarray(archive["surface_face_tags"], dtype=np.str_)
                if "surface_face_tags" in archive
                else None
            )
            surface_quads = (
                np.asarray(archive["surface_quads"], dtype=np.int32)
                if "surface_quads" in archive
                else None
            )
            surface_tri_to_quad = (
                np.asarray(archive["surface_tri_to_quad"], dtype=np.int32)
                if "surface_tri_to_quad" in archive
                else None
            )
            surface_face_nodes = (
                np.asarray(archive["surface_face_nodes"], dtype=np.int32)
                if "surface_face_nodes" in archive
                else None
            )
    except Exception as exc:
        raise InvalidGeometryError(f"Failed to deserialize volume mesh payload: {exc}") from exc

    voxel_shape = (
        (int(voxel_shape_arr[0]), int(voxel_shape_arr[1]), int(voxel_shape_arr[2]))
        if voxel_shape_arr is not None
        else None
    )
    voxel_origin = (
        (float(voxel_origin_arr[0]), float(voxel_origin_arr[1]), float(voxel_origin_arr[2]))
        if voxel_origin_arr is not None
        else None
    )
    voxel_pitch = (
        (float(voxel_pitch_arr[0]), float(voxel_pitch_arr[1]), float(voxel_pitch_arr[2]))
        if voxel_pitch_arr is not None
        else None
    )

    return VolumeMeshData(
        element_type=element_type,
        nodes=nodes,
        elements=elements,
        surface_triangles=surface_triangles,
        voxel_shape=voxel_shape,
        voxel_origin=voxel_origin,
        voxel_pitch=voxel_pitch,
        active_voxel_ijk=active_ijk,
        surface_face_tags=face_tags,
        surface_quads=surface_quads,
        surface_tri_to_quad=surface_tri_to_quad,
        surface_face_nodes=surface_face_nodes,
    )


def extract_surface_arrays(
    mesh: VolumeMeshData,
) -> tuple[NDArray[np.float32], NDArray[np.int32]]:
    """Extract float32 nodes and surface triangle indices for viewport picking."""
    return (
        np.asarray(mesh.nodes, dtype=np.float32),
        np.asarray(mesh.surface_triangles, dtype=np.int32),
    )
