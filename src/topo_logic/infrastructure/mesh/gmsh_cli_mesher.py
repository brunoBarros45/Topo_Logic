"""Optional external Gmsh CLI subprocess adapter (C3D4 / C3D10) preserving MIT core."""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from topo_logic.application.ports.geometry import VolumetricMesherPort
from topo_logic.domain.exceptions import DomainValidationError, InvalidGeometryError
from topo_logic.domain.geometry import ElementType, VolumeMeshSummary
from topo_logic.infrastructure.mesh.volume_mesh import VolumeMeshData, serialize_volume_mesh


class GmshCliMesher:
    """Invokes an external Gmsh binary via subprocess (never links GPL libgmsh)."""

    _SUPPORTED: frozenset[ElementType] = frozenset({ElementType.C3D4, ElementType.C3D10})

    def __init__(self, gmsh_executable: str = "gmsh") -> None:
        self._executable = gmsh_executable

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
        if element_type not in self._SUPPORTED:
            raise DomainValidationError(
                f"GmshCliMesher supports C3D4/C3D10, got '{element_type.value}'."
            )
        if target_element_size <= 0.0:
            raise DomainValidationError("target_element_size must be strictly positive.")

        exe_path = shutil.which(self._executable)
        if exe_path is None:
            raise DomainValidationError(
                "Gmsh CLI binary was not found on PATH. Install Gmsh CLI for unstructured "
                "C3D4/C3D10 meshing, or use ElementType.H8 (built-in MIT voxel mesher).",
                details={"executable": self._executable},
            )

        order = 2 if element_type is ElementType.C3D10 else 1
        with tempfile.TemporaryDirectory(prefix="topologic_gmsh_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            stl_path = tmp_dir / "surface.stl"
            geo_path = tmp_dir / "mesh.geo"
            msh_path = tmp_dir / "volume.msh"

            stl_path.write_bytes(surface_stl_bytes)
            angle_rad = math.radians(40.0)
            curve_rad = math.radians(180.0)
            geo_script = "\n".join(
                [
                    f'Merge "{stl_path.as_posix()}";',
                    f"ClassifySurfaces{{{angle_rad:.6f}, 1, 1, {curve_rad:.6f}}};",
                    "CreateGeometry;",
                    "Surface Loop(1) = Surface{:};",
                    "Volume(1) = {1};",
                    f"Mesh.CharacteristicLengthMin = {0.5 * target_element_size:.6g};",
                    f"Mesh.CharacteristicLengthMax = {target_element_size:.6g};",
                    f"Mesh.ElementOrder = {order};",
                    "Mesh.Optimize = 1;",
                    "Mesh.OptimizeNetgen = 1;",
                    "Mesh.MshFileVersion = 2.2;",
                ]
            )
            geo_path.write_text(geo_script, encoding="utf-8")

            proc = subprocess.run(
                [exe_path, str(geo_path), "-3", "-format", "msh2", "-o", str(msh_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0 or not msh_path.is_file():
                raise InvalidGeometryError(
                    f"Gmsh CLI meshing failed (exit {proc.returncode}): {proc.stderr.strip()}"
                )

            msh_text = msh_path.read_text(encoding="utf-8", errors="replace")

        return parse_msh2_text(
            msh_text,
            project_id=project_id,
            geometry_id=geometry_id,
            element_type=element_type,
        )


def parse_msh2_text(
    msh_text: str,
    *,
    project_id: str = "",
    geometry_id: str,
    element_type: ElementType,
) -> tuple[VolumeMeshSummary, bytes]:
    """Parse ASCII Gmsh MSH v2.2 tetrahedral nodes/elements into canonical VolumeMeshData."""
    lines = [line.strip() for line in msh_text.splitlines()]
    node_map: dict[int, tuple[float, float, float]] = {}
    tet_rows: list[list[int]] = []

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line == "$Nodes":
            idx += 1
            count = int(lines[idx])
            idx += 1
            for _ in range(count):
                parts = lines[idx].split()
                node_map[int(parts[0])] = (float(parts[1]), float(parts[2]), float(parts[3]))
                idx += 1
        elif line == "$Elements":
            idx += 1
            count = int(lines[idx])
            idx += 1
            target_gmsh_type = 11 if element_type is ElementType.C3D10 else 4
            for _ in range(count):
                parts = lines[idx].split()
                el_type = int(parts[1])
                num_tags = int(parts[2])
                raw_nodes = [int(tok) for tok in parts[3 + num_tags :]]
                if el_type == target_gmsh_type:
                    if target_gmsh_type == 11:
                        # Remap Gmsh MSH2 C3D10 [0..7, 8(2-3), 9(1-3)]
                        # into canonical order [0..7, 8(1-3), 9(2-3)]
                        raw_nodes = [
                            raw_nodes[0],
                            raw_nodes[1],
                            raw_nodes[2],
                            raw_nodes[3],
                            raw_nodes[4],
                            raw_nodes[5],
                            raw_nodes[6],
                            raw_nodes[7],
                            raw_nodes[9],
                            raw_nodes[8],
                        ]
                    tet_rows.append(raw_nodes)
                idx += 1
        idx += 1

    if not tet_rows or not node_map:
        raise InvalidGeometryError(
            f"MSH v2.2 output contains no {element_type.value} volumetric elements."
        )

    used_ids = sorted({nid for row in tet_rows for nid in row})
    id_to_idx = {nid: pos for pos, nid in enumerate(used_ids)}
    nodes = np.asarray([node_map[nid] for nid in used_ids], dtype=np.float64)
    elements = np.asarray([[id_to_idx[nid] for nid in row] for row in tet_rows], dtype=np.int32)

    # Ensure positive orientation for every tetrahedron and compute total volume & scaled Jacobian
    total_volume = 0.0
    min_jac = float("inf")
    for e_idx in range(len(elements)):
        c = nodes[elements[e_idx, :4]]
        v1 = c[1] - c[0]
        v2 = c[2] - c[0]
        v3 = c[3] - c[0]
        det = float(np.dot(v1, np.cross(v2, v3)))
        if det < 0.0:
            elements[e_idx, 1], elements[e_idx, 2] = elements[e_idx, 2], elements[e_idx, 1]
            if element_type is ElementType.C3D10:
                elements[e_idx, 4], elements[e_idx, 6] = elements[e_idx, 6], elements[e_idx, 4]
                elements[e_idx, 8], elements[e_idx, 9] = elements[e_idx, 9], elements[e_idx, 8]
            det = -det

        vol = det / 6.0
        total_volume += vol
        edges = [
            float(np.linalg.norm(c[b] - c[a]))
            for a in range(4)
            for b in range(a + 1, 4)
        ]
        max_edge = max(edges)
        scaled_j = (math.sqrt(2.0) * det) / (max_edge**3) if max_edge > 0.0 else 0.0
        min_jac = min(min_jac, scaled_j)

    surface_triangles, surface_face_nodes = extract_tet_boundary_faces(elements)
    mesh_data = VolumeMeshData(
        element_type=element_type,
        nodes=nodes,
        elements=elements,
        surface_triangles=surface_triangles,
        surface_face_nodes=surface_face_nodes,
    )
    summary = VolumeMeshSummary(
        id=str(uuid.uuid4()),
        geometry_id=geometry_id,
        element_type=element_type,
        node_count=len(nodes),
        element_count=len(elements),
        total_volume=total_volume,
        min_scaled_jacobian=min_jac,
        project_id=project_id,
        surface_triangle_count=len(surface_triangles),
    )
    return summary, serialize_volume_mesh(mesh_data)


def extract_tet_boundary_faces(
    elements: NDArray[np.int32],
) -> tuple[NDArray[np.int32], NDArray[np.int32] | None]:
    """Extract outward boundary triangles and optional 6-node T6 face nodes for C3D10."""
    is_quadratic = elements.shape[1] == 10
    # Outward local corner triangles (+ 3 edge midpoints for C3D10) for positive tet (0,1,2,3):
    # face (c0, c1, c2) has midsides (c0-c1, c1-c2, c2-c0)
    local_faces = (
        (0, 2, 1, 6, 5, 4),
        (0, 1, 3, 4, 8, 7),
        (0, 3, 2, 7, 9, 6),
        (1, 2, 3, 5, 9, 8),
    )
    face_counts: dict[tuple[int, int, int], int] = {}
    oriented_corners: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    oriented_full: dict[tuple[int, int, int], tuple[int, int, int, int, int, int]] = {}

    for row in elements:
        for c0, c1, c2, m01, m12, m20 in local_faces:
            tri = (int(row[c0]), int(row[c1]), int(row[c2]))
            key = (min(tri), sum(tri) - min(tri) - max(tri), max(tri))
            face_counts[key] = face_counts.get(key, 0) + 1
            oriented_corners[key] = tri
            if is_quadratic:
                oriented_full[key] = (
                    tri[0],
                    tri[1],
                    tri[2],
                    int(row[m01]),
                    int(row[m12]),
                    int(row[m20]),
                )

    boundary_keys = [k for k, count in face_counts.items() if count == 1]
    if not boundary_keys:
        empty_tris = np.empty((0, 3), dtype=np.int32)
        empty_t6 = np.empty((0, 6), dtype=np.int32) if is_quadratic else None
        return empty_tris, empty_t6

    tris = np.asarray([oriented_corners[k] for k in boundary_keys], dtype=np.int32)
    t6_faces = (
        np.asarray([oriented_full[k] for k in boundary_keys], dtype=np.int32)
        if is_quadratic
        else None
    )
    return tris, t6_faces


def extract_tet_boundary_triangles(elements: NDArray[np.int32]) -> NDArray[np.int32]:
    """Extract outward-oriented exterior boundary corner triangles from C3D4/C3D10."""
    tris, _ = extract_tet_boundary_faces(elements)
    return tris


class CompositeVolumetricMesher:
    """Dispatches volumetric meshing requests to strategy implementations by ElementType."""

    def __init__(self, meshers: Sequence[VolumetricMesherPort]) -> None:
        self._by_element: dict[ElementType, VolumetricMesherPort] = {}
        for mesher in meshers:
            for elem_type in mesher.supported_elements():
                self._by_element[elem_type] = mesher

    def supported_elements(self) -> frozenset[ElementType]:
        return frozenset(self._by_element.keys())

    def generate_volume_mesh(
        self,
        surface_stl_bytes: bytes,
        *,
        project_id: str = "",
        geometry_id: str,
        element_type: ElementType,
        target_element_size: float,
    ) -> tuple[VolumeMeshSummary, bytes]:
        mesher = self._by_element.get(element_type)
        if mesher is None:
            supported = sorted(e.value for e in self._by_element)
            raise DomainValidationError(
                f"ElementType '{element_type.value}' is not supported. Supported: {supported}."
            )
        return mesher.generate_volume_mesh(
            surface_stl_bytes,
            project_id=project_id,
            geometry_id=geometry_id,
            element_type=element_type,
            target_element_size=target_element_size,
        )
