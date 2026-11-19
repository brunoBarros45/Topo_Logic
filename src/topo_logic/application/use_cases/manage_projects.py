"""Use cases for creating and querying engineering projects."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from topo_logic.application.ports.persistence import ProjectRepositoryPort
from topo_logic.domain.exceptions import ResourceNotFoundError
from topo_logic.domain.jobs import ProjectRecord


class ProjectService:
    """Application service coordinating project lifecycle operations."""

    def __init__(self, project_repo: ProjectRepositoryPort) -> None:
        self._project_repo = project_repo

    def create_project(self, *, name: str, description: str = "") -> ProjectRecord:
        """Create and persist a new workspace project."""
        project = ProjectRecord(
            id=str(uuid.uuid4()),
            name=name.strip(),
            description=description.strip(),
            created_at=datetime.now(UTC),
        )
        self._project_repo.save(project)
        return project

    def get_project(self, project_id: str) -> ProjectRecord:
        """Retrieve a project by ID or raise ResourceNotFoundError."""
        project = self._project_repo.get(project_id)
        if project is None:
            raise ResourceNotFoundError(
                f"Project '{project_id}' was not found.",
                details={"project_id": project_id},
            )
        return project

    def list_projects(self) -> list[ProjectRecord]:
        """Return all persisted projects ordered by creation timestamp."""
        return self._project_repo.list_all()
