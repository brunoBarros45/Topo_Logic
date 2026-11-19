"""Pydantic schemas for project endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from topo_logic.domain.jobs import ProjectRecord


class ProjectCreateRequest(BaseModel):
    """Payload to create a new engineering project."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class ProjectResponse(BaseModel):
    """Serialized project entity."""

    id: str
    name: str
    description: str
    created_at: datetime

    @classmethod
    def from_domain(cls, record: ProjectRecord) -> ProjectResponse:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            created_at=record.created_at,
        )
