"""Surface mesh diagnostics and Tier-1 automated repair adapter using trimesh (MIT)."""

from __future__ import annotations

import io
import math

import numpy as np
import trimesh

from topo_logic.application.ports.geometry import RepairedMeshResult
from topo_logic.domain.exceptions import InvalidGeometryError
from topo_logic.domain.geometry import BoundingBox3D, MeshDiagnostics, RepairReport
from topo_logic.domain.units import UnitSystem, evaluate_scale_guard


class TrimeshSurfaceRepairer:
    """Implements MeshRepairPort following the Tier-1 STL repair pipeline."""

    def diagnose_and_repair(
        self,
        stl_bytes: bytes,
        *,
        unit_system: UnitSystem,
        auto_repair: bool,
    ) -> RepairedMeshResult:
        mesh = self._load_raw_mesh(stl_bytes)
        raw_vertex_count = len(mesh.vertices)
        raw_bounds = self._extract_bounds(mesh)
        if raw_bounds.diagonal <= 0.0:
            raise InvalidGeometryError("Geometry bounding box has zero diagonal extent.")

        merged_vertices_count = 0
        removed_degenerate_faces = 0
        removed_duplicate_faces = 0
        filled_holes = False
        normals_fixed = False
        repair_warnings: list[str] = []

        if auto_repair:
            tol = max(1e-9, 1e-6 * raw_bounds.diagonal)
            digits = max(1, min(9, int(-math.floor(math.log10(tol)))))
            mesh.merge_vertices(merge_tex=False, merge_norm=False, digits_vertex=digits)
            merged_vertices_count = max(0, raw_vertex_count - len(mesh.vertices))

            nondegenerate = np.asarray(mesh.nondegenerate_faces(), dtype=bool)
            removed_degenerate_faces = int(np.sum(~nondegenerate))
            if removed_degenerate_faces > 0:
                mesh.update_faces(nondegenerate)

            if len(mesh.faces) == 0:
                raise InvalidGeometryError(
                    "Mesh has no valid triangles remaining after removing degenerate faces."
                )

            unique_mask = np.asarray(mesh.unique_faces(), dtype=bool)
            removed_duplicate_faces = int(np.sum(~unique_mask))
            if removed_duplicate_faces > 0:
                mesh.update_faces(unique_mask)

            was_watertight = bool(mesh.is_watertight)
            if not was_watertight:
                faces_before_fill = len(mesh.faces)
                try:
                    self._fill_boundary_holes(mesh)
                except Exception as exc:
                    repair_warnings.append(f"Hole filling failed: {exc}")
                filled_holes = (len(mesh.faces) > faces_before_fill) or (
                    not was_watertight and bool(mesh.is_watertight)
                )

            faces_before_normals = np.asarray(mesh.faces, copy=True)
            mesh.fix_normals()
            if bool(mesh.is_watertight) and float(mesh.volume) < 0.0:
                mesh.invert()
            normals_fixed = not np.array_equal(faces_before_normals, np.asarray(mesh.faces))

        bounds = self._extract_bounds(mesh)
        if bounds.diagonal <= 0.0:
            raise InvalidGeometryError("Repaired mesh bounding box collapsed to zero extent.")

        boundary_edges, non_manifold_edges = self._count_edge_anomalies(mesh)
        connected_components = self._count_connected_components(mesh)
        is_watertight = bool(mesh.is_watertight)
        volume = float(mesh.volume) if is_watertight else 0.0
        surface_area = float(mesh.area)

        scale_guard = evaluate_scale_guard(bounds.diagonal, unit_system)
        warnings: list[str] = []
        if scale_guard.is_suspicious and scale_guard.message:
            warnings.append(scale_guard.message)
        if not is_watertight:
            warnings.append(
                f"Surface mesh is not watertight ({boundary_edges} open boundary edges)."
            )
        if non_manifold_edges > 0:
            warnings.append(
                f"Surface mesh contains {non_manifold_edges} non-manifold edge(s)."
            )
        if connected_components > 1:
            warnings.append(
                f"Mesh contains {connected_components} disconnected shells/components."
            )

        diagnostics = MeshDiagnostics(
            vertex_count=len(mesh.vertices),
            triangle_count=len(mesh.faces),
            connected_components=connected_components,
            is_watertight=is_watertight,
            boundary_edge_count=boundary_edges,
            non_manifold_edge_count=non_manifold_edges,
            volume=volume,
            surface_area=surface_area,
            bounds=bounds,
            scale_guard=scale_guard,
            warnings=tuple(warnings),
        )
        repair_report = RepairReport(
            applied=auto_repair,
            merged_vertices_count=merged_vertices_count,
            removed_degenerate_faces=removed_degenerate_faces,
            removed_duplicate_faces=removed_duplicate_faces,
            filled_holes=filled_holes,
            normals_fixed=normals_fixed,
            warnings=tuple(repair_warnings),
        )

        exported = mesh.export(file_type="stl")
        if isinstance(exported, bytes):
            repaired_bytes = exported
        elif isinstance(exported, str):
            repaired_bytes = exported.encode("utf-8")
        else:
            raise InvalidGeometryError("Unexpected non-binary STL export payload.")
        return RepairedMeshResult(
            repaired_stl_bytes=repaired_bytes,
            diagnostics=diagnostics,
            repair_report=repair_report,
        )

    @staticmethod
    def _load_raw_mesh(stl_bytes: bytes) -> trimesh.Trimesh:
        try:
            loaded = trimesh.load(
                io.BytesIO(stl_bytes),
                file_type="stl",
                force="mesh",
                process=False,
            )
        except Exception as exc:
            raise InvalidGeometryError(f"Failed to load STL bytes for diagnostics: {exc}") from exc

        if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
            raise InvalidGeometryError("STL payload does not contain valid triangular faces.")
        return loaded

    @staticmethod
    def _extract_bounds(mesh: trimesh.Trimesh) -> BoundingBox3D:
        bounds_arr = np.asarray(mesh.bounds, dtype=float)
        return BoundingBox3D(
            min_corner=(
                float(bounds_arr[0, 0]),
                float(bounds_arr[0, 1]),
                float(bounds_arr[0, 2]),
            ),
            max_corner=(
                float(bounds_arr[1, 0]),
                float(bounds_arr[1, 1]),
                float(bounds_arr[1, 2]),
            ),
        )

    @staticmethod
    def _count_edge_anomalies(mesh: trimesh.Trimesh) -> tuple[int, int]:
        edges = np.asarray(mesh.edges_sorted)
        if len(edges) == 0:
            return 0, 0
        _, counts = np.unique(edges, axis=0, return_counts=True)
        boundary_edges = int(np.sum(counts == 1))
        non_manifold_edges = int(np.sum(counts > 2))
        return boundary_edges, non_manifold_edges

    @staticmethod
    def _count_connected_components(mesh: trimesh.Trimesh) -> int:
        if len(mesh.faces) == 0:
            return 0
        components = trimesh.graph.connected_components(
            edges=mesh.face_adjacency,
            nodes=np.arange(len(mesh.faces)),
            min_len=1,
            engine="scipy",
        )
        return max(1, len(components))

    @staticmethod
    def _fill_boundary_holes(mesh: trimesh.Trimesh, max_cycle_len: int = 64) -> bool:
        """Close small manifold boundary loops without requiring optional networkx."""
        if len(mesh.faces) < 3 or bool(mesh.is_watertight):
            return False

        edges_sorted = np.asarray(mesh.edges_sorted)
        edges_directed = np.asarray(mesh.edges)
        if len(edges_sorted) == 0:
            return False

        _, first_idx, counts = np.unique(
            edges_sorted, axis=0, return_index=True, return_counts=True
        )
        boundary_directed = edges_directed[first_idx[counts == 1]]
        if len(boundary_directed) < 3:
            return False

        adj: dict[int, list[int]] = {}
        directed_set: set[tuple[int, int]] = set()
        for row in boundary_directed:
            u, v = int(row[0]), int(row[1])
            directed_set.add((u, v))
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, []).append(u)

        visited_edges: set[tuple[int, int]] = set()
        new_triangles: list[tuple[int, int, int]] = []

        for start, neighbors in adj.items():
            for nxt in neighbors:
                edge_key = (start, nxt) if start < nxt else (nxt, start)
                if edge_key in visited_edges:
                    continue
                cycle = [start]
                visited_edges.add(edge_key)
                prev, curr = start, nxt
                closed = False
                while len(cycle) <= max_cycle_len:
                    if curr == start:
                        closed = True
                        break
                    cycle.append(curr)
                    next_candidates = [
                        nb
                        for nb in adj.get(curr, ())
                        if nb != prev
                        and ((curr, nb) if curr < nb else (nb, curr)) not in visited_edges
                    ]
                    if not next_candidates:
                        break
                    chosen = next_candidates[0]
                    step_key = (curr, chosen) if curr < chosen else (chosen, curr)
                    visited_edges.add(step_key)
                    prev, curr = curr, chosen

                if closed and 3 <= len(cycle) <= max_cycle_len:
                    v0 = cycle[0]
                    for idx in range(1, len(cycle) - 1):
                        tri = (v0, cycle[idx], cycle[idx + 1])
                        tri_edges = ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))
                        if any(edge in directed_set for edge in tri_edges):
                            tri = (v0, cycle[idx + 1], cycle[idx])
                        new_triangles.append(tri)

        if not new_triangles:
            return False

        mesh.extend_faces(np.asarray(new_triangles, dtype=mesh.faces.dtype))
        return True
