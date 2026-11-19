"""Pure domain exception hierarchy for Topo_Logic."""

from __future__ import annotations


class TopoLogicError(Exception):
    """Base exception for all Topo_Logic domain and application errors."""

    default_code: str = "topo_logic_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.details: dict[str, object] = dict(details) if details is not None else {}


class DomainValidationError(TopoLogicError):
    """Raised when a domain entity or value object violates an engineering invariant."""

    default_code = "domain_validation_error"


class UnsupportedFormatError(TopoLogicError):
    """Raised when a geometry file format is not supported by the active importer."""

    default_code = "unsupported_format"


class InvalidGeometryError(TopoLogicError):
    """Raised when an uploaded 3D model is empty, corrupted, or geometrically degenerate."""

    default_code = "invalid_geometry"


class NonWatertightMeshError(TopoLogicError):
    """Raised when a watertight closed surface is required but the mesh has open boundaries."""

    default_code = "non_watertight_mesh"


class UnderconstrainedModelError(TopoLogicError):
    """Raised when Dirichlet supports fail to restrain rigid-body modes in 3D."""

    default_code = "underconstrained_model"


class InvalidJobTransitionError(TopoLogicError):
    """Raised on an illegal simulation job state transition."""

    default_code = "invalid_job_transition"


class ResourceNotFoundError(TopoLogicError):
    """Raised when a requested project, geometry, or job record does not exist."""

    default_code = "resource_not_found"


class JobCancelledError(TopoLogicError):
    """Raised when a background job observes cooperative cancellation."""

    default_code = "job_cancelled"
