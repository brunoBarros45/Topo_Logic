"""In-memory event pub/sub, threading cancellation token, and worker pool queue."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager

from topo_logic.application.ports.execution import CancellationToken, JobEvent


class ThreadingCancellationToken:
    """Thread-safe cooperative cancellation token backed by threading.Event."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


class InMemoryEventBus:
    """Local-First EventPublisherPort routing job events to active asyncio subscribers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[
            str,
            set[tuple[asyncio.Queue[JobEvent | None], asyncio.AbstractEventLoop]],
        ] = {}

    def publish(self, event: JobEvent) -> None:
        with self._lock:
            targets = list(self._subscribers.get(event.job_id, ()))

        for queue, loop in targets:
            if not loop.is_closed():
                loop.call_soon_threadsafe(queue.put_nowait, event)

    @asynccontextmanager
    async def subscribe(self, job_id: str) -> AsyncIterator[asyncio.Queue[JobEvent | None]]:
        queue: asyncio.Queue[JobEvent | None] = asyncio.Queue()
        entry = (queue, asyncio.get_running_loop())
        with self._lock:
            self._subscribers.setdefault(job_id, set()).add(entry)
        try:
            yield queue
        finally:
            with self._lock:
                subs = self._subscribers.get(job_id)
                if subs is not None:
                    subs.discard(entry)
                    if not subs:
                        self._subscribers.pop(job_id, None)


class LocalJobQueue:
    """Local worker pool JobQueuePort supporting cooperative cancellation."""

    def __init__(self, *, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="topologic")
        self._lock = threading.Lock()
        self._tokens: dict[str, ThreadingCancellationToken] = {}
        self._futures: dict[str, Future[None]] = {}

    def submit(self, job_id: str, task: Callable[[CancellationToken], None]) -> None:
        token = ThreadingCancellationToken()

        def _runner() -> None:
            try:
                task(token)
            finally:
                with self._lock:
                    self._tokens.pop(job_id, None)
                    self._futures.pop(job_id, None)

        with self._lock:
            self._tokens[job_id] = token
            self._futures[job_id] = self._executor.submit(_runner)

    def request_cancel(self, job_id: str) -> bool:
        with self._lock:
            token = self._tokens.get(job_id)
            if token is None:
                return False
            token.cancel()
            return True

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            for token in self._tokens.values():
                token.cancel()
        self._executor.shutdown(wait=wait)
