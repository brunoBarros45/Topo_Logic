"""Use cases for simulation job lifecycle management and cooperative cancellation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from topo_logic.application.ports.execution import EventPublisherPort, JobEvent, JobQueuePort
from topo_logic.application.ports.persistence import JobRepositoryPort, ProjectRepositoryPort
from topo_logic.domain.exceptions import ResourceNotFoundError
from topo_logic.domain.jobs import JobRecord, JobStatus
from topo_logic.domain.study import StudyType


class JobService:
    """Coordinates simulation job persistence, state transitions, and event streaming."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepositoryPort,
        job_repo: JobRepositoryPort,
        event_publisher: EventPublisherPort,
        job_queue: JobQueuePort,
    ) -> None:
        self._project_repo = project_repo
        self._job_repo = job_repo
        self._event_publisher = event_publisher
        self._job_queue = job_queue

    def create_job(
        self,
        *,
        project_id: str,
        study_type: StudyType,
        initial_message: str = "Job queued.",
    ) -> JobRecord:
        """Create and persist a queued simulation job."""
        if self._project_repo.get(project_id) is None:
            raise ResourceNotFoundError(
                f"Project '{project_id}' was not found.",
                details={"project_id": project_id},
            )

        now = datetime.now(UTC)
        job = JobRecord(
            id=str(uuid.uuid4()),
            project_id=project_id,
            study_type=study_type,
            status=JobStatus.QUEUED,
            progress=0.0,
            message=initial_message,
            error_message=None,
            result_artifact_key=None,
            created_at=now,
            updated_at=now,
        )
        self._job_repo.save(job)
        self._publish(job, event_type="job.queued")
        return job

    def get_job(self, job_id: str) -> JobRecord:
        """Retrieve a job by ID or raise ResourceNotFoundError."""
        job = self._job_repo.get(job_id)
        if job is None:
            raise ResourceNotFoundError(
                f"Job '{job_id}' was not found.",
                details={"job_id": job_id},
            )
        return job

    def list_project_jobs(self, project_id: str) -> list[JobRecord]:
        """List all jobs belonging to a project."""
        if self._project_repo.get(project_id) is None:
            raise ResourceNotFoundError(
                f"Project '{project_id}' was not found.",
                details={"project_id": project_id},
            )
        return self._job_repo.list_by_project(project_id)

    def transition_job(
        self,
        job_id: str,
        new_status: JobStatus,
        *,
        progress: float | None = None,
        message: str | None = None,
        error_message: str | None = None,
        result_artifact_key: str | None = None,
    ) -> JobRecord:
        """Transition a job to a new state, persist it, and publish a status event."""
        current = self.get_job(job_id)
        updated = current.transition_to(
            new_status,
            progress=progress,
            message=message,
            error_message=error_message,
            result_artifact_key=result_artifact_key,
        )
        self._job_repo.save(updated)
        self._publish(updated, event_type=f"job.{new_status.value}")
        return updated

    def cancel_job(self, job_id: str) -> JobRecord:
        """Signal cooperative cancellation and transition non-terminal jobs to CANCELLED."""
        current = self.get_job(job_id)
        if current.is_terminal:
            return current

        self._job_queue.request_cancel(job_id)
        cancelled = current.transition_to(
            JobStatus.CANCELLED,
            message="Cancellation requested by user.",
        )
        self._job_repo.save(cancelled)
        self._publish(cancelled, event_type="job.cancelled")
        return cancelled

    def _publish(self, job: JobRecord, *, event_type: str) -> None:
        self._event_publisher.publish(
            JobEvent(
                job_id=job.id,
                event_type=event_type,
                status=job.status,
                progress=job.progress,
                message=job.message,
                payload={
                    "study_type": job.study_type.value,
                    "updated_at": job.updated_at.isoformat(),
                },
            )
        )
