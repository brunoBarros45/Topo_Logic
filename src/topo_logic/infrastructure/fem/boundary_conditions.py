"""Boundary region resolution, tributary-area Neumann loads, and Dirichlet DOF extraction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from topo_logic.domain.boundary import (
    BoundaryRegion,
    BoundingBoxSelector,
    CadFaceTagSelector,
    ForceLoad,
    LoadCase,
    PlaneSelector,
    PressureLoad,
    SupportBC,
    TriangleSetSelector,
)
from topo_logic.domain.exceptions import DomainValidationError, UnderconstrainedModelError
from topo_logic.domain.geometry import ElementType
from topo_logic.infrastructure.mesh.volume_mesh import VolumeMeshData


@dataclass(frozen=True)
class ResolvedRegion:
    """Volume node indices and exterior surface triangle indices matching a BoundaryRegion."""

    region_id: str
    node_indices: NDArray[np.int32]
    surface_triangle_indices: NDArray[np.int32]


def resolve_regions(
    mesh: VolumeMeshData, regions: tuple[BoundaryRegion, ...]
) -> dict[str, ResolvedRegion]:
    """Resolve client-agnostic BoundaryRegions onto volumetric mesh nodes and surface faces."""
    nodes = mesh.nodes
    tris = mesh.surface_triangles
    has_tris = len(tris) > 0
    tri_centroids = nodes[tris].mean(axis=1) if has_tris else np.empty((0, 3), dtype=np.float64)

    resolved: dict[str, ResolvedRegion] = {}
    for region in regions:
        sel = region.selector
        if isinstance(sel, PlaneSelector):
            point = np.asarray(sel.point, dtype=np.float64)
            normal = np.asarray(sel.normal, dtype=np.float64)
            normal = normal / np.linalg.norm(normal)

            node_dist = np.abs((nodes - point) @ normal)
            node_indices = np.flatnonzero(node_dist <= sel.tolerance).astype(np.int32)

            if has_tris:
                v_dists = node_dist[tris]
                tri_mask = np.all(v_dists <= sel.tolerance, axis=1)
                # Also filter by centroid alignment and ignore faces with tiny projection if strict
                surf_indices = np.flatnonzero(tri_mask).astype(np.int32)
                if len(surf_indices) == 0 and len(node_indices) > 0:
                    tri_cent_dist = np.abs((tri_centroids - point) @ normal)
                    surf_indices = np.flatnonzero(tri_cent_dist <= sel.tolerance).astype(np.int32)
            else:
                surf_indices = np.empty(0, dtype=np.int32)

        elif isinstance(sel, BoundingBoxSelector):
            lo = np.asarray(sel.min_corner, dtype=np.float64)
            hi = np.asarray(sel.max_corner, dtype=np.float64)
            in_box = np.all((nodes >= lo) & (nodes <= hi), axis=1)
            node_indices = np.flatnonzero(in_box).astype(np.int32)
            if has_tris:
                tri_in_box = np.all(in_box[tris], axis=1)
                surf_indices = np.flatnonzero(tri_in_box).astype(np.int32)
            else:
                surf_indices = np.empty(0, dtype=np.int32)

        elif isinstance(sel, TriangleSetSelector):
            idx_arr = np.asarray(sel.triangle_indices, dtype=np.int32)
            if not has_tris or np.any(idx_arr >= len(tris)):
                raise DomainValidationError(
                    f"TriangleSetSelector in region '{region.id}' references out-of-range "
                    "surface triangle indices.",
                    details={"region_id": region.id, "surface_triangle_count": len(tris)},
                )
            surf_indices = np.unique(idx_arr).astype(np.int32)
            face_source = (
                mesh.surface_face_nodes[surf_indices]
                if mesh.surface_face_nodes is not None
                else tris[surf_indices]
            )
            node_indices = np.unique(face_source.ravel()).astype(np.int32)

        elif isinstance(sel, CadFaceTagSelector):
            if mesh.surface_face_tags is None or not has_tris:
                raise DomainValidationError(
                    f"Region '{region.id}' uses CadFaceTagSelector, but this mesh does not carry "
                    "native CAD face tags.",
                    details={"region_id": region.id},
                )
            tag_mask = np.isin(mesh.surface_face_tags, sel.face_tags)
            surf_indices = np.flatnonzero(tag_mask).astype(np.int32)
            face_source = (
                mesh.surface_face_nodes[surf_indices]
                if mesh.surface_face_nodes is not None
                else tris[surf_indices]
            )
            node_indices = (
                np.unique(face_source.ravel()).astype(np.int32)
                if len(surf_indices) > 0
                else np.empty(0, dtype=np.int32)
            )
        else:
            raise DomainValidationError(f"Unsupported selector type in region '{region.id}'.")

        if len(node_indices) == 0:
            raise DomainValidationError(
                f"BoundaryRegion '{region.name}' ({region.id}) matched zero volume mesh nodes.",
                details={"region_id": region.id},
            )

        resolved[region.id] = ResolvedRegion(
            region_id=region.id,
            node_indices=node_indices,
            surface_triangle_indices=surf_indices,
        )

    return resolved


def extract_dirichlet_dofs(
    mesh: VolumeMeshData,
    resolved_regions: dict[str, ResolvedRegion],
    supports: tuple[SupportBC, ...],
) -> tuple[NDArray[np.int32], NDArray[np.float64]]:
    """Map SupportBC definitions into unique restrained DOF indices and prescribed values."""
    dof_values: dict[int, float] = {}
    restrained_axes = [False, False, False]

    for support in supports:
        region = resolved_regions[support.region_id]
        for axis in range(3):
            if not support.restrained_dofs[axis]:
                continue
            restrained_axes[axis] = True
            val = float(support.prescribed_displacement[axis])
            dofs = 3 * region.node_indices + axis
            for dof in dofs:
                dof_values[int(dof)] = val

    if len(dof_values) < 6 or not all(restrained_axes):
        raise UnderconstrainedModelError(
            "Model is underconstrained: at least 6 total DOFs across all 3 translational axes "
            "must be restrained to eliminate 3D rigid-body modes.",
            details={
                "restrained_dof_count": len(dof_values),
                "restrained_axes": restrained_axes,
            },
        )

    sorted_dofs = np.array(sorted(dof_values.keys()), dtype=np.int32)
    prescribed = np.array([dof_values[int(d)] for d in sorted_dofs], dtype=np.float64)
    return sorted_dofs, prescribed


def assemble_load_vector(
    mesh: VolumeMeshData,
    resolved_regions: dict[str, ResolvedRegion],
    load_case: LoadCase,
) -> NDArray[np.float64]:
    """Assemble global nodal load vector f_ext using tributary-area surface integration."""
    ndof = 3 * len(mesh.nodes)
    f_ext = np.zeros(ndof, dtype=np.float64)

    for load in load_case.loads:
        region = resolved_regions[load.region_id]
        if isinstance(load, ForceLoad):
            _apply_force_load(mesh, region, np.asarray(load.force_vector, dtype=np.float64), f_ext)
        elif isinstance(load, PressureLoad):
            _apply_pressure_load(mesh, region, load.magnitude, f_ext)
        else:
            raise DomainValidationError(
                f"Unsupported load definition in load case '{load_case.id}'."
            )

    return f_ext


def _extract_consistent_face_patches(
    mesh: VolumeMeshData,
    tri_idx: NDArray[np.int32],
) -> list[tuple[NDArray[np.int32], NDArray[np.float64]]]:
    """Return (node_groups (M, K), outward_area_vectors (M, 3)) for consistent traction."""
    if len(tri_idx) == 0:
        return []

    patches: list[tuple[NDArray[np.int32], NDArray[np.float64]]] = []

    if mesh.element_type is ElementType.C3D10 and mesh.surface_face_nodes is not None:
        t6 = mesh.surface_face_nodes[tri_idx]
        p0 = mesh.nodes[t6[:, 0]]
        p1 = mesh.nodes[t6[:, 1]]
        p2 = mesh.nodes[t6[:, 2]]
        area_vecs = 0.5 * np.cross(p1 - p0, p2 - p0)
        # Consistent quadratic T6 shape-function integral: 0 on corners, 1/3 area on midsides
        patches.append((t6[:, 3:6], area_vecs))
        return patches

    remaining_tris = tri_idx
    if (
        mesh.element_type is ElementType.H8
        and mesh.surface_quads is not None
        and mesh.surface_tri_to_quad is not None
    ):
        quad_ids = mesh.surface_tri_to_quad[tri_idx]
        uniq_q, counts = np.unique(quad_ids, return_counts=True)
        complete_quads = uniq_q[counts == 2]
        if len(complete_quads) > 0:
            quad_nodes = mesh.surface_quads[complete_quads]
            q0 = mesh.nodes[quad_nodes[:, 0]]
            q1 = mesh.nodes[quad_nodes[:, 1]]
            q2 = mesh.nodes[quad_nodes[:, 2]]
            q3 = mesh.nodes[quad_nodes[:, 3]]
            quad_area_vecs = 0.5 * (
                np.cross(q1 - q0, q2 - q0) + np.cross(q2 - q0, q3 - q0)
            )
            patches.append((quad_nodes, quad_area_vecs))
            in_complete = np.isin(quad_ids, complete_quads)
            remaining_tris = tri_idx[~in_complete]

    if len(remaining_tris) > 0:
        tris = mesh.surface_triangles[remaining_tris]
        p0 = mesh.nodes[tris[:, 0]]
        p1 = mesh.nodes[tris[:, 1]]
        p2 = mesh.nodes[tris[:, 2]]
        patches.append((tris, 0.5 * np.cross(p1 - p0, p2 - p0)))

    return patches


def _apply_force_load(
    mesh: VolumeMeshData,
    region: ResolvedRegion,
    force_vector: NDArray[np.float64],
    f_ext: NDArray[np.float64],
) -> None:
    patches = _extract_consistent_face_patches(mesh, region.surface_triangle_indices)
    if patches:
        patch_areas = [np.linalg.norm(area_vecs, axis=1) for _, area_vecs in patches]
        total_area = float(sum(float(np.sum(a)) for a in patch_areas))
        if total_area > 0.0:
            for (node_groups, _), areas in zip(patches, patch_areas, strict=True):
                nodes_per_face = float(node_groups.shape[1])
                nodal_weights = (
                    (areas / (nodes_per_face * total_area))[:, None] * force_vector[None, :]
                )
                for col in range(node_groups.shape[1]):
                    np.add.at(f_ext, 3 * node_groups[:, col], nodal_weights[:, 0])
                    np.add.at(f_ext, 3 * node_groups[:, col] + 1, nodal_weights[:, 1])
                    np.add.at(f_ext, 3 * node_groups[:, col] + 2, nodal_weights[:, 2])
            return

    # Fallback when region represents interior nodes without exterior triangles
    n_count = len(region.node_indices)
    per_node = force_vector / float(n_count)
    f_ext[3 * region.node_indices] += per_node[0]
    f_ext[3 * region.node_indices + 1] += per_node[1]
    f_ext[3 * region.node_indices + 2] += per_node[2]


def _apply_pressure_load(
    mesh: VolumeMeshData,
    region: ResolvedRegion,
    magnitude: float,
    f_ext: NDArray[np.float64],
) -> None:
    patches = _extract_consistent_face_patches(mesh, region.surface_triangle_indices)
    if not patches:
        raise DomainValidationError(
            f"PressureLoad on region '{region.region_id}' requires exterior surface triangles.",
            details={"region_id": region.region_id},
        )

    for node_groups, area_vecs in patches:
        nodes_per_face = float(node_groups.shape[1])
        # Outward area vector; positive pressure pushes inward (-normal)
        per_node_force = (-magnitude / nodes_per_face) * area_vecs
        for col in range(node_groups.shape[1]):
            np.add.at(f_ext, 3 * node_groups[:, col], per_node_force[:, 0])
            np.add.at(f_ext, 3 * node_groups[:, col] + 1, per_node_force[:, 1])
            np.add.at(f_ext, 3 * node_groups[:, col] + 2, per_node_force[:, 2])
