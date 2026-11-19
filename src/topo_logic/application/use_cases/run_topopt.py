"""Use case for 3D SIMP Topology Optimization, live streaming, and watertight STL export."""

from __future__ import annotations

import json
from typing import Any

from topo_logic.application.ports.execution import (
    CancellationToken,
    EventPublisherPort,
    JobEvent,
    JobQueuePort,
)
from topo_logic.application.ports.persistence import (
    ArtifactStoragePort,
    GeometryRepositoryPort,
    MeshRepositoryPort,
    ProjectRepositoryPort,
)
from topo_logic.application.ports.simulation import OptimizerPort, SurfaceReconstructorPort
from topo_logic.application.use_cases.manage_jobs import JobService
from topo_logic.domain.exceptions import (
    DomainValidationError,
    InvalidJobTransitionError,
    JobCancelledError,
    ResourceNotFoundError,
)
from topo_logic.domain.geometry import ElementType
from topo_logic.domain.jobs import JobRecord, JobStatus
from topo_logic.domain.results import (
    TopOptIterationEvent,
    TopOptResultSummary,
    WeightSavingsMetrics,
)
from topo_logic.domain.study import StudyType, TopOptStudyConfig


class RunTopOptUseCase:
    """Orchestrates asynchronous 3D Topology Optimization and watertight STL reconstruction."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepositoryPort,
        geometry_repo: GeometryRepositoryPort,
        mesh_repo: MeshRepositoryPort,
        artifact_storage: ArtifactStoragePort,
        job_service: JobService,
        job_queue: JobQueuePort,
        event_publisher: EventPublisherPort,
        optimizer: OptimizerPort,
        reconstructor: SurfaceReconstructorPort,
    ) -> None:
        self._project_repo = project_repo
        self._geometry_repo = geometry_repo
        self._mesh_repo = mesh_repo
        self._storage = artifact_storage
        self._job_service = job_service
        self._job_queue = job_queue
        self._event_publisher = event_publisher
        self._optimizer = optimizer
        self._reconstructor = reconstructor

    def submit(
        self,
        *,
        project_id: str,
        mesh_id: str,
        study: TopOptStudyConfig,
    ) -> JobRecord:
        """Validate study configuration, enqueue TopOpt worker, and return JobRecord."""
        if self._project_repo.get(project_id) is None:
            raise ResourceNotFoundError(
                f"Project '{project_id}' was not found.",
                details={"project_id": project_id},
            )

        geom_id = study.fem_config.geometry_id
        geometry = self._geometry_repo.get(geom_id)
        if geometry is None or geometry.project_id != project_id:
            raise ResourceNotFoundError(
                f"Geometry '{geom_id}' was not found in project '{project_id}'.",
                details={"project_id": project_id, "geometry_id": geom_id},
            )

        mesh = self._mesh_repo.get(mesh_id)
        if mesh is None or mesh.project_id != project_id:
            raise ResourceNotFoundError(
                f"Volume mesh '{mesh_id}' was not found in project '{project_id}'.",
                details={"project_id": project_id, "mesh_id": mesh_id},
            )

        if mesh.geometry_id != geom_id:
            raise DomainValidationError(
                f"Volume mesh '{mesh_id}' belongs to geometry '{mesh.geometry_id}', "
                f"not '{geom_id}'."
            )

        if (
            mesh.element_type is not ElementType.H8
            or study.fem_config.element_type is not ElementType.H8
        ):
            raise DomainValidationError(
                "3D SIMP Topology Optimization currently requires structured H8 voxel meshes."
            )

        job = self._job_service.create_job(
            project_id=project_id,
            study_type=StudyType.TOPOLOGY_OPTIMIZATION,
            initial_message="Topology optimization job queued.",
        )

        def _worker(token: CancellationToken) -> None:
            self._run_worker(
                job_id=job.id,
                project_id=project_id,
                mesh_artifact_key=mesh.artifact_key,
                study=study,
                token=token,
            )

        self._job_queue.submit(job.id, _worker)
        return job

    def get_topopt_summary(self, job_id: str) -> TopOptResultSummary:
        """Load the persisted TopOptResultSummary for a completed TopOpt job."""
        job = self._job_service.get_job(job_id)
        if job.study_type is not StudyType.TOPOLOGY_OPTIMIZATION:
            raise DomainValidationError(
                f"Job '{job_id}' is of study_type '{job.study_type.value}', "
                "not topology_optimization."
            )
        if job.status is not JobStatus.COMPLETED or job.result_artifact_key is None:
            raise DomainValidationError(
                f"TopOpt summary is unavailable while job '{job_id}' has status "
                f"'{job.status.value}'.",
                details={"job_id": job_id, "status": job.status.value},
            )
        raw = self._storage.read_bytes(job.result_artifact_key)
        return _deserialize_topopt_summary(raw)

    def read_reconstructed_stl(self, job_id: str) -> bytes:
        """Load reconstructed watertight binary STL bytes for a completed TopOpt job."""
        summary = self.get_topopt_summary(job_id)
        return self._storage.read_bytes(summary.reconstructed_stl_key)

    def read_density_payload(self, job_id: str) -> tuple[TopOptResultSummary, bytes]:
        """Load summary and packed density archive for a completed TopOpt job."""
        summary = self.get_topopt_summary(job_id)
        return summary, self._storage.read_bytes(summary.density_field_key)

    def _run_worker(
        self,
        *,
        job_id: str,
        project_id: str,
        mesh_artifact_key: str,
        study: TopOptStudyConfig,
        token: CancellationToken,
    ) -> None:
        try:
            if token.is_cancelled():
                raise JobCancelledError("Topology optimization cancelled before start.")

            self._job_service.transition_job(
                job_id,
                JobStatus.OPTIMIZING,
                progress=0.05,
                message=f"Starting 3D SIMP optimization ({study.optimizer_kind.value.upper()})...",
            )

            mesh_bytes = self._storage.read_bytes(mesh_artifact_key)

            def _on_iteration(ev: TopOptIterationEvent) -> None:
                frac = min(1.0, float(ev.iteration) / float(study.max_iterations))
                payload: dict[str, object] = {
                    "iteration": ev.iteration,
                    "compliance": ev.compliance,
                    "volume_fraction": ev.volume_fraction,
                    "max_density_change": ev.max_density_change,
                }
                if ev.max_von_mises is not None:
                    payload["max_von_mises"] = ev.max_von_mises
                self._event_publisher.publish(
                    JobEvent(
                        job_id=job_id,
                        event_type="topopt.iteration",
                        status=JobStatus.OPTIMIZING,
                        progress=0.05 + 0.80 * frac,
                        message=f"Iteration {ev.iteration}/{study.max_iterations}",
                        payload=payload,
                    )
                )

            raw_summary, density_payload = self._optimizer.run_optimization(
                job_id=job_id,
                mesh_payload=mesh_bytes,
                study=study,
                cancellation_token=token,
                on_iteration=_on_iteration,
            )

            if token.is_cancelled():
                raise JobCancelledError("Topology optimization cancelled before reconstruction.")

            self._job_service.transition_job(
                job_id,
                JobStatus.RECONSTRUCTING,
                progress=0.90,
                message="Reconstructing watertight STL isosurface (Taubin smoothing)...",
            )

            reconstructed = self._reconstructor.reconstruct_watertight_stl(
                density_payload=density_payload,
                target_volume_fraction=study.target_volume_fraction,
            )

            densities_key = f"projects/{project_id}/jobs/{job_id}/densities.npz"
            stored_densities_key = self._storage.save_bytes(densities_key, density_payload)

            stl_key = f"projects/{project_id}/jobs/{job_id}/reconstructed.stl"
            stored_stl_key = self._storage.save_bytes(stl_key, reconstructed.stl_bytes)

            summary = TopOptResultSummary(
                job_id=raw_summary.job_id,
                iterations_completed=raw_summary.iterations_completed,
                converged=raw_summary.converged,
                final_compliance=raw_summary.final_compliance,
                final_volume_fraction=raw_summary.final_volume_fraction,
                reconstructed_stl_key=stored_stl_key,
                density_field_key=stored_densities_key,
                weight_savings=raw_summary.weight_savings,
            )
            summary_key = f"projects/{project_id}/jobs/{job_id}/topopt_summary.json"
            stored_summary_key = self._storage.save_bytes(
                summary_key, _serialize_topopt_summary(summary)
            )

            self._job_service.transition_job(
                job_id,
                JobStatus.COMPLETED,
                progress=1.0,
                message="3D Topology Optimization completed.",
                result_artifact_key=stored_summary_key,
            )
        except JobCancelledError:
            current = self._job_service.get_job(job_id)
            if not current.is_terminal:
                self._job_service.transition_job(
                    job_id,
                    JobStatus.CANCELLED,
                    message="Topology optimization cancelled.",
                )
        except InvalidJobTransitionError:
            return
        except Exception as exc:
            current = self._job_service.get_job(job_id)
            if not current.is_terminal:
                self._job_service.transition_job(
                    job_id,
                    JobStatus.FAILED,
                    message="3D Topology Optimization failed.",
                    error_message=str(exc),
                )


def _serialize_topopt_summary(summary: TopOptResultSummary) -> bytes:
    ws_payload: dict[str, object] | None = None
    if summary.weight_savings is not None:
        ws = summary.weight_savings
        ws_payload = {
            "original_mass_kg": ws.original_mass_kg,
            "optimized_mass_kg": ws.optimized_mass_kg,
            "mass_saved_kg": ws.mass_saved_kg,
            "original_mass_g": ws.original_mass_g,
            "optimized_mass_g": ws.optimized_mass_g,
            "mass_saved_g": ws.mass_saved_g,
            "mass_reduction_percent": ws.mass_reduction_percent,
        }

    payload: dict[str, Any] = {
        "job_id": summary.job_id,
        "iterations_completed": summary.iterations_completed,
        "converged": summary.converged,
        "final_compliance": summary.final_compliance,
        "final_volume_fraction": summary.final_volume_fraction,
        "reconstructed_stl_key": summary.reconstructed_stl_key,
        "density_field_key": summary.density_field_key,
        "weight_savings": ws_payload,
    }
    return json.dumps(payload).encode("utf-8")


def _deserialize_topopt_summary(raw: bytes) -> TopOptResultSummary:
    data: dict[str, Any] = json.loads(raw.decode("utf-8"))
    ws_raw = data.get("weight_savings")
    ws: WeightSavingsMetrics | None = None
    if isinstance(ws_raw, dict):
        ws = WeightSavingsMetrics(
            original_mass_kg=float(ws_raw["original_mass_kg"]),
            optimized_mass_kg=float(ws_raw["optimized_mass_kg"]),
            mass_saved_kg=float(ws_raw["mass_saved_kg"]),
            original_mass_g=float(ws_raw["original_mass_g"]),
            optimized_mass_g=float(ws_raw["optimized_mass_g"]),
            mass_saved_g=float(ws_raw["mass_saved_g"]),
            mass_reduction_percent=float(ws_raw["mass_reduction_percent"]),
        )
    return TopOptResultSummary(
        job_id=str(data["job_id"]),
        iterations_completed=int(data["iterations_completed"]),
        converged=bool(data["converged"]),
        final_compliance=float(data["final_compliance"]),
        final_volume_fraction=float(data["final_volume_fraction"]),
        reconstructed_stl_key=str(data["reconstructed_stl_key"]),
        density_field_key=str(data["density_field_key"]),
        weight_savings=ws,
    )
