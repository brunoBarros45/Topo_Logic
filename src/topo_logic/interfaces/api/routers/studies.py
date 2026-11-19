"""Static FEM study submission, result summary, and binary Float32 field endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response, status

from topo_logic.application.use_cases import RunStaticFemUseCase
from topo_logic.domain.exceptions import ResourceNotFoundError
from topo_logic.domain.units import UnitSystem
from topo_logic.infrastructure.fem import extract_binary_field
from topo_logic.interfaces.api.dependencies import get_run_static_fem_use_case
from topo_logic.interfaces.api.schemas import (
    FemResultSummaryResponse,
    FemStudyCreateRequest,
    JobResponse,
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
