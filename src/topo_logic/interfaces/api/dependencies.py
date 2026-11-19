"""Composition Root wiring Local-First infrastructure adapters into application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fastapi import HTTPException, Request, WebSocket, status

from topo_logic.application.use_cases import (
    GenerateMeshUseCase,
    IngestGeometryUseCase,
    JobService,
    ProjectService,
    RunStaticFemUseCase,
    RunTopOptUseCase,
)
from topo_logic.infrastructure.config import AppSettings
from topo_logic.infrastructure.execution import InMemoryEventBus, LocalJobQueue
from topo_logic.infrastructure.fem import StaticFemSolver
from topo_logic.infrastructure.mesh import (
    CompositeGeometryImporter,
    CompositeVolumetricMesher,
    GmshCliMesher,
    GmshStepImporter,
    TrimeshSurfaceImporter,
    TrimeshSurfaceRepairer,
    VoxelH8Mesher,
)
from topo_logic.infrastructure.storage import (
    LocalFsArtifactStorage,
    SqliteDatabase,
    SqliteGeometryRepository,
    SqliteJobRepository,
    SqliteMeshRepository,
    SqliteProjectRepository,
)
from topo_logic.infrastructure.topopt import (
    SimpTopologyOptimizer,
    WatertightStlReconstructor,
)


@dataclass(frozen=True)
class AppContainer:
    """Immutable dependency container stored on app.state during FastAPI lifespan."""

    settings: AppSettings
    database: SqliteDatabase
    storage: LocalFsArtifactStorage
    event_bus: InMemoryEventBus
    job_queue: LocalJobQueue
    project_service: ProjectService
    ingest_geometry: IngestGeometryUseCase
    generate_mesh: GenerateMeshUseCase
    run_static_fem: RunStaticFemUseCase
    run_topopt: RunTopOptUseCase
    job_service: JobService

    def shutdown(self) -> None:
        self.job_queue.shutdown(wait=True)
        self.database.close()


def build_container(settings: AppSettings) -> AppContainer:
    """Construct the Local-First runtime container (Composition Root)."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    database = SqliteDatabase(settings.db_path)
    storage = LocalFsArtifactStorage(settings.artifacts_dir)

    project_repo = SqliteProjectRepository(database)
    geometry_repo = SqliteGeometryRepository(database)
    mesh_repo = SqliteMeshRepository(database)
    job_repo = SqliteJobRepository(database)

    importer = CompositeGeometryImporter([TrimeshSurfaceImporter(), GmshStepImporter()])
    repairer = TrimeshSurfaceRepairer()
    mesher = CompositeVolumetricMesher([VoxelH8Mesher(), GmshCliMesher()])
    fem_solver = StaticFemSolver()
    topopt_optimizer = SimpTopologyOptimizer()
    surface_reconstructor = WatertightStlReconstructor()
    event_bus = InMemoryEventBus()
    job_queue = LocalJobQueue(max_workers=settings.max_workers)

    project_service = ProjectService(project_repo=project_repo)
    ingest_geometry = IngestGeometryUseCase(
        project_repo=project_repo,
        geometry_repo=geometry_repo,
        artifact_storage=storage,
        importer=importer,
        repairer=repairer,
    )
    generate_mesh = GenerateMeshUseCase(
        project_repo=project_repo,
        geometry_repo=geometry_repo,
        mesh_repo=mesh_repo,
        artifact_storage=storage,
        mesher=mesher,
    )
    job_service = JobService(
        project_repo=project_repo,
        job_repo=job_repo,
        event_publisher=event_bus,
        job_queue=job_queue,
    )
    run_static_fem = RunStaticFemUseCase(
        project_repo=project_repo,
        geometry_repo=geometry_repo,
        mesh_repo=mesh_repo,
        artifact_storage=storage,
        job_service=job_service,
        job_queue=job_queue,
        fem_solver=fem_solver,
    )
    run_topopt = RunTopOptUseCase(
        project_repo=project_repo,
        geometry_repo=geometry_repo,
        mesh_repo=mesh_repo,
        artifact_storage=storage,
        job_service=job_service,
        job_queue=job_queue,
        event_publisher=event_bus,
        optimizer=topopt_optimizer,
        reconstructor=surface_reconstructor,
    )
    return AppContainer(
        settings=settings,
        database=database,
        storage=storage,
        event_bus=event_bus,
        job_queue=job_queue,
        project_service=project_service,
        ingest_geometry=ingest_geometry,
        generate_mesh=generate_mesh,
        run_static_fem=run_static_fem,
        run_topopt=run_topopt,
        job_service=job_service,
    )


def get_container(request: Request) -> AppContainer:
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, AppContainer):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application container is not initialized.",
        )
    return container


def get_ws_container(websocket: WebSocket) -> AppContainer:
    return cast(AppContainer, websocket.app.state.container)


def get_settings(request: Request) -> AppSettings:
    return get_container(request).settings


def get_project_service(request: Request) -> ProjectService:
    return get_container(request).project_service


def get_ingest_geometry_use_case(request: Request) -> IngestGeometryUseCase:
    return get_container(request).ingest_geometry


def get_generate_mesh_use_case(request: Request) -> GenerateMeshUseCase:
    return get_container(request).generate_mesh


def get_run_static_fem_use_case(request: Request) -> RunStaticFemUseCase:
    return get_container(request).run_static_fem


def get_run_topopt_use_case(request: Request) -> RunTopOptUseCase:
    return get_container(request).run_topopt


def get_job_service(request: Request) -> JobService:
    return get_container(request).job_service
