"""Pydantic schemas for 3D geometry ingestion, diagnostics, and repair reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from topo_logic.domain.geometry import (
    BoundingBox3D,
    GeometryAsset,
    GeometryFormat,
    MeshDiagnostics,
    RepairReport,
)
from topo_logic.domain.units import AxisConvention, ScaleGuardWarning, UnitSystem


class BoundingBoxResponse(BaseModel):
    """Axis-aligned 3D bounding box."""

    min_corner: tuple[float, float, float]
    max_corner: tuple[float, float, float]
    size: tuple[float, float, float]
    center: tuple[float, float, float]
    diagonal: float

    @classmethod
    def from_domain(cls, bounds: BoundingBox3D) -> BoundingBoxResponse:
        return cls(
            min_corner=bounds.min_corner,
            max_corner=bounds.max_corner,
            size=bounds.size,
            center=bounds.center,
            diagonal=bounds.diagonal,
        )


class ScaleGuardResponse(BaseModel):
    """Unit-scale sanity check warning."""

    is_suspicious: bool
    suggested_scale_factor: float | None = None
    suggested_unit_system: UnitSystem | None = None
    message: str | None = None

    @classmethod
    def from_domain(cls, guard: ScaleGuardWarning) -> ScaleGuardResponse:
        return cls(
            is_suspicious=guard.is_suspicious,
            suggested_scale_factor=guard.suggested_scale_factor,
            suggested_unit_system=guard.suggested_unit_system,
            message=guard.message,
        )


class MeshDiagnosticsResponse(BaseModel):
    """Topological and geometric audit summary."""

    vertex_count: int
    triangle_count: int
    connected_components: int
    is_watertight: bool
    boundary_edge_count: int
    non_manifold_edge_count: int
    volume: float
    surface_area: float
    bounds: BoundingBoxResponse
    scale_guard: ScaleGuardResponse
    warnings: list[str]

    @classmethod
    def from_domain(cls, diag: MeshDiagnostics) -> MeshDiagnosticsResponse:
        return cls(
            vertex_count=diag.vertex_count,
            triangle_count=diag.triangle_count,
            connected_components=diag.connected_components,
            is_watertight=diag.is_watertight,
            boundary_edge_count=diag.boundary_edge_count,
            non_manifold_edge_count=diag.non_manifold_edge_count,
            volume=diag.volume,
            surface_area=diag.surface_area,
            bounds=BoundingBoxResponse.from_domain(diag.bounds),
            scale_guard=ScaleGuardResponse.from_domain(diag.scale_guard),
            warnings=list(diag.warnings),
        )


class RepairReportResponse(BaseModel):
    """Summary of surface repair steps performed."""

    applied: bool
    merged_vertices_count: int
    removed_degenerate_faces: int
    removed_duplicate_faces: int
    filled_holes: bool
    normals_fixed: bool
    warnings: list[str]

    @classmethod
    def from_domain(cls, report: RepairReport) -> RepairReportResponse:
        return cls(
            applied=report.applied,
            merged_vertices_count=report.merged_vertices_count,
            removed_degenerate_faces=report.removed_degenerate_faces,
            removed_duplicate_faces=report.removed_duplicate_faces,
            filled_holes=report.filled_holes,
            normals_fixed=report.normals_fixed,
            warnings=list(report.warnings),
        )


class GeometryAssetResponse(BaseModel):
    """Uploaded geometry metadata, diagnostics, and artifact download links."""

    id: str
    project_id: str
    filename: str
    format: GeometryFormat
    unit_system: UnitSystem
    axis_convention: AxisConvention
    has_repaired_artifact: bool
    diagnostics: MeshDiagnosticsResponse
    repair_report: RepairReportResponse
    created_at: datetime

    @classmethod
    def from_domain(cls, asset: GeometryAsset) -> GeometryAssetResponse:
        return cls(
            id=asset.id,
            project_id=asset.project_id,
            filename=asset.filename,
            format=asset.format,
            unit_system=asset.unit_system,
            axis_convention=asset.axis_convention,
            has_repaired_artifact=asset.repaired_artifact_key is not None,
            diagnostics=MeshDiagnosticsResponse.from_domain(asset.diagnostics),
            repair_report=RepairReportResponse.from_domain(asset.repair_report),
            created_at=asset.created_at,
        )
