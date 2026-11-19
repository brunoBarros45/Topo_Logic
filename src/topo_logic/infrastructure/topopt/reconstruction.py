"""Watertight STL isosurface reconstruction with 1-voxel zero halo and Taubin smoothing."""

from __future__ import annotations

import io

import numpy as np
import scipy.sparse as sp
import trimesh
from numpy.typing import NDArray
from skimage import measure

from topo_logic.application.ports.simulation import ReconstructedSurface
from topo_logic.domain.exceptions import InvalidGeometryError


class WatertightStlReconstructor:
    """Implements SurfaceReconstructorPort via zero-halo Marching Cubes and Taubin smoothing."""

    def __init__(
        self,
        *,
        taubin_iterations: int = 6,
        taubin_lambda: float = 0.5,
        taubin_mu: float = -0.53,
    ) -> None:
        self._taubin_iterations = taubin_iterations
        self._taubin_lambda = taubin_lambda
        self._taubin_mu = taubin_mu

    def reconstruct_watertight_stl(
        self,
        *,
        density_payload: bytes,
        target_volume_fraction: float,
    ) -> ReconstructedSurface:
        with np.load(io.BytesIO(density_payload), allow_pickle=False) as archive:
            densities = np.asarray(archive["densities_phys"], dtype=np.float64)
            shape_arr = np.asarray(archive["voxel_shape"], dtype=np.int32)
            origin = np.asarray(archive["voxel_origin"], dtype=np.float64)
            pitch = np.asarray(archive["voxel_pitch"], dtype=np.float64)
            active_ijk = np.asarray(archive["active_voxel_ijk"], dtype=np.int32)

        nx, ny, nz = int(shape_arr[0]), int(shape_arr[1]), int(shape_arr[2])
        grid = np.zeros((nx, ny, nz), dtype=np.float64)
        grid[active_ijk[:, 0], active_ijk[:, 1], active_ijk[:, 2]] = densities

        # 1-voxel zero halo guarantees Marching Cubes closes outer domain faces cleanly
        padded = np.pad(grid, pad_width=1, mode="constant", constant_values=0.0)
        level = self._select_isosurface_level(
            densities=densities,
            padded=padded,
            target_volume_fraction=target_volume_fraction,
        )

        verts, faces, _normals, _values = measure.marching_cubes(  # type: ignore[no-untyped-call]
            padded,
            level=level,
            spacing=(float(pitch[0]), float(pitch[1]), float(pitch[2])),
        )
        if len(verts) == 0 or len(faces) == 0:
            raise InvalidGeometryError("Isosurface reconstruction produced an empty mesh.")

        # Voxel center (0,0,0) maps to index (1,1,1) in padded -> shift by origin - 0.5*pitch
        verts_world = verts + origin[None, :] - 0.5 * pitch[None, :]
        mesh = trimesh.Trimesh(vertices=verts_world, faces=faces, process=True)

        if self._taubin_iterations > 0 and len(mesh.edges_unique) > 0:
            mesh.vertices = _taubin_smooth_vertices(
                np.asarray(mesh.vertices, dtype=np.float64),
                np.asarray(mesh.edges_unique, dtype=np.int32),
                iterations=self._taubin_iterations,
                lam=self._taubin_lambda,
                mu=self._taubin_mu,
            )

        mesh.fix_normals()
        if bool(mesh.is_watertight) and float(mesh.volume) < 0.0:
            mesh.invert()

        is_watertight = bool(mesh.is_watertight)
        volume = float(mesh.volume) if is_watertight else 0.0
        exported = mesh.export(file_type="stl")
        if isinstance(exported, bytes):
            stl_bytes = exported
        elif isinstance(exported, str):
            stl_bytes = exported.encode("utf-8")
        else:
            raise InvalidGeometryError("Unexpected STL payload returned during reconstruction.")

        return ReconstructedSurface(
            stl_bytes=stl_bytes,
            volume=volume,
            is_watertight=is_watertight,
        )

    @staticmethod
    def _select_isosurface_level(
        *,
        densities: NDArray[np.float64],
        padded: NDArray[np.float64],
        target_volume_fraction: float,
    ) -> float:
        p_min = float(np.min(padded))
        p_max = float(np.max(padded))
        if p_max - p_min < 1e-8:
            raise InvalidGeometryError("Density field is uniform zero; cannot extract isosurface.")

        # Bisect threshold inside active density range to closely match target volume fraction
        lo = max(p_min + 1e-4 * (p_max - p_min), 0.05)
        hi = min(p_max - 1e-4 * (p_max - p_min), 0.95)
        if lo >= hi:
            return 0.5 * (p_min + p_max)

        # If field is crisp 0/1 around 0.5, start directly at 0.5 when close to target
        frac_half = float(np.mean(densities >= 0.5))
        if abs(frac_half - target_volume_fraction) <= 0.05 and p_min < 0.5 < p_max:
            return 0.5

        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if float(np.mean(densities >= mid)) > target_volume_fraction:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)


def _taubin_smooth_vertices(
    vertices: NDArray[np.float64],
    edges_unique: NDArray[np.int32],
    *,
    iterations: int,
    lam: float,
    mu: float,
) -> NDArray[np.float64]:
    """Volume-preserving pure-SciPy Taubin (lambda/mu) mesh smoothing."""
    n_verts = len(vertices)
    if n_verts == 0 or len(edges_unique) == 0:
        return vertices

    u = edges_unique[:, 0]
    v = edges_unique[:, 1]
    rows = np.concatenate([u, v])
    cols = np.concatenate([v, u])
    ones = np.ones(len(rows), dtype=np.float64)
    adj = sp.coo_matrix((ones, (rows, cols)), shape=(n_verts, n_verts)).tocsr()
    deg = np.maximum(np.asarray(adj.sum(axis=1), dtype=np.float64).ravel(), 1.0)

    pts = vertices.copy()
    for _ in range(iterations):
        avg_1 = (adj @ pts) / deg[:, None]
        pts = pts + lam * (avg_1 - pts)
        avg_2 = (adj @ pts) / deg[:, None]
        pts = pts + mu * (avg_2 - pts)
    return pts


def extract_binary_densities(density_payload: bytes) -> tuple[bytes, dict[str, str]]:
    """Extract packed little-endian Float32 physical element densities and shape headers."""
    with np.load(io.BytesIO(density_payload), allow_pickle=False) as archive:
        densities = np.ascontiguousarray(archive["densities_phys"], dtype="<f4")
        voxel_shape = np.asarray(archive["voxel_shape"], dtype=np.int32)

    headers = {
        "X-Topo-Dtype": "float32",
        "X-Topo-Shape": str(len(densities)),
        "X-Topo-Voxel-Shape": ",".join(str(int(v)) for v in voxel_shape),
        "X-Topo-Min": f"{float(np.min(densities)):.9g}",
        "X-Topo-Max": f"{float(np.max(densities)):.9g}",
    }
    return densities.tobytes(), headers
