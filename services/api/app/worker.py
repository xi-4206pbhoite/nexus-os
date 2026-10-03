"""The worker entrypoint. Same image as the API, different command.

`doc/12` P9: *remove the scheduler from the API process*. This is where it went.

**Why a separate process rather than a flag on the API.** Two reasons, and the
second is the one that will hurt:

- Every API process used to run every job. With one container that is untidy;
  with three behind a proxy it is three copies of every sweep. The jobs are
  idempotent rather than exclusive, so the symptom is triple the load and no
  error anybody sees — the worst shape of defect this codebase keeps finding.
- The embedding pass runs on a ~2 GB model. Once `[embeddings]` is installed,
  whichever process runs it holds those weights resident, and that must not be
  the process answering requests.

**No HTTP server here.** A worker that opens a port is a worker somebody will
eventually route traffic to. It runs the scheduler, waits, and shuts it down
cleanly on a signal — which matters because a sweep killed mid-transaction
leaves a connection open on a serverless Postgres billed by connection-time.
"""

from __future__ import annotations

import asyncio
import signal
from types import FrameType

from app.config import get_settings
from app.db import get_engine
from app.jobs.scheduler import build_scheduler
from app.logging import configure_logging, get_logger

log = get_logger(__name__)


async def run() -> None:
    configure_logging()
    settings = get_settings()

    if not settings.database_url.get_secret_value():
        # Refuse rather than idle. A worker with no database runs no jobs, and
        # a container that looks healthy while doing nothing is worse than one
        # that fails to start.
        raise RuntimeError("NEXUS_DATABASE_URL is not set; the worker has nothing to run.")

    scheduler = build_scheduler()
    scheduler.start()
    log.info("worker.started", jobs=[j.id for j in scheduler.get_jobs()])

    stopping = asyncio.Event()

    def stop(_signum: int, _frame: FrameType | None) -> None:
        # Set an event rather than shutting down here: the handler runs in the
        # signal context, and tearing down an event loop from inside one is how
        # a clean stop becomes a hang.
        stopping.set()

    for received in (signal.SIGTERM, signal.SIGINT):
        signal.signal(received, stop)

    try:
        await stopping.wait()
    finally:
        log.info("worker.stopping")
        scheduler.shutdown(wait=True)
        # The pool is closed explicitly. Letting the OS reap the connections
        # costs money on a database billed by connection-time, and leaves the
        # server holding them until its own timeout.
        await get_engine().dispose()
        log.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(run())
