"""In-memory job tracking for async RCA generation.

Each `JobRecord` represents one POST /rca call. Jobs are processed
sequentially (Semaphore=1) because a single Ollama LLM call already
saturates a CPU; submitting eight in parallel would just thrash and
extend wall-clock time.

This is intentionally simple: a process-local dict + asyncio primitives.
Restarting the agent loses job history, but the actual RCA artifacts
sit on disk under `reports/` and survive.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

log = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class JobRecord:
    id: str
    ticket_id: str
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    report_path: str | None = None
    error: str | None = None
    _task: asyncio.Task | None = field(default=None, repr=False, compare=False)


JobWork = Callable[[str], Awaitable[tuple[str | None, str | None]]]
"""A function that does the real work for one ticket.

It is given the ticket id and returns ``(report_path, error)``: exactly
one of the two is non-None.
"""


class JobStore:
    """Process-local job registry. Bounded by `max_records` (FIFO eviction)."""

    def __init__(self, *, concurrency: int = 1, max_records: int = 500) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(concurrency)
        self._max_records = max_records

    async def submit(self, ticket_id: str, work: JobWork) -> JobRecord:
        job = JobRecord(
            id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            status=JobStatus.QUEUED,
            submitted_at=datetime.now(UTC),
        )
        async with self._lock:
            self._jobs[job.id] = job
            self._evict_if_needed()
        job._task = asyncio.create_task(self._run(job, work))
        return job

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_recent(self, limit: int = 50) -> list[JobRecord]:
        async with self._lock:
            return list(self._jobs.values())[-limit:]

    # ----- internals -----------------------------------------------------

    async def _run(self, job: JobRecord, work: JobWork) -> None:
        # Mutating `job` here is safe without `_lock`: only this task ever
        # writes to its own JobRecord, and `get()` returns the same object —
        # readers see eventually-consistent fields, never a torn struct.
        async with self._semaphore:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(UTC)
            try:
                report_path, error = await work(job.ticket_id)
                if error:
                    job.status = JobStatus.FAILED
                    job.error = error
                else:
                    job.status = JobStatus.SUCCEEDED
                    job.report_path = report_path
            except Exception as exc:  # pragma: no cover — defensive
                log.exception("Job %s for ticket %s crashed", job.id, job.ticket_id)
                job.status = JobStatus.FAILED
                job.error = f"unhandled error: {exc}"
            finally:
                job.finished_at = datetime.now(UTC)

    def _evict_if_needed(self) -> None:
        # Caller already holds the lock.
        excess = len(self._jobs) - self._max_records
        if excess <= 0:
            return
        for old_id in list(self._jobs.keys())[:excess]:
            self._jobs.pop(old_id, None)
