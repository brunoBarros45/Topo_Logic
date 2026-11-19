"""Static FEM study submission, result summary, and binary Float32 field endpoints."""

from __future__ import annotations

import io
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, Response, status

from topo_logic.application.use_cases import RunStaticFemUseCase, RunTopOptUseCase
from topo_logic.domain.exceptions import ResourceNotFoundError
from topo_logic.domain.units import UnitSystem
from topo_logic.infrastructure.exporters import (
    export_fem_surface_vtp,
    export_fem_volume_vtu,
    export_stl_to_glb,
    export_topopt_densities_vti,
    extract_load_case_fields,
)
from topo_logic.infrastructure.fem import extract_binary_field
from topo_logic.infrastructure.mesh import deserialize_volume_mesh
from topo_logic.infrastructure.topopt import extract_binary_densities
from topo_logic.interfaces.api.dependencies import (
    get_run_static_fem_use_case,
    get_run_topopt_use_case,
)
from topo_logic.interfaces.api.schemas import (
    FemResultSummaryResponse,
    FemStudyCreateRequest,
    JobResponse,
    TopOptHistoryResponse,
    TopOptIterationPointResponse,
    TopOptResultSummaryResponse,
    TopOptStudyCreateRequest,
)

router = APIRouter(prefix="/api/v1", tags=["studies"])


@router.post(
    "/projects/{project_id}/studies/fem",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_fem_study(
    project_id: str,
    body: FemStudyCreateRequest,
    run_fem_uc: RunStaticFemUseCase = Depends(get_run_static_fem_use_case),  # noqa: B008
) -> JobResponse:
    """Submit an asynchronous multi-loadcase 3D linear static FEM study."""
    study = body.to_domain()
    job = run_fem_uc.submit(
        project_id=project_id,
        mesh_id=body.mesh_id,
        study=study,
    )
    return JobResponse.from_domain(job)


@router.get("/jobs/{job_id}/fem-summary", response_model=FemResultSummaryResponse)
def get_fem_summary(
    job_id: str,
    run_fem_uc: RunStaticFemUseCase = Depends(get_run_static_fem_use_case),  # noqa: B008
) -> FemResultSummaryResponse:
    """Retrieve post-processed stress, displacement, safety factor, and equilibrium summaries."""
    summary = run_fem_uc.get_fem_summary(job_id)
    return FemResultSummaryResponse.from_domain(summary)


@router.get("/jobs/{job_id}/fields/{load_case_id}")
def download_fem_field(
    job_id: str,
    load_case_id: str,
    field: Literal[
        "displacement", "displacement_magnitude", "von_mises", "safety_factor"
    ] = "von_mises",
    run_fem_uc: RunStaticFemUseCase = Depends(get_run_static_fem_use_case),  # noqa: B008
) -> Response:
    """Download packed little-endian Float32 nodal field arrays for client GPU colormaps."""
    summary, bundle_bytes = run_fem_uc.read_fields_bundle(job_id)
    is_mm = bool(
        summary.load_case_results
        and summary.load_case_results[0].displacement_stats.unit == "mm"
    )
    unit_system = UnitSystem.MM_N_MPA if is_mm else UnitSystem.M_N_PA
    try:
        raw_bytes, headers = extract_binary_field(
            bundle_bytes,
            load_case_id=load_case_id,
            field_name=field,
            unit_system=unit_system,
        )
    except KeyError as exc:
        raise ResourceNotFoundError(
            f"Field '{field}' for load case '{load_case_id}' was not found on job '{job_id}'.",
            details={"job_id": job_id, "load_case_id": load_case_id, "field": field},
        ) from exc

    return Response(
        content=raw_bytes,
        media_type="application/octet-stream",
        headers=headers,
    )


@router.post(
    "/projects/{project_id}/studies/topopt",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_topopt_study(
    project_id: str,
    body: TopOptStudyCreateRequest,
    run_topopt_uc: RunTopOptUseCase = Depends(get_run_topopt_use_case),  # noqa: B008
) -> JobResponse:
    """Submit an asynchronous 3D SIMP Topology Optimization study (OC or MMA)."""
    study = body.to_domain()
    job = run_topopt_uc.submit(
        project_id=project_id,
        mesh_id=body.mesh_id,
        study=study,
    )
    return JobResponse.from_domain(job)


@router.get("/jobs/{job_id}/topopt-summary", response_model=TopOptResultSummaryResponse)
def get_topopt_summary(
    job_id: str,
    run_topopt_uc: RunTopOptUseCase = Depends(get_run_topopt_use_case),  # noqa: B008
) -> TopOptResultSummaryResponse:
    """Retrieve final compliance, volume fraction, and mass savings summary."""
    summary = run_topopt_uc.get_topopt_summary(job_id)
    return TopOptResultSummaryResponse.from_domain(summary)


@router.get("/jobs/{job_id}/reconstructed-stl")
def download_reconstructed_stl(
    job_id: str,
    run_topopt_uc: RunTopOptUseCase = Depends(get_run_topopt_use_case),  # noqa: B008
) -> Response:
    """Download the reconstructed watertight Taubin-smoothed STL mesh."""
    stl_bytes = run_topopt_uc.read_reconstructed_stl(job_id)
    return Response(
        content=stl_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="topopt_{job_id}.stl"'},
    )


@router.get("/jobs/{job_id}/densities")
def download_topopt_densities(
    job_id: str,
    run_topopt_uc: RunTopOptUseCase = Depends(get_run_topopt_use_case),  # noqa: B008
) -> Response:
    """Download packed little-endian Float32 physical element densities."""
    _summary, density_payload = run_topopt_uc.read_density_payload(job_id)
    raw_bytes, headers = extract_binary_densities(density_payload)
    return Response(
        content=raw_bytes,
        media_type="application/octet-stream",
        headers=headers,
    )


@router.get("/jobs/{job_id}/fem-results/{load_case_id}.vtp")
def download_fem_surface_vtp(
    job_id: str,
    load_case_id: str,
    run_fem_uc: RunStaticFemUseCase = Depends(get_run_static_fem_use_case),  # noqa: B008
) -> Response:
    """Download exterior boundary surface with FEM fields as VTK XML PolyData (.vtp)."""
    _summary, mesh_bytes, bundle_bytes = run_fem_uc.read_mesh_and_fields(job_id)
    try:
        fields = extract_load_case_fields(bundle_bytes, load_case_id)
    except KeyError as exc:
        raise ResourceNotFoundError(
            f"FEM results for load case '{load_case_id}' were not found on job '{job_id}'.",
            details={"job_id": job_id, "load_case_id": load_case_id},
        ) from exc
    mesh_data = deserialize_volume_mesh(mesh_bytes)
    vtp_bytes = export_fem_surface_vtp(mesh_data, fields)
    return Response(
        content=vtp_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="fem_{job_id}_{load_case_id}.vtp"'
        },
    )


@router.get("/jobs/{job_id}/fem-results/{load_case_id}.vtu")
def download_fem_volume_vtu(
    job_id: str,
    load_case_id: str,
    run_fem_uc: RunStaticFemUseCase = Depends(get_run_static_fem_use_case),  # noqa: B008
) -> Response:
    """Download full volumetric FEM mesh + nodal fields as VTK UnstructuredGrid (.vtu)."""
    _summary, mesh_bytes, bundle_bytes = run_fem_uc.read_mesh_and_fields(job_id)
    try:
        fields = extract_load_case_fields(bundle_bytes, load_case_id)
    except KeyError as exc:
        raise ResourceNotFoundError(
            f"FEM results for load case '{load_case_id}' were not found on job '{job_id}'.",
            details={"job_id": job_id, "load_case_id": load_case_id},
        ) from exc
    mesh_data = deserialize_volume_mesh(mesh_bytes)
    vtu_bytes = export_fem_volume_vtu(mesh_data, point_fields=fields)
    return Response(
        content=vtu_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="fem_{job_id}_{load_case_id}.vtu"'
        },
    )


@router.get("/jobs/{job_id}/topopt-history", response_model=TopOptHistoryResponse)
def get_topopt_history(
    job_id: str,
    run_topopt_uc: RunTopOptUseCase = Depends(get_run_topopt_use_case),  # noqa: B008
) -> TopOptHistoryResponse:
    """Retrieve per-iteration TopOpt convergence telemetry for Recharts plots."""
    events = run_topopt_uc.get_topopt_history(job_id)
    return TopOptHistoryResponse(
        job_id=job_id,
        points=[TopOptIterationPointResponse.from_domain(ev) for ev in events],
    )


@router.get("/jobs/{job_id}/topopt-densities.vti")
def download_topopt_densities_vti(
    job_id: str,
    run_topopt_uc: RunTopOptUseCase = Depends(get_run_topopt_use_case),  # noqa: B008
) -> Response:
    """Download TopOpt density voxel grid (1-voxel zero halo) as VTK ImageData (.vti)."""
    _summary, density_payload = run_topopt_uc.read_density_payload(job_id)
    vti_bytes = export_topopt_densities_vti(density_payload)
    return Response(
        content=vti_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="topopt_{job_id}_densities.vti"'},
    )


@router.get("/jobs/{job_id}/topopt-results.vtu")
def download_topopt_results_vtu(
    job_id: str,
    run_topopt_uc: RunTopOptUseCase = Depends(get_run_topopt_use_case),  # noqa: B008
) -> Response:
    """Download full volumetric H8 mesh + element densities as VTK UnstructuredGrid (.vtu)."""
    _summary, mesh_bytes, density_payload = run_topopt_uc.read_mesh_and_densities(job_id)
    mesh_data = deserialize_volume_mesh(mesh_bytes)
    with np.load(io.BytesIO(density_payload), allow_pickle=False) as archive:
        densities_phys = np.asarray(archive["densities_phys"], dtype="<f4")
        densities_raw = np.asarray(archive["densities_raw"], dtype="<f4")
    vtu_bytes = export_fem_volume_vtu(
        mesh_data,
        cell_fields={"density": densities_phys, "density_raw": densities_raw},
    )
    return Response(
        content=vtu_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="topopt_{job_id}_results.vtu"'},
    )


@router.get("/jobs/{job_id}/reconstructed.glb")
def download_reconstructed_glb(
    job_id: str,
    run_topopt_uc: RunTopOptUseCase = Depends(get_run_topopt_use_case),  # noqa: B008
) -> Response:
    """Download reconstructed watertight TopOpt surface as binary glTF 2.0 (.glb)."""
    stl_bytes = run_topopt_uc.read_reconstructed_stl(job_id)
    glb_bytes = export_stl_to_glb(stl_bytes)
    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f'inline; filename="topopt_{job_id}.glb"'},
    )
