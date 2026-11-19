"""FastAPI application factory, middleware, lifespan, and domain error mapping."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from topo_logic import __version__
from topo_logic.domain.exceptions import (
    DomainValidationError,
    InvalidGeometryError,
    InvalidJobTransitionError,
    NonWatertightMeshError,
    ResourceNotFoundError,
    TopoLogicError,
    UnderconstrainedModelError,
    UnsupportedFormatError,
)
from topo_logic.infrastructure.config import AppSettings
from topo_logic.interfaces.api.dependencies import AppContainer, build_container
from topo_logic.interfaces.api.routers import (
    geometries,
    health,
    jobs,
    materials,
    meshes,
    projects,
    studies,
)
from topo_logic.interfaces.api.schemas import ErrorEnvelope


def _register_domain_exception_handlers(app: FastAPI) -> None:
    status_map: list[tuple[type[TopoLogicError], int]] = [
        (ResourceNotFoundError, status.HTTP_404_NOT_FOUND),
        (UnsupportedFormatError, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
        (InvalidJobTransitionError, status.HTTP_409_CONFLICT),
        (InvalidGeometryError, status.HTTP_422_UNPROCESSABLE_CONTENT),
        (NonWatertightMeshError, status.HTTP_422_UNPROCESSABLE_CONTENT),
        (UnderconstrainedModelError, status.HTTP_422_UNPROCESSABLE_CONTENT),
        (DomainValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT),
        (TopoLogicError, status.HTTP_400_BAD_REQUEST),
    ]

    for exc_type, http_status in status_map:
        app.add_exception_handler(exc_type, _make_error_handler(http_status))


def _make_error_handler(
    http_status: int,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def _handler(_request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, TopoLogicError):
            envelope = ErrorEnvelope(code=exc.code, message=exc.message, details=exc.details)
        else:
            envelope = ErrorEnvelope(code="internal_error", message=str(exc), details={})
        return JSONResponse(status_code=http_status, content=envelope.model_dump())

    return _handler


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create a configured FastAPI application instance."""
    resolved_settings = settings or AppSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container: AppContainer = build_container(resolved_settings)
        app.state.container = container
        try:
            yield
        finally:
            container.shutdown()

    app = FastAPI(
        title="Topo_Logic API",
        description="Open-source 3D Finite Element Analysis (FEM) and Topology Optimization API.",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Topo-Dtype",
            "X-Topo-Shape",
            "X-Topo-Voxel-Shape",
            "X-Topo-Unit",
            "X-Topo-Min",
            "X-Topo-Max",
            "Content-Disposition",
        ],
    )

    _register_domain_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(materials.router)
    app.include_router(projects.router)
    app.include_router(geometries.router)
    app.include_router(meshes.router)
    app.include_router(studies.router)
    app.include_router(jobs.router)
    return app
