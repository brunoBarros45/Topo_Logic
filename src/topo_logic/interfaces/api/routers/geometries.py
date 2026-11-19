"""3D geometry upload, diagnostics, repair, and artifact download endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from topo_logic.application.use_cases import IngestGeometryUseCase
from topo_logic.domain.units import AxisConvention, UnitSystem
from topo_logic.infrastructure.config import AppSettings
from topo_logic.interfaces.api.dependencies import (
    get_ingest_geometry_use_case,
    get_settings,
)
from topo_logic.interfaces.api.schemas import GeometryAssetResponse

router = APIRouter(prefix="/api/v1", tags=["geometries"])


@router.post(
    "/projects/{project_id}/geometries/upload",
    response_model=GeometryAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_geometry(
    project_id: str,
    file: UploadFile = File(...),  # noqa: B008
    unit_system: UnitSystem = Form(UnitSystem.MM_N_MPA),  # noqa: B008
    axis_convention: AxisConvention = Form(AxisConvention.Z_UP),  # noqa: B008
    auto_repair: bool = Form(True),
    settings: AppSettings = Depends(get_settings),  # noqa: B008
    ingest_use_case: IngestGeometryUseCase = Depends(get_ingest_geometry_use_case),  # noqa: B008
) -> GeometryAssetResponse:
    """Upload a 3D model (.STL in Phase 1), validate scale/topology, and repair surface."""
    max_bytes = settings.max_upload_bytes
    raw_bytes = await file.read(max_bytes + 1)
    if len(raw_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Uploaded file exceeds maximum allowed size of {settings.max_upload_mb} MB.",
        )

    asset = ingest_use_case.execute(
        project_id=project_id,
        filename=file.filename or "upload.stl",
        raw_bytes=raw_bytes,
        unit_system=unit_system,
        axis_convention=axis_convention,
        auto_repair=auto_repair,
    )
    return GeometryAssetResponse.from_domain(asset)


@router.get("/projects/{project_id}/geometries", response_model=list[GeometryAssetResponse])
def list_project_geometries(
    project_id: str,
    ingest_use_case: IngestGeometryUseCase = Depends(get_ingest_geometry_use_case),  # noqa: B008
) -> list[GeometryAssetResponse]:
    """List all geometries uploaded to a project."""
    assets = ingest_use_case.list_project_geometries(project_id)
    return [GeometryAssetResponse.from_domain(asset) for asset in assets]


@router.get("/geometries/{geometry_id}", response_model=GeometryAssetResponse)
def get_geometry(
    geometry_id: str,
    ingest_use_case: IngestGeometryUseCase = Depends(get_ingest_geometry_use_case),  # noqa: B008
) -> GeometryAssetResponse:
    """Retrieve diagnostics, scale guard report, and repair status for a geometry."""
    asset = ingest_use_case.get_geometry(geometry_id)
    return GeometryAssetResponse.from_domain(asset)


@router.get("/geometries/{geometry_id}/download")
def download_geometry(
    geometry_id: str,
    variant: Literal["repaired", "raw"] = "repaired",
    ingest_use_case: IngestGeometryUseCase = Depends(get_ingest_geometry_use_case),  # noqa: B008
) -> Response:
    """Download the canonical repaired binary STL or original uploaded geometry bytes."""
    asset, payload = ingest_use_case.read_geometry_bytes(
        geometry_id,
        prefer_repaired=(variant == "repaired"),
    )
    stem = Path(asset.filename).stem or "geometry"
    download_name = (
        f"{stem}_repaired.stl"
        if variant == "repaired" and asset.repaired_artifact_key is not None
        else asset.filename
    )
    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
