"""Simulation job query, cancellation, and WebSocket event stream endpoints."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from topo_logic.application.use_cases import JobService
from topo_logic.domain.exceptions import ResourceNotFoundError
from topo_logic.domain.jobs import TERMINAL_JOB_STATUSES
from topo_logic.interfaces.api.dependencies import get_job_service, get_ws_container
from topo_logic.interfaces.api.schemas import JobResponse

router = APIRouter(tags=["jobs"])


@router.get("/api/v1/projects/{project_id}/jobs", response_model=list[JobResponse])
def list_project_jobs(
    project_id: str,
    job_service: JobService = Depends(get_job_service),  # noqa: B008
) -> list[JobResponse]:
    """List simulation jobs for a project."""
    return [JobResponse.from_domain(job) for job in job_service.list_project_jobs(project_id)]


@router.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    job_service: JobService = Depends(get_job_service),  # noqa: B008
) -> JobResponse:
    """Retrieve the current status and progress of a simulation job."""
    return JobResponse.from_domain(job_service.get_job(job_id))


@router.post("/api/v1/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(
    job_id: str,
    job_service: JobService = Depends(get_job_service),  # noqa: B008
) -> JobResponse:
    """Request cooperative cancellation for a queued or active job."""
    return JobResponse.from_domain(job_service.cancel_job(job_id))


@router.websocket("/ws/jobs/{job_id}")
async def job_events_websocket(websocket: WebSocket, job_id: str) -> None:
    """Stream real-time simulation progress and iteration events for a job."""
    await websocket.accept()
    container = get_ws_container(websocket)
    job_service = container.job_service
    event_bus = container.event_bus

    try:
        snapshot = job_service.get_job(job_id)
    except ResourceNotFoundError as exc:
        await websocket.send_json(
            {"event_type": "error", "code": exc.code, "message": exc.message}
        )
        await websocket.close(code=1008)
        return

    await websocket.send_json(
        {
            "event_type": "job.snapshot",
            "job_id": snapshot.id,
            "status": snapshot.status.value,
            "progress": snapshot.progress,
            "message": snapshot.message,
            "payload": {
                "study_type": snapshot.study_type.value,
                "updated_at": snapshot.updated_at.isoformat(),
            },
        }
    )

    if snapshot.is_terminal:
        await websocket.close(code=1000)
        return

    async with event_bus.subscribe(job_id) as queue:
        recv_task: asyncio.Task[object] = asyncio.create_task(websocket.receive())
        try:
            while True:
                queue_task = asyncio.create_task(queue.get())
                done, _pending = await asyncio.wait(
                    {queue_task, recv_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if recv_task in done:
                    queue_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await queue_task
                    msg = recv_task.result()
                    if isinstance(msg, dict) and msg.get("type") == "websocket.disconnect":
                        break
                    recv_task = asyncio.create_task(websocket.receive())

                if queue_task in done:
                    event = queue_task.result()
                    if event is None:
                        break
                    await websocket.send_json(
                        {
                            "event_type": event.event_type,
                            "job_id": event.job_id,
                            "status": event.status.value,
                            "progress": event.progress,
                            "message": event.message,
                            "payload": event.payload,
                        }
                    )
                    if event.status in TERMINAL_JOB_STATUSES:
                        await websocket.close(code=1000)
                        break
        except WebSocketDisconnect:
            pass
        finally:
            if not recv_task.done():
                recv_task.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await recv_task
