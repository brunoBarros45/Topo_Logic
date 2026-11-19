"""Pydantic schemas for volumetric mesh generation and exterior surface picking."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from topo_logic.domain.geometry import ElementType, VolumeMeshSummary


class MeshGenerateRequest(BaseModel):
    """Request payload to volumetrically mesh an ingested watertight geometry."""

    geometry_id: str = Field(min_length=1)
    element_type: ElementType = ElementType.H8
    target_element_size: float = Field(gt=0.0)


class VolumeMeshResponse(BaseModel):
    """Summary metadata for a generated volumetric FEM/TopOpt mesh."""

    id: str
    project_id: str
    geometry_id: str
    element_type: ElementType
    node_count: int
    element_count: int
    total_volume: float
    min_scaled_jacobian: float
    surface_triangle_count: int
    created_at: datetime | None = None

    @classmethod
    def from_domain(cls, summary: VolumeMeshSummary) -> VolumeMeshResponse:
        return cls(
            id=summary.id,
            project_id=summary.project_id,
            geometry_id=summary.geometry_id,
            element_type=summary.element_type,
            node_count=summary.node_count,
            element_count=summary.element_count,
            total_volume=summary.total_volume,
            min_scaled_jacobian=summary.min_scaled_jacobian,
            surface_triangle_count=summary.surface_triangle_count,
            created_at=summary.created_at,
        )


class MeshSurfaceResponse(BaseModel):
    """Indexed exterior boundary surface triangles mapped directly to volume node IDs."""

    mesh_id: str
    element_type: ElementType
    node_count: int
    surface_triangle_count: int
    nodes: list[list[float]]
    surface_triangles: list[list[int]]
