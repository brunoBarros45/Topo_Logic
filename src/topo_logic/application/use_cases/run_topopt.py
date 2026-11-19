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
from topo_logic.domain.units import UnitSystem


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

        kg_factor = 1000.0 if study.fem_config.material.unit_system is UnitSystem.MM_N_MPA else 1.0
        original_mass_kg = mesh.total_volume * study.fem_config.material.density * kg_factor

        def _worker(token: CancellationToken) -> None:
            self._run_worker(
                job_id=job.id,
                project_id=project_id,
                mesh_id=mesh.id,
                mesh_artifact_key=mesh.artifact_key,
                original_mass_kg=original_mass_kg,
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

    def read_mesh_and_densities(self, job_id: str) -> tuple[TopOptResultSummary, bytes, bytes]:
        """Load summary, source H8 mesh payload, and packed densities for a completed TopOpt job."""
        summary, density_payload = self.read_density_payload(job_id)
        if summary.mesh_id is None:
            raise DomainValidationError(
                f"TopOpt job '{job_id}' does not have an associated volume mesh reference."
            )
        mesh = self._mesh_repo.get(summary.mesh_id)
        if mesh is None:
            raise ResourceNotFoundError(
                f"Volume mesh '{summary.mesh_id}' for job '{job_id}' was not found.",
                details={"job_id": job_id, "mesh_id": summary.mesh_id},
            )
        return summary, self._storage.read_bytes(mesh.artifact_key), density_payload

    def get_topopt_history(self, job_id: str) -> list[TopOptIterationEvent]:
        """Load per-iteration convergence telemetry for a completed TopOpt job."""
        summary = self.get_topopt_summary(job_id)
        if summary.history_artifact_key is None:
            return []
        raw = self._storage.read_bytes(summary.history_artifact_key)
        return _deserialize_topopt_history(raw)

    def _run_worker(
        self,
        *,
        job_id: str,
        project_id: str,
        mesh_id: str,
        mesh_artifact_key: str,
        original_mass_kg: float,
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
            history_events: list[TopOptIterationEvent] = []

            def _on_iteration(ev: TopOptIterationEvent) -> None:
                frac = min(1.0, float(ev.iteration) / float(study.max_iterations))
                strain_energy = 0.5 * ev.compliance
                remaining_mass_kg = original_mass_kg * ev.volume_fraction
                enriched = TopOptIterationEvent(
                    job_id=ev.job_id,
                    iteration=ev.iteration,
                    compliance=ev.compliance,
                    volume_fraction=ev.volume_fraction,
                    max_density_change=ev.max_density_change,
                    max_von_mises=ev.max_von_mises,
                    preview_artifact_key=ev.preview_artifact_key,
                    strain_energy=strain_energy,
                    remaining_mass_kg=remaining_mass_kg,
                )
                history_events.append(enriched)

                payload: dict[str, object] = {
                    "iteration": ev.iteration,
                    "compliance": ev.compliance,
                    "volume_fraction": ev.volume_fraction,
                    "max_density_change": ev.max_density_change,
                    "strain_energy": strain_energy,
                    "remaining_mass_kg": remaining_mass_kg,
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

            history_key = f"projects/{project_id}/jobs/{job_id}/topopt_history.json"
            stored_history_key = self._storage.save_bytes(
                history_key, _serialize_topopt_history(history_events)
            )

            summary = TopOptResultSummary(
                job_id=raw_summary.job_id,
                iterations_completed=raw_summary.iterations_completed,
                converged=raw_summary.converged,
                final_compliance=raw_summary.final_compliance,
                final_volume_fraction=raw_summary.final_volume_fraction,
                reconstructed_stl_key=stored_stl_key,
                density_field_key=stored_densities_key,
                weight_savings=raw_summary.weight_savings,
                mesh_id=mesh_id,
                history_artifact_key=stored_history_key,
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
        "mesh_id": summary.mesh_id,
        "history_artifact_key": summary.history_artifact_key,
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
    mesh_id_raw = data.get("mesh_id")
    history_raw = data.get("history_artifact_key")
    return TopOptResultSummary(
        job_id=str(data["job_id"]),
        iterations_completed=int(data["iterations_completed"]),
        converged=bool(data["converged"]),
        final_compliance=float(data["final_compliance"]),
        final_volume_fraction=float(data["final_volume_fraction"]),
        reconstructed_stl_key=str(data["reconstructed_stl_key"]),
        density_field_key=str(data["density_field_key"]),
        weight_savings=ws,
        mesh_id=str(mesh_id_raw) if mesh_id_raw is not None else None,
        history_artifact_key=str(history_raw) if history_raw is not None else None,
    )


def _serialize_topopt_history(events: list[TopOptIterationEvent]) -> bytes:
    items = [
        {
            "job_id": ev.job_id,
            "iteration": ev.iteration,
            "compliance": ev.compliance,
            "volume_fraction": ev.volume_fraction,
            "max_density_change": ev.max_density_change,
            "max_von_mises": ev.max_von_mises,
            "strain_energy": ev.strain_energy,
            "remaining_mass_kg": ev.remaining_mass_kg,
        }
        for ev in events
    ]
    return json.dumps(items).encode("utf-8")


def _deserialize_topopt_history(raw: bytes) -> list[TopOptIterationEvent]:
    items: list[dict[str, Any]] = json.loads(raw.decode("utf-8"))
    events: list[TopOptIterationEvent] = []
    for item in items:
        max_vm = item.get("max_von_mises")
        strain = item.get("strain_energy")
        mass_kg = item.get("remaining_mass_kg")
        events.append(
            TopOptIterationEvent(
                job_id=str(item["job_id"]),
                iteration=int(item["iteration"]),
                compliance=float(item["compliance"]),
                volume_fraction=float(item["volume_fraction"]),
                max_density_change=float(item["max_density_change"]),
                max_von_mises=float(max_vm) if max_vm is not None else None,
                strain_energy=float(strain) if strain is not None else None,
                remaining_mass_kg=float(mass_kg) if mass_kg is not None else None,
            )
        )
    return events
