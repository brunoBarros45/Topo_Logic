"""Ports for artifact blob storage and metadata repositories."""

from __future__ import annotations

from typing import Protocol

from topo_logic.domain.geometry import GeometryAsset, VolumeMeshSummary
from topo_logic.domain.jobs import JobRecord, ProjectRecord


class ArtifactStoragePort(Protocol):
    """Binary artifact storage port (Local filesystem -> S3/MinIO)."""

    def save_bytes(self, key: str, data: bytes) -> str:
        """Persist raw bytes under the logical artifact key and return stored key."""
        ...

    def read_bytes(self, key: str) -> bytes:
        """Read artifact bytes for the given logical key."""
        ...

    def exists(self, key: str) -> bool:
        """Check whether an artifact exists for the given key."""
        ...

    def delete(self, key: str) -> None:
        """Remove an artifact if present."""
        ...


class ProjectRepositoryPort(Protocol):
    """Persistence port for Project entities."""

    def save(self, project: ProjectRecord) -> None:
        ...

    def get(self, project_id: str) -> ProjectRecord | None:
        ...

    def list_all(self) -> list[ProjectRecord]:
        ...


class GeometryRepositoryPort(Protocol):
    """Persistence port for GeometryAsset entities."""

    def save(self, asset: GeometryAsset) -> None:
        ...

    def get(self, geometry_id: str) -> GeometryAsset | None:
        ...

    def list_by_project(self, project_id: str) -> list[GeometryAsset]:
        ...


class JobRepositoryPort(Protocol):
    """Persistence port for JobRecord state snapshots."""

    def save(self, job: JobRecord) -> None:
        ...

    def get(self, job_id: str) -> JobRecord | None:
        ...

    def list_by_project(self, project_id: str) -> list[JobRecord]:
        ...


class MeshRepositoryPort(Protocol):
    """Persistence port for generated volumetric mesh summaries."""

    def save(self, mesh: VolumeMeshSummary) -> None:
        ...

    def get(self, mesh_id: str) -> VolumeMeshSummary | None:
        ...

    def list_by_project(self, project_id: str) -> list[VolumeMeshSummary]:
        ...
