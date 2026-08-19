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

from collections.abc import Iterator

import pytest

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.embedding.registry import get_embedder

_PINNED = (
    "NEXUS_DATABASE_URL",
    "NEXUS_SESSION_SECRET",
    "NEXUS_STORAGE_SIGNING_SECRET",
)


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    # The embedder is process-wide and chosen from settings, so a test that
    # selects a backend would otherwise leak it into every test after it.
    get_embedder.cache_clear()


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

    # No embedder unless a test asks for one. `fastembed` would download ~1.1 GB
    # of weights on first use, which a test suite must never do implicitly.
    monkeypatch.setenv("NEXUS_EMBEDDING_BACKEND", "none")

    _clear_caches()
    yield
    _clear_caches()
