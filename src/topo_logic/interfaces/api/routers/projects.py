"""Project CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from topo_logic.application.use_cases import ProjectService
from topo_logic.interfaces.api.dependencies import get_project_service
from topo_logic.interfaces.api.schemas import ProjectCreateRequest, ProjectResponse

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreateRequest,
    project_service: ProjectService = Depends(get_project_service),  # noqa: B008
) -> ProjectResponse:
    """Create a new Topo_Logic project workspace."""
    record = project_service.create_project(name=body.name, description=body.description)
    return ProjectResponse.from_domain(record)


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    project_service: ProjectService = Depends(get_project_service),  # noqa: B008
) -> list[ProjectResponse]:
    """List all projects."""
    return [ProjectResponse.from_domain(item) for item in project_service.list_projects()]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),  # noqa: B008
) -> ProjectResponse:
    """Fetch a single project by ID."""
    return ProjectResponse.from_domain(project_service.get_project(project_id))
