"""Pydantic API schema exports."""

from __future__ import annotations

from topo_logic.interfaces.api.schemas.common import ErrorEnvelope, HealthResponse
from topo_logic.interfaces.api.schemas.geometries import (
    BoundingBoxResponse,
    GeometryAssetResponse,
    MeshDiagnosticsResponse,
    RepairReportResponse,
    ScaleGuardResponse,
)
from topo_logic.interfaces.api.schemas.jobs import JobResponse
from topo_logic.interfaces.api.schemas.materials import MaterialPresetResponse
from topo_logic.interfaces.api.schemas.meshes import (
    MeshGenerateRequest,
    MeshSurfaceResponse,
    VolumeMeshResponse,
)
from topo_logic.interfaces.api.schemas.projects import ProjectCreateRequest, ProjectResponse
from topo_logic.interfaces.api.schemas.studies import (
    BoundaryRegionSchema,
    BoundingBoxSelectorSchema,
    CadFaceTagSelectorSchema,
    EquilibriumCheckResponse,
    FemResultSummaryResponse,
    FemStudyCreateRequest,
    FieldStatsResponse,
    ForceLoadSchema,
    LoadCaseFemSummaryResponse,
    LoadCaseSchema,
    MaterialInputSchema,
    PlaneSelectorSchema,
    PressureLoadSchema,
    SupportBCSchema,
    TriangleSetSelectorSchema,
)

__all__ = [
    "BoundaryRegionSchema",
    "BoundingBoxResponse",
    "BoundingBoxSelectorSchema",
    "CadFaceTagSelectorSchema",
    "EquilibriumCheckResponse",
    "ErrorEnvelope",
    "FemResultSummaryResponse",
    "FemStudyCreateRequest",
    "FieldStatsResponse",
    "ForceLoadSchema",
    "GeometryAssetResponse",
    "HealthResponse",
    "JobResponse",
    "LoadCaseFemSummaryResponse",
    "LoadCaseSchema",
    "MaterialInputSchema",
    "MaterialPresetResponse",
    "MeshDiagnosticsResponse",
    "MeshGenerateRequest",
    "MeshSurfaceResponse",
    "PlaneSelectorSchema",
    "PressureLoadSchema",
    "ProjectCreateRequest",
    "ProjectResponse",
    "RepairReportResponse",
    "ScaleGuardResponse",
    "SupportBCSchema",
    "TriangleSetSelectorSchema",
    "VolumeMeshResponse",
]
