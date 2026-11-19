"""Use case for executing multi-loadcase 3D linear static FEM studies."""

from __future__ import annotations

import json
from typing import Any

from topo_logic.application.ports.execution import CancellationToken, JobQueuePort
from topo_logic.application.ports.persistence import (
    ArtifactStoragePort,
    GeometryRepositoryPort,
    MeshRepositoryPort,
    ProjectRepositoryPort,
)
from topo_logic.application.ports.simulation import FemSolverPort
from topo_logic.application.use_cases.manage_jobs import JobService
from topo_logic.domain.exceptions import (
    DomainValidationError,
    InvalidJobTransitionError,
    JobCancelledError,
    ResourceNotFoundError,
)
from topo_logic.domain.jobs import JobRecord, JobStatus
from topo_logic.domain.results import (
    EquilibriumCheck,
    FemResultSummary,
    FieldStats,
    LoadCaseFemSummary,
)
from topo_logic.domain.study import FemStudyConfig, StudyType


class RunStaticFemUseCase:
    """Schedules and executes multi-loadcase 3D linear static FEM simulations."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepositoryPort,
        geometry_repo: GeometryRepositoryPort,
        mesh_repo: MeshRepositoryPort,
        artifact_storage: ArtifactStoragePort,
        job_service: JobService,
        job_queue: JobQueuePort,
        fem_solver: FemSolverPort,
    ) -> None:
        self._project_repo = project_repo
        self._geometry_repo = geometry_repo
        self._mesh_repo = mesh_repo
        self._storage = artifact_storage
        self._job_service = job_service
        self._job_queue = job_queue
        self._fem_solver = fem_solver

    def submit(
        self,
        *,
        project_id: str,
        mesh_id: str,
        study: FemStudyConfig,
    ) -> JobRecord:
        """Validate study inputs, enqueue background FEM solve, and return JobRecord."""
        if self._project_repo.get(project_id) is None:
            raise ResourceNotFoundError(
                f"Project '{project_id}' was not found.",
                details={"project_id": project_id},
            )

        geometry = self._geometry_repo.get(study.geometry_id)
        if geometry is None or geometry.project_id != project_id:
            raise ResourceNotFoundError(
                f"Geometry '{study.geometry_id}' was not found in project '{project_id}'.",
                details={"project_id": project_id, "geometry_id": study.geometry_id},
            )

        mesh = self._mesh_repo.get(mesh_id)
        if mesh is None or mesh.project_id != project_id:
            raise ResourceNotFoundError(
                f"Volume mesh '{mesh_id}' was not found in project '{project_id}'.",
                details={"project_id": project_id, "mesh_id": mesh_id},
            )

        if mesh.geometry_id != study.geometry_id:
            raise DomainValidationError(
                f"Volume mesh '{mesh_id}' belongs to geometry '{mesh.geometry_id}', "
                f"not '{study.geometry_id}'."
            )

        if mesh.element_type is not study.element_type:
            raise DomainValidationError(
                f"Mesh '{mesh_id}' uses element type '{mesh.element_type.value}', "
                f"which does not match study element type '{study.element_type.value}'."
            )

        job = self._job_service.create_job(
            project_id=project_id,
            study_type=StudyType.STATIC_FEM,
            initial_message="Static FEM study queued.",
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

    def execute_sync(
        self,
        *,
        job_id: str,
        mesh_bytes: bytes,
        study: FemStudyConfig,
        cancellation_token: CancellationToken,
    ) -> tuple[FemResultSummary, bytes]:
        """Execute a static FEM analysis directly in-process (benchmarks/CLI)."""
        return self._fem_solver.run_static_analysis(
            job_id=job_id,
            mesh_payload=mesh_bytes,
            study=study,
            cancellation_token=cancellation_token,
        )

    def get_fem_summary(self, job_id: str) -> FemResultSummary:
        """Load the persisted FemResultSummary for a completed static FEM job."""
        job = self._job_service.get_job(job_id)
        if job.study_type is not StudyType.STATIC_FEM:
            raise DomainValidationError(
                f"Job '{job_id}' is of study_type '{job.study_type.value}', not static_fem."
            )
        if job.status is not JobStatus.COMPLETED or job.result_artifact_key is None:
            raise DomainValidationError(
                f"FEM summary is unavailable while job '{job_id}' has status '{job.status.value}'.",
                details={"job_id": job_id, "status": job.status.value},
            )
        raw = self._storage.read_bytes(job.result_artifact_key)
        return _deserialize_fem_summary(raw)

    def read_fields_bundle(self, job_id: str) -> tuple[FemResultSummary, bytes]:
        """Load the summary and compressed binary Float32 fields archive for a completed job."""
        summary = self.get_fem_summary(job_id)
        return summary, self._storage.read_bytes(summary.fields_artifact_key)

    def _run_worker(
        self,
        *,
        job_id: str,
        project_id: str,
        mesh_artifact_key: str,
        study: FemStudyConfig,
        token: CancellationToken,
    ) -> None:
        try:
            if token.is_cancelled():
                raise JobCancelledError("FEM job cancelled before execution started.")

            self._job_service.transition_job(
                job_id,
                JobStatus.SOLVING,
                progress=0.15,
                message=f"Assembling and solving {len(study.load_cases)} load case(s)...",
            )

            mesh_bytes = self._storage.read_bytes(mesh_artifact_key)
            raw_summary, fields_bytes = self._fem_solver.run_static_analysis(
                job_id=job_id,
                mesh_payload=mesh_bytes,
                study=study,
                cancellation_token=token,
            )

            if token.is_cancelled():
                raise JobCancelledError("FEM job cancelled after solve.")

            fields_key = f"projects/{project_id}/jobs/{job_id}/fem_fields.npz"
            stored_fields_key = self._storage.save_bytes(fields_key, fields_bytes)

            summary = FemResultSummary(
                job_id=raw_summary.job_id,
                load_case_results=raw_summary.load_case_results,
                fields_artifact_key=stored_fields_key,
            )
            summary_key = f"projects/{project_id}/jobs/{job_id}/fem_summary.json"
            stored_summary_key = self._storage.save_bytes(
                summary_key, _serialize_fem_summary(summary)
            )

            self._job_service.transition_job(
                job_id,
                JobStatus.COMPLETED,
                progress=1.0,
                message="Linear static FEM analysis completed.",
                result_artifact_key=stored_summary_key,
            )
        except JobCancelledError:
            current = self._job_service.get_job(job_id)
            if not current.is_terminal:
                self._job_service.transition_job(
                    job_id,
                    JobStatus.CANCELLED,
                    message="FEM job cancelled.",
                )
        except InvalidJobTransitionError:
            # Already cancelled concurrently by the API caller
            return
        except Exception as exc:
            current = self._job_service.get_job(job_id)
            if not current.is_terminal:
                self._job_service.transition_job(
                    job_id,
                    JobStatus.FAILED,
                    message="Linear static FEM analysis failed.",
                    error_message=str(exc),
                )


def _serialize_fem_summary(summary: FemResultSummary) -> bytes:
    payload: dict[str, Any] = {
        "job_id": summary.job_id,
        "fields_artifact_key": summary.fields_artifact_key,
        "load_case_results": [
            {
                "load_case_id": lc.load_case_id,
                "compliance": lc.compliance,
                "min_safety_factor": lc.min_safety_factor,
                "displacement_stats": {
                    "min_value": lc.displacement_stats.min_value,
                    "max_value": lc.displacement_stats.max_value,
                    "mean_value": lc.displacement_stats.mean_value,
                    "unit": lc.displacement_stats.unit,
                },
                "von_mises_stats": {
                    "min_value": lc.von_mises_stats.min_value,
                    "max_value": lc.von_mises_stats.max_value,
                    "mean_value": lc.von_mises_stats.mean_value,
                    "unit": lc.von_mises_stats.unit,
                },
                "equilibrium": {
                    "force_residual_norm": lc.equilibrium.force_residual_norm,
                    "applied_force_norm": lc.equilibrium.applied_force_norm,
                    "relative_force_error": lc.equilibrium.relative_force_error,
                    "moment_residual_norm": lc.equilibrium.moment_residual_norm,
                    "is_balanced": lc.equilibrium.is_balanced,
                },
            }
            for lc in summary.load_case_results
        ],
    }
    return json.dumps(payload).encode("utf-8")


def _deserialize_fem_summary(raw: bytes) -> FemResultSummary:
    data: dict[str, Any] = json.loads(raw.decode("utf-8"))
    load_cases: list[LoadCaseFemSummary] = []
    for item in data["load_case_results"]:
        disp = item["displacement_stats"]
        vm = item["von_mises_stats"]
        eq = item["equilibrium"]
        load_cases.append(
            LoadCaseFemSummary(
                load_case_id=str(item["load_case_id"]),
                compliance=float(item["compliance"]),
                displacement_stats=FieldStats(
                    min_value=float(disp["min_value"]),
                    max_value=float(disp["max_value"]),
                    mean_value=float(disp["mean_value"]),
                    unit=str(disp["unit"]),
                ),
                von_mises_stats=FieldStats(
                    min_value=float(vm["min_value"]),
                    max_value=float(vm["max_value"]),
                    mean_value=float(vm["mean_value"]),
                    unit=str(vm["unit"]),
                ),
                min_safety_factor=float(item["min_safety_factor"]),
                equilibrium=EquilibriumCheck(
                    force_residual_norm=float(eq["force_residual_norm"]),
                    applied_force_norm=float(eq["applied_force_norm"]),
                    relative_force_error=float(eq["relative_force_error"]),
                    moment_residual_norm=float(eq["moment_residual_norm"]),
                    is_balanced=bool(eq["is_balanced"]),
                ),
            )
        )
    return FemResultSummary(
        job_id=str(data["job_id"]),
        load_case_results=tuple(load_cases),
        fields_artifact_key=str(data["fields_artifact_key"]),
    )
