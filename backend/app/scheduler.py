"""Dependency-free daily scheduler: an asyncio task started in the app lifespan
that periodically runs the maintenance jobs off the event loop thread.

Single-worker friendly (dev/MVP). For multi-worker production, run the scheduler
as a single dedicated process instead (or gate it to one worker).
"""

import asyncio
import logging

from app.config import settings
from app.db import SessionLocal
from app.services import scheduled_jobs

log = logging.getLogger("dawal.scheduler")

_task: asyncio.Task | None = None


def run_once() -> dict[str, int]:
    """Run all daily jobs in a fresh session (used by the loop)."""
    db = SessionLocal()
    try:
        counts = scheduled_jobs.run_daily_jobs(db)
        db.commit()
        return counts
    finally:
        db.close()


async def _loop(interval_seconds: float) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            counts = await asyncio.to_thread(run_once)
            log.info("scheduled jobs completed: %s", counts)
        except Exception:  # keep the loop alive across failures
            log.exception("scheduled job run failed")


def start() -> None:
    global _task
    if not settings.SCHEDULER_ENABLED:
        log.info("scheduler disabled (SCHEDULER_ENABLED=false)")
        return
    interval = settings.SCHEDULER_INTERVAL_HOURS * 3600
    _task = asyncio.create_task(_loop(interval))
    log.info("scheduler started (every %sh)", settings.SCHEDULER_INTERVAL_HOURS)


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
