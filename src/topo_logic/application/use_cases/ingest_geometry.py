"""Use case pipeline for 3D geometry ingestion, scale checks, and surface repair."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from topo_logic.application.ports.geometry import (
    GeometryImporterPort,
    MeshRepairPort,
    RawSurfacePayload,
)
from topo_logic.application.ports.persistence import (
    ArtifactStoragePort,
    GeometryRepositoryPort,
    ProjectRepositoryPort,
)
from topo_logic.domain.exceptions import (
    InvalidGeometryError,
    ResourceNotFoundError,
    UnsupportedFormatError,
)
from topo_logic.domain.geometry import GeometryAsset, GeometryFormat
from topo_logic.domain.units import AxisConvention, UnitSystem


class IngestGeometryUseCase:
    """Orchestrates upload validation, surface extraction, diagnostics, repair, and storage."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepositoryPort,
        geometry_repo: GeometryRepositoryPort,
        artifact_storage: ArtifactStoragePort,
        importer: GeometryImporterPort,
        repairer: MeshRepairPort,
    ) -> None:
        self._project_repo = project_repo
        self._geometry_repo = geometry_repo
        self._storage = artifact_storage
        self._importer = importer
        self._repairer = repairer

    def supported_formats(self) -> frozenset[GeometryFormat]:
        """Expose geometry formats accepted by the configured importer strategy."""
        return self._importer.supported_formats()

    def execute(
        self,
        *,
        project_id: str,
        filename: str,
        raw_bytes: bytes,
        unit_system: UnitSystem = UnitSystem.MM_N_MPA,
        axis_convention: AxisConvention = AxisConvention.Z_UP,
        auto_repair: bool = True,
    ) -> GeometryAsset:
        """Ingest, validate, optionally repair, and persist a 3D surface geometry."""
        if self._project_repo.get(project_id) is None:
            raise ResourceNotFoundError(
                f"Project '{project_id}' was not found.",
                details={"project_id": project_id},
            )

        if not raw_bytes:
            raise InvalidGeometryError("Uploaded geometry file is empty.")

        fmt = self._resolve_format(filename)
        canonical_stl = self._importer.extract_surface_stl(
            RawSurfacePayload(raw_bytes=raw_bytes, filename=filename, format=fmt)
        )
        repair_result = self._repairer.diagnose_and_repair(
            canonical_stl,
            unit_system=unit_system,
            auto_repair=auto_repair,
        )

        geometry_id = str(uuid.uuid4())
        safe_filename = Path(filename).name or f"model.{fmt.value}"
        raw_key = f"projects/{project_id}/geometries/{geometry_id}/raw.{fmt.value}"
        self._storage.save_bytes(raw_key, raw_bytes)

        repaired_key: str | None = None
        if auto_repair:
            repaired_key = f"projects/{project_id}/geometries/{geometry_id}/repaired.stl"
            self._storage.save_bytes(repaired_key, repair_result.repaired_stl_bytes)

        asset = GeometryAsset(
            id=geometry_id,
            project_id=project_id,
            filename=safe_filename,
            format=fmt,
            unit_system=unit_system,
            axis_convention=axis_convention,
            raw_artifact_key=raw_key,
            repaired_artifact_key=repaired_key,
            diagnostics=repair_result.diagnostics,
            repair_report=repair_result.repair_report,
            created_at=datetime.now(UTC),
        )
        self._geometry_repo.save(asset)
        return asset

    def get_geometry(self, geometry_id: str) -> GeometryAsset:
        """Retrieve geometry metadata and diagnostics by ID."""
        asset = self._geometry_repo.get(geometry_id)
        if asset is None:
            raise ResourceNotFoundError(
                f"Geometry '{geometry_id}' was not found.",
                details={"geometry_id": geometry_id},
            )
        return asset

    def list_project_geometries(self, project_id: str) -> list[GeometryAsset]:
        """List all geometries belonging to a project."""
        if self._project_repo.get(project_id) is None:
            raise ResourceNotFoundError(
                f"Project '{project_id}' was not found.",
                details={"project_id": project_id},
            )
        return self._geometry_repo.list_by_project(project_id)

    def read_geometry_bytes(
        self, geometry_id: str, *, prefer_repaired: bool = True
    ) -> tuple[GeometryAsset, bytes]:
        """Load stored STL bytes (repaired when available, otherwise raw)."""
        asset = self.get_geometry(geometry_id)
        key = (
            asset.repaired_artifact_key
            if prefer_repaired and asset.repaired_artifact_key is not None
            else asset.raw_artifact_key
        )
        return asset, self._storage.read_bytes(key)

    def _resolve_format(self, filename: str) -> GeometryFormat:
        suffix = Path(filename).suffix.lower().lstrip(".")
        if suffix == "stp":
            suffix = "step"
        supported = sorted(fmt.value for fmt in self._importer.supported_formats())
        if not suffix:
            raise UnsupportedFormatError(
                f"File '{filename}' has no extension. Supported formats: {supported}.",
                details={"filename": filename, "supported_formats": supported},
            )
        try:
            fmt = GeometryFormat(suffix)
        except ValueError as exc:
            raise UnsupportedFormatError(
                f"Format '.{suffix}' is not supported. Supported formats: {supported}.",
                details={"format": suffix, "supported_formats": supported},
            ) from exc

        if fmt not in self._importer.supported_formats():
            raise UnsupportedFormatError(
                f"Format '.{suffix}' is not enabled yet in this phase. "
                f"Currently supported formats: {supported}.",
                details={"format": fmt.value, "supported_formats": supported},
            )
        return fmt
