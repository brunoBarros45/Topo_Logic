"""Common Pydantic v2 API response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    """Standardized error envelope returned by all API endpoints."""

    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Service health and capability metadata (used by Web UI and Fusion 360 client)."""

    status: str
    version: str
    execution_mode: str
    supported_formats: list[str]
