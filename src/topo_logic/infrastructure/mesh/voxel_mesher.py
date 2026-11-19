"""100% MIT structured hexahedral (H8) voxel mesher for watertight STL models."""

from __future__ import annotations

import io
import uuid

import numpy as np
import trimesh
from numpy.typing import NDArray

from topo_logic.domain.exceptions import (
    DomainValidationError,
    InvalidGeometryError,
    NonWatertightMeshError,
)
from topo_logic.domain.geometry import ElementType, VolumeMeshSummary
from topo_logic.infrastructure.mesh.volume_mesh import VolumeMeshData, serialize_volume_mesh


class VoxelH8Mesher:
    """Generates structured 8-node hexahedral (H8) meshes without external GPL dependencies."""

    _SUPPORTED: frozenset[ElementType] = frozenset({ElementType.H8})
    _MAX_GRID_VOXELS: int = 250_000

    def supported_elements(self) -> frozenset[ElementType]:
        return self._SUPPORTED

    def generate_volume_mesh(
        self,
        surface_stl_bytes: bytes,
        *,
        project_id: str = "",
        geometry_id: str,
        element_type: ElementType,
        target_element_size: float,
    ) -> tuple[VolumeMeshSummary, bytes]:
        if element_type is not ElementType.H8:
            raise DomainValidationError(
                f"VoxelH8Mesher only supports H8 elements, got '{element_type.value}'."
            )
        if target_element_size <= 0.0:
            raise DomainValidationError("target_element_size must be strictly positive.")

        surface = self._load_watertight_surface(surface_stl_bytes)
        bounds = np.asarray(surface.bounds, dtype=np.float64)
        min_corner = bounds[0]
        max_corner = bounds[1]
        extents = max_corner - min_corner
        if np.any(extents <= 0.0):
            raise InvalidGeometryError(
                "Surface mesh has zero thickness along at least one coordinate axis."
            )

        nx = max(1, round(float(extents[0]) / target_element_size))
        ny = max(1, round(float(extents[1]) / target_element_size))
        nz = max(1, round(float(extents[2]) / target_element_size))

        total_cells = nx * ny * nz
        if total_cells > self._MAX_GRID_VOXELS:
            raise DomainValidationError(
                f"Requested target_element_size={target_element_size} produces {total_cells} "
                f"grid cells, exceeding the limit of {self._MAX_GRID_VOXELS}.",
                details={"nx": nx, "ny": ny, "nz": nz, "max_cells": self._MAX_GRID_VOXELS},
            )

        hx = float(extents[0]) / nx
        hy = float(extents[1]) / ny
        hz = float(extents[2]) / nz

        occupied = self._voxelize_interior(
            surface=surface,
            min_corner=min_corner,
            extents=extents,
            nx=nx,
            ny=ny,
            nz=nz,
            hx=hx,
            hy=hy,
            hz=hz,
        )
        if not np.any(occupied):
            raise InvalidGeometryError(
                "Voxelization produced zero solid elements. Decrease target_element_size."
            )

        active_ijk = np.argwhere(occupied).astype(np.int32)
        nodes, elements, surface_triangles, surface_quads, surface_tri_to_quad = (
            self._build_hex_mesh(
                occupied=occupied,
                active_ijk=active_ijk,
                min_corner=min_corner,
                nx=nx,
                ny=ny,
                nz=nz,
                hx=hx,
                hy=hy,
                hz=hz,
            )
        )

        mesh_data = VolumeMeshData(
            element_type=ElementType.H8,
            nodes=nodes,
            elements=elements,
            surface_triangles=surface_triangles,
            voxel_shape=(nx, ny, nz),
            voxel_origin=(float(min_corner[0]), float(min_corner[1]), float(min_corner[2])),
            voxel_pitch=(hx, hy, hz),
            active_voxel_ijk=active_ijk,
            surface_quads=surface_quads,
            surface_tri_to_quad=surface_tri_to_quad,
        )
        total_volume = float(len(elements)) * hx * hy * hz
        summary = VolumeMeshSummary(
            id=str(uuid.uuid4()),
            geometry_id=geometry_id,
            element_type=ElementType.H8,
            node_count=len(nodes),
            element_count=len(elements),
            total_volume=total_volume,
            min_scaled_jacobian=1.0,
            project_id=project_id,
            surface_triangle_count=len(surface_triangles),
        )
        return summary, serialize_volume_mesh(mesh_data)

    @staticmethod
    def _load_watertight_surface(surface_stl_bytes: bytes) -> trimesh.Trimesh:
        try:
            loaded = trimesh.load(
                io.BytesIO(surface_stl_bytes),
                file_type="stl",
                force="mesh",
                process=True,
            )
        except Exception as exc:
            raise InvalidGeometryError(f"Failed to parse STL for meshing: {exc}") from exc

        if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
            raise InvalidGeometryError("STL payload contains no valid triangles.")
        if not bool(loaded.is_watertight):
            raise NonWatertightMeshError("Volumetric H8 meshing requires a watertight surface STL.")
        return loaded

    @staticmethod
    def _voxelize_interior(
        *,
        surface: trimesh.Trimesh,
        min_corner: NDArray[np.float64],
        extents: NDArray[np.float64],
        nx: int,
        ny: int,
        nz: int,
        hx: float,
        hy: float,
        hz: float,
    ) -> NDArray[np.bool_]:
        bbox_volume = float(extents[0] * extents[1] * extents[2])
        if abs(float(surface.volume) - bbox_volume) <= 1e-4 * bbox_volume:
            return np.ones((nx, ny, nz), dtype=bool)

        cx = min_corner[0] + (np.arange(nx, dtype=np.float64) + 0.5) * hx
        cy = min_corner[1] + (np.arange(ny, dtype=np.float64) + 0.5) * hy
        cz = min_corner[2] + (np.arange(nz, dtype=np.float64) + 0.5) * hz

        # Tiny asymmetric jitter prevents rays grazing axis-aligned triangle edges/vertices.
        ray_x = cx + 1.1317e-6 * hx
        ray_y = cy + 2.7183e-6 * hy

        parity_diff = np.zeros((nx, ny, nz + 1), dtype=np.int32)
        triangles = np.asarray(surface.triangles, dtype=np.float64)

        for tri in triangles:
            x0, y0, z0 = float(tri[0, 0]), float(tri[0, 1]), float(tri[0, 2])
            x1, y1, z1 = float(tri[1, 0]), float(tri[1, 1]), float(tri[1, 2])
            x2, y2, z2 = float(tri[2, 0]), float(tri[2, 1]), float(tri[2, 2])

            e1x, e1y = x1 - x0, y1 - y0
            e2x, e2y = x2 - x0, y2 - y0
            det = e1x * e2y - e2x * e1y
            if abs(det) <= 1e-18:
                continue

            ix0 = int(np.searchsorted(ray_x, min(x0, x1, x2), side="left"))
            ix1 = int(np.searchsorted(ray_x, max(x0, x1, x2), side="right"))
            iy0 = int(np.searchsorted(ray_y, min(y0, y1, y2), side="left"))
            iy1 = int(np.searchsorted(ray_y, max(y0, y1, y2), side="right"))
            if ix0 >= ix1 or iy0 >= iy1:
                continue

            gx, gy = np.meshgrid(ray_x[ix0:ix1], ray_y[iy0:iy1], indexing="ij")
            dx = gx - x0
            dy = gy - y0
            w1 = (dx * e2y - dy * e2x) / det
            w2 = (e1x * dy - e1y * dx) / det
            w0 = 1.0 - w1 - w2

            inside = (w0 >= 0.0) & (w1 >= 0.0) & (w2 >= 0.0)
            if not np.any(inside):
                continue

            local_i, local_j = np.nonzero(inside)
            z_hit = (
                w0[local_i, local_j] * z0 + w1[local_i, local_j] * z1 + w2[local_i, local_j] * z2
            )
            kz = np.searchsorted(cz, z_hit, side="right")
            np.add.at(parity_diff, (ix0 + local_i, iy0 + local_j, kz), 1)

        crossings_below = np.cumsum(parity_diff[:, :, :-1], axis=2)
        return np.asarray((crossings_below % 2) == 1, dtype=bool)

    @staticmethod
    def _build_hex_mesh(
        *,
        occupied: NDArray[np.bool_],
        active_ijk: NDArray[np.int32],
        min_corner: NDArray[np.float64],
        nx: int,
        ny: int,
        nz: int,
        hx: float,
        hy: float,
        hz: float,
    ) -> tuple[
        NDArray[np.float64],
        NDArray[np.int32],
        NDArray[np.int32],
        NDArray[np.int32],
        NDArray[np.int32],
    ]:
        ii = active_ijk[:, 0]
        jj = active_ijk[:, 1]
        kk = active_ijk[:, 2]

        # Canonical H8 corner offsets:
        # 0:(0,0,0), 1:(1,0,0), 2:(1,1,0), 3:(0,1,0),
        # 4:(0,0,1), 5:(1,0,1), 6:(1,1,1), 7:(0,1,1)
        corner_offsets = np.array(
            [
                [0, 0, 0],
                [1, 0, 0],
                [1, 1, 0],
                [0, 1, 0],
                [0, 0, 1],
                [1, 0, 1],
                [1, 1, 1],
                [0, 1, 1],
            ],
            dtype=np.int32,
        )

        # (N_elem, 8, 3) grid corner coordinates -> flat grid node IDs -> compacted node IDs
        elem_corner_ijk = active_ijk[:, None, :] + corner_offsets[None, :, :]
        stride_i = (ny + 1) * (nz + 1)
        stride_j = nz + 1
        raw_node_ids = (
            elem_corner_ijk[:, :, 0] * stride_i
            + elem_corner_ijk[:, :, 1] * stride_j
            + elem_corner_ijk[:, :, 2]
        )
        unique_raw_ids, inverse = np.unique(raw_node_ids.ravel(), return_inverse=True)
        elements = inverse.reshape(-1, 8).astype(np.int32)

        node_i = unique_raw_ids // stride_i
        rem = unique_raw_ids % stride_i
        node_j = rem // stride_j
        node_k = rem % stride_j

        nodes = np.column_stack(
            [
                min_corner[0] + node_i * hx,
                min_corner[1] + node_j * hy,
                min_corner[2] + node_k * hz,
            ]
        ).astype(np.float64)

        # Extract outward-oriented boundary quads and triangles for all exposed voxel faces
        quad_chunks: list[NDArray[np.int32]] = []
        tri_chunks: list[NDArray[np.int32]] = []

        def _append_face(mask: NDArray[np.bool_], c0: int, c1: int, c2: int, c3: int) -> None:
            if not np.any(mask):
                return
            sub = elements[mask]
            quads = sub[:, [c0, c1, c2, c3]]
            t1 = sub[:, [c0, c1, c2]]
            t2 = sub[:, [c0, c2, c3]]
            quad_chunks.append(quads)
            tri_chunks.append(np.hstack([t1, t2]).reshape(-1, 3))

        neg_z = np.ones(len(elements), dtype=bool)
        has_nz = kk > 0
        neg_z[has_nz] = ~occupied[ii[has_nz], jj[has_nz], kk[has_nz] - 1]
        _append_face(neg_z, 0, 3, 2, 1)

        pos_z = np.ones(len(elements), dtype=bool)
        has_pz = kk < (nz - 1)
        pos_z[has_pz] = ~occupied[ii[has_pz], jj[has_pz], kk[has_pz] + 1]
        _append_face(pos_z, 4, 5, 6, 7)

        neg_y = np.ones(len(elements), dtype=bool)
        has_ny = jj > 0
        neg_y[has_ny] = ~occupied[ii[has_ny], jj[has_ny] - 1, kk[has_ny]]
        _append_face(neg_y, 0, 1, 5, 4)

        pos_y = np.ones(len(elements), dtype=bool)
        has_py = jj < (ny - 1)
        pos_y[has_py] = ~occupied[ii[has_py], jj[has_py] + 1, kk[has_py]]
        _append_face(pos_y, 3, 7, 6, 2)

        neg_x = np.ones(len(elements), dtype=bool)
        has_nx = ii > 0
        neg_x[has_nx] = ~occupied[ii[has_nx] - 1, jj[has_nx], kk[has_nx]]
        _append_face(neg_x, 0, 4, 7, 3)

        pos_x = np.ones(len(elements), dtype=bool)
        has_px = ii < (nx - 1)
        pos_x[has_px] = ~occupied[ii[has_px] + 1, jj[has_px], kk[has_px]]
        _append_face(pos_x, 1, 2, 6, 5)

        surface_quads = (
            np.vstack(quad_chunks).astype(np.int32)
            if quad_chunks
            else np.empty((0, 4), dtype=np.int32)
        )
        surface_triangles = (
            np.vstack(tri_chunks).astype(np.int32)
            if tri_chunks
            else np.empty((0, 3), dtype=np.int32)
        )
        surface_tri_to_quad = (np.arange(len(surface_triangles), dtype=np.int32) // 2).astype(
            np.int32
        )
        return nodes, elements, surface_triangles, surface_quads, surface_tri_to_quad
