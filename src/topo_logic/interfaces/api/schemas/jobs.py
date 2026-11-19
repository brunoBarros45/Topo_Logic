"""Pydantic schemas for asynchronous simulation job status and cancellation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from topo_logic.domain.jobs import JobRecord, JobStatus
from topo_logic.domain.study import StudyType


class JobResponse(BaseModel):
    """Serialized simulation job snapshot."""

    id: str
    project_id: str
    study_type: StudyType
    status: JobStatus
    progress: float
    message: str
    error_message: str | None = None
    has_result_artifact: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, job: JobRecord) -> JobResponse:
        return cls(
            id=job.id,
            project_id=job.project_id,
            study_type=job.study_type,
            status=job.status,
            progress=job.progress,
            message=job.message,
            error_message=job.error_message,
            has_result_artifact=job.result_artifact_key is not None,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
