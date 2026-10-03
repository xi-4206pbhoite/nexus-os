"""Test configuration.

Tests must not read the developer's `.env`. Before this fixture existed they
did, and the suite's result changed the moment a real `NEXUS_DATABASE_URL` was
configured locally — readiness started returning 200 where the test expected
503. That is worse than a failing test: it means the suite passes or fails based
on machine state rather than on the code, and it would have passed in CI (no
`.env` there) while failing on the machine that wrote it.

Environment variables take precedence over the `.env` file in pydantic-settings,
so setting them empty here pins every test to a known-unconfigured baseline. A
test that wants a configured dependency opts in explicitly.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from tests.dburl import database_url

_PINNED = (
    "NEXUS_DATABASE_URL",
    "NEXUS_STORAGE_SIGNING_SECRET",
    # Omitted at first, and it showed: on a machine with a key in `.env` the
    # readiness probe reported `language_model: ok` during tests, so
    # `test_readiness_reports_the_language_model_but_never_gates_on_it` had to
    # accept either state to pass anywhere. That is the machine-state dependence
    # this fixture exists to remove. It also kept a live key reachable from the
    # suite, one careless test away from a billable call.
    "NEXUS_ANTHROPIC_API_KEY",
)


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture(autouse=True)
def hermetic_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    """Pin settings to a known baseline, independent of the local environment."""
    for key in _PINNED:
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("NEXUS_ENV", "ci")

    # Keep the storage probe out of the repo working tree.
    monkeypatch.setenv("NEXUS_STORAGE_ROOT", str(tmp_path_factory.mktemp("storage")))
    monkeypatch.setenv("NEXUS_MAIL_ROOT", str(tmp_path_factory.mktemp("mail")))

    _clear_caches()
    yield
    _clear_caches()


# ── The database contract ─────────────────────────────────────
#
# Nine test modules each carried their own
# `pytest.mark.skipif(DB_URL is None, ...)`. Nine copies meant nine places a DB
# suite could quietly vanish from a run, and the run still reported green: 92
# tests skipped, row-level security unproved, exit code 0. The whole point of
# `test_tenant_isolation.py` is that it *executes*.
#
# So the skip decision lives here, once, and it is paired with a guard that
# fails the session if it ever fires. `tests/test_ci_contract.py` asserts the
# other half — that a database is configured at all.

_skipped_requires_db: set[str] = set()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip `requires_db` tests only when no database is configured.

    With a database configured, nothing here fires and every marked test runs.
    Without one, `test_ci_contract.py::test_a_database_is_configured` fails, so
    the skips are never the only signal.
    """
    if database_url() is not None:
        return

    skip = pytest.mark.skip(
        reason="no database configured — see tests/test_ci_contract.py",
    )
    for item in items:
        if item.get_closest_marker("requires_db") is not None:
            item.add_marker(skip)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record any `requires_db` test that skipped, wherever the skip came from."""
    if report.skipped and "requires_db" in report.keywords:
        _skipped_requires_db.add(report.nodeid)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """A skipped database test fails the build. A silent skip proves nothing."""
    if not _skipped_requires_db:
        return

    sys.stderr.write(
        f"\nFAILED: {len(_skipped_requires_db)} requires_db test(s) were skipped. "
        "A database test that does not run proves nothing.\n"
    )
    for node_id in sorted(_skipped_requires_db):
        sys.stderr.write(f"  skipped: {node_id}\n")

    session.exitstatus = pytest.ExitCode.TESTS_FAILED
