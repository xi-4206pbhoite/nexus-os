"""The suite must not depend on the developer's machine.

This is a regression guard. The health tests originally read the local `.env`,
so the moment a real database was configured they began failing — while still
passing in CI, which has no `.env`. A suite whose verdict depends on machine
state cannot be trusted to prove an invariant, and from M1 these tests are what
prove tenant isolation.
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings


def test_settings_are_pinned_regardless_of_local_env() -> None:
    settings = get_settings()
    assert settings.env.value == "ci"
    assert settings.database_url.get_secret_value() == ""
    assert settings.storage_signing_secret.get_secret_value() == ""


def test_storage_probe_does_not_write_into_the_repo() -> None:
    """A readiness probe must not leave artefacts in the working tree."""
    settings = get_settings()
    repo_root = Path(__file__).resolve().parents[3]
    assert not settings.storage_root.is_relative_to(repo_root)
    assert not settings.mail_root.is_relative_to(repo_root)


def test_required_secrets_fail_loudly_rather_than_defaulting() -> None:
    """A missing secret must raise, never silently run on a placeholder."""
    settings = get_settings()
    for name in ("database_url", "storage_signing_secret"):
        try:
            settings.require(name)
        except RuntimeError as exc:
            assert "not set" in str(exc)
        else:  # pragma: no cover - only reached on regression
            raise AssertionError(f"{name} should have raised when unset")
