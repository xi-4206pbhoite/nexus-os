"""The three upload limits, all enforced server-side (Q36).

`doc/11` stage 5: **25 MB per file, 20 files at onboarding, 500 MB per
workspace.** Three different limits protecting three different things, and the
reason they are all here rather than in the browser is that a limit the client
enforces is a suggestion — the endpoint is reachable without the client, and the
one caller who bypasses it is the one the limit exists for.

Each refusal has to say **which** limit was hit and what the number is. "Upload
failed" makes a founder retry the same file; "this file is over 25 MB, split it"
tells them what to do instead. That is the same rule the parse failures already
follow in `OUTCOME_MESSAGE`.

The per-file limit was **50 MB** until this phase — twice what the spec says —
because it was set from `doc/01` M1 before `doc/11` settled it. Nothing failed:
a limit that is too generous refuses nothing, so no test could have caught it.
"""

from __future__ import annotations

import pytest

from app.documents.limits import (
    MAX_FILE_BYTES,
    MAX_FILES_AT_ONBOARDING,
    WORKSPACE_QUOTA_BYTES,
    LimitBreach,
    check_upload,
)

MB = 1024 * 1024


def test_the_three_limits_are_what_the_spec_says() -> None:
    """Q36's numbers, asserted as numbers.

    Worth a test precisely because it looks too simple for one: the per-file
    limit was wrong for a whole phase and no behavioural test could see it,
    because being too permissive refuses nothing.
    """
    assert MAX_FILE_BYTES == 25 * MB
    assert MAX_FILES_AT_ONBOARDING == 20
    assert WORKSPACE_QUOTA_BYTES == 500 * MB


def test_a_file_over_the_per_file_limit_is_refused_with_its_size() -> None:
    breach = check_upload(
        size_bytes=26 * MB, workspace_bytes_used=0, files_uploaded=0, onboarding=True
    )
    assert breach is LimitBreach.FILE_TOO_LARGE
    assert "25 MB" in breach.message


def test_a_file_at_the_limit_exactly_is_accepted() -> None:
    """Boundaries are inclusive, and the test says so out loud.

    A founder whose file is exactly 25 MB has met the limit they were told
    about, and an off-by-one here reads to them as the product lying."""
    assert (
        check_upload(size_bytes=25 * MB, workspace_bytes_used=0, files_uploaded=0, onboarding=True)
        is None
    )


def test_the_workspace_quota_counts_what_is_already_stored() -> None:
    """The quota is about the workspace, not the request.

    A 10 MB file is fine on its own and not fine as the 500th MB, so the check
    has to see what is already there — which is why it takes the total rather
    than deciding from the upload alone."""
    assert (
        check_upload(
            size_bytes=10 * MB,
            workspace_bytes_used=WORKSPACE_QUOTA_BYTES - 20 * MB,
            files_uploaded=0,
            onboarding=True,
        )
        is None
    )
    breach = check_upload(
        size_bytes=10 * MB,
        workspace_bytes_used=WORKSPACE_QUOTA_BYTES - 5 * MB,
        files_uploaded=0,
        onboarding=True,
    )
    assert breach is LimitBreach.WORKSPACE_FULL
    assert "500 MB" in breach.message


def test_the_file_count_limit_applies_to_onboarding_only() -> None:
    """Twenty files is a limit on *the onboarding flow*, not on the product.

    `doc/11` says "20 files **at onboarding**". A workspace that has finished
    onboarding and wants to upload its 21st document is doing the thing the
    product is for, and refusing it would turn a guard-rail against an
    overwhelming first session into a permanent cap nobody agreed to.
    """
    at_the_cap = {"size_bytes": 1 * MB, "workspace_bytes_used": 0, "files_uploaded": 20}
    breach = check_upload(**at_the_cap, onboarding=True)
    assert breach is LimitBreach.TOO_MANY_FILES
    assert "20" in breach.message

    assert check_upload(**at_the_cap, onboarding=False) is None


def test_every_breach_names_a_number_the_user_can_act_on() -> None:
    """A refusal without the limit in it makes the user retry the same file."""
    for breach in LimitBreach:
        assert any(ch.isdigit() for ch in breach.message), breach
        assert breach.message.endswith("."), breach


@pytest.mark.parametrize("size", [0, -1])
def test_a_non_positive_size_is_not_a_limit_question(size: int) -> None:
    """An empty file is refused earlier, with a different message. This checks
    the limits do not also claim it — two components refusing the same input
    for different stated reasons is how a user gets told something untrue."""
    assert (
        check_upload(size_bytes=size, workspace_bytes_used=0, files_uploaded=0, onboarding=True)
        is None
    )


def test_the_route_actually_consults_the_limits() -> None:
    """The functions above are pure and provable; this proves they are *wired*.

    Worth its own test because the failure it catches is invisible to every
    other one here: `check_upload` can be correct, fully covered, and never
    called. A limit that is computed and discarded refuses nothing, which is
    indistinguishable from a limit that is too generous — the exact shape of the
    50 MB constant this phase corrected.
    """
    from uuid import UUID, uuid4

    from fastapi.testclient import TestClient

    from app.deps import current_scope
    from app.domain.scopes import Department, Role
    from app.domain.session import ScopedSession
    from app.main import create_app
    from app.routes.documents import WorkspaceUsage, workspace_usage

    app = create_app()
    app.dependency_overrides[current_scope] = lambda: ScopedSession(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        workspace_id=UUID("22222222-2222-2222-2222-222222222222"),
        tenant_id=uuid4(),
        role=Role.OWNER,
        departments=frozenset({Department.FINANCE}),
    )
    # A workspace with 499 MB stored: the file below is fine on its own and is
    # not fine as the 500th MB, which is the whole point of a workspace quota.
    app.dependency_overrides[workspace_usage] = lambda: WorkspaceUsage(
        WORKSPACE_QUOTA_BYTES - 1 * MB, 1, True
    )

    with TestClient(app) as client:
        client.cookies.set("nexus_csrf", "a-known-csrf-value")
        response = client.post(
            "/documents",
            headers={"X-CSRF-Token": "a-known-csrf-value"},
            files={"file": ("prices.txt", b"x" * (2 * MB), "text/plain")},
            data={"consent": "true"},
        )

    assert response.status_code == 413, response.text
    assert "500 MB" in response.json()["detail"], "the refusal must name the limit that was hit"

    app.dependency_overrides.clear()
