"""The scheduler belongs to the worker, not to the API (`doc/12` P9).

Every API process used to run every job. With one container that is untidy;
with three behind a proxy it is three copies of every sweep — and because the
jobs are idempotent rather than exclusive, the symptom is triple the load and
**no error anybody sees**. That is the shape of defect this codebase keeps
finding, so the split gets a test rather than a comment.

The second reason is the one that will hurt later: the embedding pass runs on a
~2 GB model, and whichever process holds those weights must not be the one
answering requests.
"""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings


def test_the_scheduler_is_off_by_default() -> None:
    """Off unless asked for.

    Defaulting to on is what produced the original problem: nobody chose it for
    any particular process, it was simply what `create_app` did.
    """
    assert get_settings().run_scheduler is False


def test_the_api_does_not_start_a_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API container is `NEXUS_RUN_SCHEDULER=false`, and this proves the
    flag is actually consulted rather than merely declared."""
    import app.main

    built = False

    def build() -> None:
        nonlocal built
        built = True
        raise AssertionError("the API must not build a scheduler")

    monkeypatch.setattr("app.main.build_scheduler", build)

    from fastapi.testclient import TestClient

    with TestClient(app.main.create_app()):
        pass

    assert not built


def test_the_flag_is_what_turns_it_on() -> None:
    """`Settings` carries it, so the difference between the API container and
    the worker container is one environment variable and nothing else."""
    assert "run_scheduler" in Settings.model_fields


def test_the_worker_refuses_to_start_without_a_database() -> None:
    """A worker with no database runs no jobs. A container that looks healthy
    while doing nothing is worse than one that fails to start — the first is
    discovered weeks later when somebody asks why a sweep never ran."""
    import asyncio

    from app.worker import run

    with pytest.raises(RuntimeError, match="nothing to run"):
        asyncio.run(run())
