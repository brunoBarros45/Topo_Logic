"""Health and capability discovery endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from topo_logic import __version__
from topo_logic.application.use_cases import IngestGeometryUseCase
from topo_logic.interfaces.api.dependencies import get_ingest_geometry_use_case
from topo_logic.interfaces.api.schemas import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(
    ingest_use_case: IngestGeometryUseCase = Depends(get_ingest_geometry_use_case),  # noqa: B008
) -> HealthResponse:
    """Return service status, version, execution mode, and enabled 3D file formats."""
    supported = sorted(fmt.value for fmt in ingest_use_case.supported_formats())
    return HealthResponse(
        status="ok",
        version=__version__,
        execution_mode="local_first",
        supported_formats=supported,
    )
