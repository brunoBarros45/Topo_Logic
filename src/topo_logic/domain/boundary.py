"""Client-agnostic boundary region selectors, supports, multi-loadcases, and design zones."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from topo_logic.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class TriangleSetSelector:
    """Select surface triangles explicitly (used by interactive Web viewport flood-fill)."""

    triangle_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.triangle_indices:
            raise DomainValidationError("TriangleSetSelector requires at least one triangle index.")
        if any(idx < 0 for idx in self.triangle_indices):
            raise DomainValidationError("Triangle indices must be non-negative.")


@dataclass(frozen=True)
class PlaneSelector:
    """Select boundary entities lying within tolerance of a plane (CLI & benchmarks)."""

    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    tolerance: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (*self.point, *self.normal)):
            raise DomainValidationError("PlaneSelector coordinates and normal must be finite.")
        nx, ny, nz = self.normal
        norm = math.sqrt(nx * nx + ny * ny + nz * nz)
        if norm <= 0.0:
            raise DomainValidationError("PlaneSelector normal vector must have non-zero length.")
        if not math.isfinite(self.tolerance) or self.tolerance <= 0.0:
            raise DomainValidationError("PlaneSelector tolerance must be strictly positive.")


@dataclass(frozen=True)
class BoundingBoxSelector:
    """Select boundary entities enclosed by an axis-aligned 3D box."""

    min_corner: tuple[float, float, float]
    max_corner: tuple[float, float, float]

    def __post_init__(self) -> None:
        for lo, hi in zip(self.min_corner, self.max_corner, strict=True):
            if not (math.isfinite(lo) and math.isfinite(hi)):
                raise DomainValidationError("BoundingBoxSelector coordinates must be finite.")
            if lo > hi:
                raise DomainValidationError(
                    "BoundingBoxSelector min_corner must be <= max_corner on every axis."
                )


@dataclass(frozen=True)
class CadFaceTagSelector:
    """Select native CAD B-Rep faces by persistent tag (STEP & Fusion 360 Add-In)."""

    face_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.face_tags or any(not tag.strip() for tag in self.face_tags):
            raise DomainValidationError("CadFaceTagSelector requires non-empty face tags.")


RegionSelector = (
    TriangleSetSelector | PlaneSelector | BoundingBoxSelector | CadFaceTagSelector
)


@dataclass(frozen=True)
class BoundaryRegion:
    """Named boundary selection decoupled from client geometry representation."""

    id: str
    name: str
    selector: RegionSelector

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise DomainValidationError("BoundaryRegion id and name must not be empty.")


class SupportType(StrEnum):
    """Supported Dirichlet restraint types."""

    FIXED = "fixed"
    DISPLACEMENT = "displacement"
    SYMMETRY = "symmetry"


@dataclass(frozen=True)
class SupportBC:
    """Dirichlet boundary condition applied to a boundary region."""

    region_id: str
    support_type: SupportType
    restrained_dofs: tuple[bool, bool, bool] = (True, True, True)
    prescribed_displacement: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if not self.region_id.strip():
            raise DomainValidationError("SupportBC region_id must not be empty.")
        if not any(self.restrained_dofs):
            raise DomainValidationError("SupportBC must restrain at least one translational DOF.")
        if not all(math.isfinite(v) for v in self.prescribed_displacement):
            raise DomainValidationError("Prescribed displacements must be finite.")


@dataclass(frozen=True)
class ForceLoad:
    """Total resultant nodal force distributed consistently over a surface region."""

    region_id: str
    force_vector: tuple[float, float, float]

    def __post_init__(self) -> None:
        if not self.region_id.strip():
            raise DomainValidationError("ForceLoad region_id must not be empty.")
        if not all(math.isfinite(v) for v in self.force_vector):
            raise DomainValidationError("Force vector components must be finite.")
        fx, fy, fz = self.force_vector
        if math.sqrt(fx * fx + fy * fy + fz * fz) <= 0.0:
            raise DomainValidationError("ForceLoad force_vector must have non-zero magnitude.")


@dataclass(frozen=True)
class PressureLoad:
    """Uniform normal surface pressure load (positive along inward/outward normal)."""

    region_id: str
    magnitude: float

    def __post_init__(self) -> None:
        if not self.region_id.strip():
            raise DomainValidationError("PressureLoad region_id must not be empty.")
        if not math.isfinite(self.magnitude) or self.magnitude == 0.0:
            raise DomainValidationError("PressureLoad magnitude must be finite and non-zero.")


LoadDefinition = ForceLoad | PressureLoad


@dataclass(frozen=True)
class LoadCase:
    """Independent structural load case for linear static FEM and multi-loadcase TopOpt."""

    id: str
    name: str
    loads: tuple[LoadDefinition, ...]
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise DomainValidationError("LoadCase id and name must not be empty.")
        if not self.loads:
            raise DomainValidationError("LoadCase must contain at least one load definition.")
        if not math.isfinite(self.weight) or self.weight <= 0.0:
            raise DomainValidationError("LoadCase weight must be finite and strictly positive.")


class DesignZoneType(StrEnum):
    """Non-design domain tags preserved or excluded during Topology Optimization."""

    PASSIVE_SOLID = "passive_solid"
    PASSIVE_VOID = "passive_void"


@dataclass(frozen=True)
class DesignZone:
    """Non-design region assignment inside a Topology Optimization study."""

    region_id: str
    zone_type: DesignZoneType

    def __post_init__(self) -> None:
        if not self.region_id.strip():
            raise DomainValidationError("DesignZone region_id must not be empty.")
