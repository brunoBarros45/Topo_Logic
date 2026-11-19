"""Project entities and simulation job state machine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from topo_logic.domain.exceptions import DomainValidationError, InvalidJobTransitionError
from topo_logic.domain.study import StudyType


class JobStatus(StrEnum):
    """Lifecycle states for asynchronous FEM and Topology Optimization jobs."""

    QUEUED = "queued"
    MESHING = "meshing"
    SOLVING = "solving"
    OPTIMIZING = "optimizing"
    RECONSTRUCTING = "reconstructing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
)

ALLOWED_JOB_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset(
        {
            JobStatus.MESHING,
            JobStatus.SOLVING,
            JobStatus.OPTIMIZING,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.MESHING: frozenset(
        {
            JobStatus.SOLVING,
            JobStatus.OPTIMIZING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.SOLVING: frozenset(
        {
            JobStatus.OPTIMIZING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.OPTIMIZING: frozenset(
        {
            JobStatus.RECONSTRUCTING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RECONSTRUCTING: frozenset(
        {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class ProjectRecord:
    """Top-level workspace container grouping geometries and simulation studies."""

    id: str
    name: str
    description: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise DomainValidationError("Project id must not be empty.")
        if not self.name.strip():
            raise DomainValidationError("Project name must not be empty.")


@dataclass(frozen=True)
class JobRecord:
    """Immutable state snapshot of a simulation job."""

    id: str
    project_id: str
    study_type: StudyType
    status: JobStatus
    progress: float
    message: str
    error_message: str | None
    result_artifact_key: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.project_id.strip():
            raise DomainValidationError("Job id and project_id must not be empty.")
        if not math.isfinite(self.progress) or not (0.0 <= self.progress <= 1.0):
            raise DomainValidationError(
                "Job progress must be within [0.0, 1.0].",
                details={"progress": self.progress},
            )

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_JOB_STATUSES

    def transition_to(
        self,
        new_status: JobStatus,
        *,
        progress: float | None = None,
        message: str | None = None,
        error_message: str | None = None,
        result_artifact_key: str | None = None,
    ) -> JobRecord:
        """Advance the job state machine while enforcing legal transitions."""
        allowed = ALLOWED_JOB_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidJobTransitionError(
                f"Cannot transition job '{self.id}' from '{self.status.value}' "
                f"to '{new_status.value}'.",
                details={
                    "job_id": self.id,
                    "current_status": self.status.value,
                    "target_status": new_status.value,
                },
            )

        next_progress = self.progress if progress is None else progress
        if new_status is JobStatus.COMPLETED and progress is None:
            next_progress = 1.0

        return JobRecord(
            id=self.id,
            project_id=self.project_id,
            study_type=self.study_type,
            status=new_status,
            progress=next_progress,
            message=self.message if message is None else message,
            error_message=self.error_message if error_message is None else error_message,
            result_artifact_key=(
                self.result_artifact_key if result_artifact_key is None else result_artifact_key
            ),
            created_at=self.created_at,
            updated_at=datetime.now(UTC),
        )
