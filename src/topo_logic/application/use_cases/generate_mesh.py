"""Use case for volumetric meshing of validated watertight 3D geometries."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from topo_logic.application.ports.geometry import VolumetricMesherPort
from topo_logic.application.ports.persistence import (
    ArtifactStoragePort,
    GeometryRepositoryPort,
    MeshRepositoryPort,
    ProjectRepositoryPort,
)
from topo_logic.domain.exceptions import (
    DomainValidationError,
    NonWatertightMeshError,
    ResourceNotFoundError,
)
from topo_logic.domain.geometry import ElementType, VolumeMeshSummary


class GenerateMeshUseCase:
    """Generates, validates, and persists volumetric FEM/TopOpt meshes."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepositoryPort,
        geometry_repo: GeometryRepositoryPort,
        mesh_repo: MeshRepositoryPort,
        artifact_storage: ArtifactStoragePort,
        mesher: VolumetricMesherPort,
    ) -> None:
        self._project_repo = project_repo
        self._geometry_repo = geometry_repo
        self._mesh_repo = mesh_repo
        self._storage = artifact_storage
        self._mesher = mesher

    def supported_elements(self) -> frozenset[ElementType]:
        """Return element formulations supported by the configured volumetric mesher."""
        return self._mesher.supported_elements()

    def execute(
        self,
        *,
        project_id: str,
        geometry_id: str,
        element_type: ElementType = ElementType.H8,
        target_element_size: float,
    ) -> VolumeMeshSummary:
        """Generate a volumetric mesh from a stored watertight STL geometry."""
        if self._project_repo.get(project_id) is None:
            raise ResourceNotFoundError(
                f"Project '{project_id}' was not found.",
                details={"project_id": project_id},
            )

        geometry = self._geometry_repo.get(geometry_id)
        if geometry is None or geometry.project_id != project_id:
            raise ResourceNotFoundError(
                f"Geometry '{geometry_id}' was not found in project '{project_id}'.",
                details={"project_id": project_id, "geometry_id": geometry_id},
            )

        if not geometry.diagnostics.is_watertight:
            raise NonWatertightMeshError(
                "Volumetric meshing requires a watertight surface mesh. "
                "Repair or upload a closed STL first.",
                details={
                    "geometry_id": geometry_id,
                    "boundary_edge_count": geometry.diagnostics.boundary_edge_count,
                },
            )

        if not math.isfinite(target_element_size) or target_element_size <= 0.0:
            raise DomainValidationError(
                "target_element_size must be a finite positive number.",
                details={"target_element_size": target_element_size},
            )

        source_key = (
            geometry.repaired_artifact_key
            if geometry.repaired_artifact_key is not None
            else geometry.raw_artifact_key
        )
        surface_bytes = self._storage.read_bytes(source_key)

        raw_summary, mesh_payload = self._mesher.generate_volume_mesh(
            surface_bytes,
            project_id=project_id,
            geometry_id=geometry_id,
            element_type=element_type,
            target_element_size=target_element_size,
        )

        artifact_key = f"projects/{project_id}/meshes/{raw_summary.id}/mesh.npz"
        stored_key = self._storage.save_bytes(artifact_key, mesh_payload)

        persisted_summary = VolumeMeshSummary(
            id=raw_summary.id,
            geometry_id=raw_summary.geometry_id,
            element_type=raw_summary.element_type,
            node_count=raw_summary.node_count,
            element_count=raw_summary.element_count,
            total_volume=raw_summary.total_volume,
            min_scaled_jacobian=raw_summary.min_scaled_jacobian,
            project_id=project_id,
            surface_triangle_count=raw_summary.surface_triangle_count,
            artifact_key=stored_key,
            created_at=datetime.now(UTC),
        )
        self._mesh_repo.save(persisted_summary)
        return persisted_summary

    def get_mesh(self, mesh_id: str) -> VolumeMeshSummary:
        """Fetch mesh metadata by ID or raise ResourceNotFoundError."""
        mesh = self._mesh_repo.get(mesh_id)
        if mesh is None:
            raise ResourceNotFoundError(
                f"Volume mesh '{mesh_id}' was not found.",
                details={"mesh_id": mesh_id},
            )
        return mesh

    def list_project_meshes(self, project_id: str) -> list[VolumeMeshSummary]:
        """List all volumetric meshes belonging to a project."""
        if self._project_repo.get(project_id) is None:
            raise ResourceNotFoundError(
                f"Project '{project_id}' was not found.",
                details={"project_id": project_id},
            )
        return self._mesh_repo.list_by_project(project_id)

    def read_mesh_bytes(self, mesh_id: str) -> tuple[VolumeMeshSummary, bytes]:
        """Load the compressed serialized volume mesh artifact."""
        summary = self.get_mesh(mesh_id)
        if not summary.artifact_key:
            raise ResourceNotFoundError(
                f"Volume mesh '{mesh_id}' has no stored mesh artifact.",
                details={"mesh_id": mesh_id},
            )
        return summary, self._storage.read_bytes(summary.artifact_key)
