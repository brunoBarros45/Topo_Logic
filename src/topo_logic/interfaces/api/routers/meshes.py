"""Volumetric meshing and indexed exterior surface endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from topo_logic.application.use_cases import GenerateMeshUseCase
from topo_logic.infrastructure.mesh import deserialize_volume_mesh, extract_surface_arrays
from topo_logic.interfaces.api.dependencies import get_generate_mesh_use_case
from topo_logic.interfaces.api.schemas import (
    MeshGenerateRequest,
    MeshSurfaceResponse,
    VolumeMeshResponse,
)

router = APIRouter(prefix="/api/v1", tags=["meshes"])


@router.post(
    "/projects/{project_id}/meshes",
    response_model=VolumeMeshResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_mesh(
    project_id: str,
    body: MeshGenerateRequest,
    generate_mesh_uc: GenerateMeshUseCase = Depends(get_generate_mesh_use_case),  # noqa: B008
) -> VolumeMeshResponse:
    """Generate a volumetric H8 (or Gmsh C3D4/C3D10) mesh from a watertight STL."""
    summary = generate_mesh_uc.execute(
        project_id=project_id,
        geometry_id=body.geometry_id,
        element_type=body.element_type,
        target_element_size=body.target_element_size,
    )
    return VolumeMeshResponse.from_domain(summary)


@router.get("/projects/{project_id}/meshes", response_model=list[VolumeMeshResponse])
def list_project_meshes(
    project_id: str,
    generate_mesh_uc: GenerateMeshUseCase = Depends(get_generate_mesh_use_case),  # noqa: B008
) -> list[VolumeMeshResponse]:
    """List all volumetric meshes belonging to a project."""
    return [
        VolumeMeshResponse.from_domain(item)
        for item in generate_mesh_uc.list_project_meshes(project_id)
    ]


@router.get("/meshes/{mesh_id}", response_model=VolumeMeshResponse)
def get_mesh(
    mesh_id: str,
    generate_mesh_uc: GenerateMeshUseCase = Depends(get_generate_mesh_use_case),  # noqa: B008
) -> VolumeMeshResponse:
    """Retrieve metadata for a volumetric mesh."""
    return VolumeMeshResponse.from_domain(generate_mesh_uc.get_mesh(mesh_id))


@router.get("/meshes/{mesh_id}/surface", response_model=MeshSurfaceResponse)
def get_mesh_surface(
    mesh_id: str,
    generate_mesh_uc: GenerateMeshUseCase = Depends(get_generate_mesh_use_case),  # noqa: B008
) -> MeshSurfaceResponse:
    """Serve exterior boundary triangles indexed to volume mesh nodes for viewport picking."""
    summary, raw_bytes = generate_mesh_uc.read_mesh_bytes(mesh_id)
    mesh_data = deserialize_volume_mesh(raw_bytes)
    nodes_f32, tris_i32 = extract_surface_arrays(mesh_data)
    return MeshSurfaceResponse(
        mesh_id=summary.id,
        element_type=summary.element_type,
        node_count=len(nodes_f32),
        surface_triangle_count=len(tris_i32),
        nodes=nodes_f32.tolist(),
        surface_triangles=tris_i32.tolist(),
    )
