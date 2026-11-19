"""Ports for asynchronous execution, event streaming, and cooperative cancellation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from topo_logic.domain.jobs import JobStatus


@dataclass(frozen=True)
class JobEvent:
    """Lightweight event emitted by background simulation jobs for WebSocket streaming."""

    job_id: str
    event_type: str
    status: JobStatus
    progress: float
    message: str
    payload: dict[str, object] = field(default_factory=dict)


class CancellationToken(Protocol):
    """Cooperative cancellation handle checked between solver/optimizer iterations."""

    def is_cancelled(self) -> bool:
        """Return True if cancellation was requested for the current job."""
        ...

    def cancel(self) -> None:
        """Signal cancellation to the running worker."""
        ...


class EventPublisherPort(Protocol):
    """Pub/sub port decoupling job progress emission from WebSocket/SSE transport."""

    def publish(self, event: JobEvent) -> None:
        """Broadcast a job progress or iteration event to subscribers."""
        ...


class JobQueuePort(Protocol):
    """Background worker execution queue port (Local process pool -> Celery/Redis)."""

    def submit(self, job_id: str, task: Callable[[CancellationToken], None]) -> None:
        """Schedule a job task for non-blocking background execution."""
        ...

    def request_cancel(self, job_id: str) -> bool:
        """Request cooperative cancellation for a running or queued job."""
        ...
