"""Surface geometry diagnostics, repair reports, and volumetric mesh summaries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from topo_logic.domain.exceptions import DomainValidationError
from topo_logic.domain.units import AxisConvention, ScaleGuardWarning, UnitSystem


class GeometryFormat(StrEnum):
    """Supported 3D surface and CAD geometry formats across project phases."""

    STL = "stl"
    OBJ = "obj"
    PLY = "ply"
    STEP = "step"


class ElementType(StrEnum):
    """Volumetric finite element formulations."""

    H8 = "H8"
    C3D4 = "C3D4"
    C3D10 = "C3D10"


@dataclass(frozen=True)
class BoundingBox3D:
    """Axis-aligned 3D bounding box."""

    min_corner: tuple[float, float, float]
    max_corner: tuple[float, float, float]

    def __post_init__(self) -> None:
        for lo, hi in zip(self.min_corner, self.max_corner, strict=True):
            if not (math.isfinite(lo) and math.isfinite(hi)):
                raise DomainValidationError("Bounding-box coordinates must be finite.")
            if lo > hi:
                raise DomainValidationError(
                    "Bounding-box min_corner must be <= max_corner on every axis.",
                    details={"min_corner": self.min_corner, "max_corner": self.max_corner},
                )

    @property
    def size(self) -> tuple[float, float, float]:
        return (
            self.max_corner[0] - self.min_corner[0],
            self.max_corner[1] - self.min_corner[1],
            self.max_corner[2] - self.min_corner[2],
        )

    @property
    def center(self) -> tuple[float, float, float]:
        return (
            0.5 * (self.min_corner[0] + self.max_corner[0]),
            0.5 * (self.min_corner[1] + self.max_corner[1]),
            0.5 * (self.min_corner[2] + self.max_corner[2]),
        )

    @property
    def diagonal(self) -> float:
        dx, dy, dz = self.size
        return math.sqrt(dx * dx + dy * dy + dz * dz)


@dataclass(frozen=True)
class RepairReport:
    """Summary of automated surface mesh repair actions."""

    applied: bool
    merged_vertices_count: int
    removed_degenerate_faces: int
    removed_duplicate_faces: int
    filled_holes: bool
    normals_fixed: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MeshDiagnostics:
    """Topological and geometric audit report for an ingested surface mesh."""

    vertex_count: int
    triangle_count: int
    connected_components: int
    is_watertight: bool
    boundary_edge_count: int
    non_manifold_edge_count: int
    volume: float
    surface_area: float
    bounds: BoundingBox3D
    scale_guard: ScaleGuardWarning
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeometryAsset:
    """Persisted geometry asset owned by a project."""

    id: str
    project_id: str
    filename: str
    format: GeometryFormat
    unit_system: UnitSystem
    axis_convention: AxisConvention
    raw_artifact_key: str
    repaired_artifact_key: str | None
    diagnostics: MeshDiagnostics
    repair_report: RepairReport
    created_at: datetime


@dataclass(frozen=True)
class VolumeMeshSummary:
    """Verification summary of a generated 3D finite element mesh."""

    id: str
    geometry_id: str
    element_type: ElementType
    node_count: int
    element_count: int
    total_volume: float
    min_scaled_jacobian: float
    project_id: str = ""
    surface_triangle_count: int = 0
    artifact_key: str = ""
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.node_count <= 0 or self.element_count <= 0:
            raise DomainValidationError("Volume mesh must have positive node and element counts.")
        if self.min_scaled_jacobian <= 0.0:
            raise DomainValidationError(
                "Volume mesh contains inverted or degenerate elements (scaled Jacobian <= 0).",
                details={"min_scaled_jacobian": self.min_scaled_jacobian},
            )
