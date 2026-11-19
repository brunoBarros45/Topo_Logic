"""Unit tests for Local-First persistence and background execution adapters."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from topo_logic.application.ports import CancellationToken, JobEvent
from topo_logic.domain import DomainValidationError, JobStatus, ResourceNotFoundError
from topo_logic.infrastructure.execution import InMemoryEventBus, LocalJobQueue
from topo_logic.infrastructure.storage import LocalFsArtifactStorage


@pytest.mark.unit
def test_local_fs_storage_atomic_write_and_path_traversal_guard(tmp_path: Path) -> None:
    storage = LocalFsArtifactStorage(tmp_path / "artifacts")
    key = storage.save_bytes("projects/p1/geometries/g1/repaired.stl", b"solid test\n")

    assert storage.exists(key) is True
    assert storage.read_bytes(key) == b"solid test\n"

    storage.delete(key)
    assert storage.exists(key) is False

    with pytest.raises(ResourceNotFoundError):
        storage.read_bytes(key)

    with pytest.raises(DomainValidationError):
        storage.save_bytes("../escape.stl", b"bad")

    with pytest.raises(DomainValidationError):
        storage.save_bytes("/abs/escape.stl", b"bad")

    with pytest.raises(DomainValidationError):
        storage.save_bytes("C:\\escape.stl", b"bad")

    with pytest.raises(DomainValidationError):
        storage.save_bytes("C:relative.stl", b"bad")

    with pytest.raises(DomainValidationError):
        storage.save_bytes("\\\\server\\share\\escape.stl", b"bad")


@pytest.mark.unit
async def test_event_bus_and_local_job_queue_cooperative_cancellation() -> None:
    bus = InMemoryEventBus()
    queue = LocalJobQueue(max_workers=1)
    started = threading.Event()
    observed_cancel = threading.Event()

    def _worker(token: CancellationToken) -> None:
        started.set()
        while not token.is_cancelled():
            threading.Event().wait(0.01)
        observed_cancel.set()
        bus.publish(
            JobEvent(
                job_id="job-cancel-1",
                event_type="job.cancelled",
                status=JobStatus.CANCELLED,
                progress=0.25,
                message="Worker cancelled cleanly.",
            )
        )

    try:
        async with bus.subscribe("job-cancel-1") as sub_queue:
            queue.submit("job-cancel-1", _worker)
            assert started.wait(timeout=2.0) is True
            assert queue.request_cancel("job-cancel-1") is True
            assert observed_cancel.wait(timeout=2.0) is True

            event = await asyncio.wait_for(sub_queue.get(), timeout=2.0)
            assert event is not None
            assert event.status is JobStatus.CANCELLED
            assert event.progress == 0.25
    finally:
        queue.shutdown(wait=True)
