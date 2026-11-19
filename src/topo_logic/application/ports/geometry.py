"""Ports (interfaces) for geometry ingestion, mesh repair, and volumetric meshing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from topo_logic.domain.geometry import (
    ElementType,
    GeometryFormat,
    MeshDiagnostics,
    RepairReport,
    VolumeMeshSummary,
)
from topo_logic.domain.units import UnitSystem


@dataclass(frozen=True)
class RawSurfacePayload:
    """Uploaded raw 3D file payload handed to a geometry importer."""

    raw_bytes: bytes
    filename: str
    format: GeometryFormat


@dataclass(frozen=True)
class RepairedMeshResult:
    """Output of surface mesh diagnostics and optional automated repair."""

    repaired_stl_bytes: bytes
    diagnostics: MeshDiagnostics
    repair_report: RepairReport


class GeometryImporterPort(Protocol):
    """Strategy port for validating and converting uploaded 3D formats to surface STL."""

    def supported_formats(self) -> frozenset[GeometryFormat]:
        """Return geometry formats supported by this importer."""
        ...

    def extract_surface_stl(self, payload: RawSurfacePayload) -> bytes:
        """Validate uploaded geometry bytes and return canonical surface STL bytes."""
        ...


class MeshRepairPort(Protocol):
    """Port for auditing surface topology, unit-scale sanity, and Tier-1 repair."""

    def diagnose_and_repair(
        self,
        stl_bytes: bytes,
        *,
        unit_system: UnitSystem,
        auto_repair: bool,
    ) -> RepairedMeshResult:
        """Run surface diagnostics and optionally repair winding, holes, and duplicates."""
        ...


class VolumetricMesherPort(Protocol):
    """Strategy port for generating volumetric FEM/TopOpt meshes (H8, C3D4, C3D10)."""

    def supported_elements(self) -> frozenset[ElementType]:
        """Return volumetric element types supported by this mesher."""
        ...

    def generate_volume_mesh(
        self,
        surface_stl_bytes: bytes,
        *,
        project_id: str = "",
        geometry_id: str,
        element_type: ElementType,
        target_element_size: float,
    ) -> tuple[VolumeMeshSummary, bytes]:
        """Generate a validated volume mesh and return summary metadata + serialized payload."""
        ...
