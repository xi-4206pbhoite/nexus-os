"""The three upload limits, in one place, as pure functions.

`doc/11` stage 5 (Q36): **25 MB per file, 20 files at onboarding, 500 MB per
workspace.** Three limits protecting three different things — one oversized
file, one overwhelming first session, and one workspace's share of the disk.

Pure and side-effect free so the rule is testable without a database and
reusable by anything that needs to *predict* a refusal — the upload UI shows
what is left before a founder picks a file, and it must agree with the server
exactly. Two implementations of one limit is how a client says "fine" and the
server says "too big" about the same file.

**Server-side is the point.** A limit the browser enforces is a suggestion: the
endpoint is reachable without the browser, and the one caller who skips it is
the caller the limit exists for.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

MB: Final = 1024 * 1024

MAX_FILE_BYTES: Final = 25 * MB
"""Per file. Was 50 MB — `doc/01` M1's number, left behind when `doc/11`
settled on 25. Nothing failed, because a limit that is too generous refuses
nothing and no test can see it."""

MAX_FILES_AT_ONBOARDING: Final = 20
"""Onboarding only. A guard-rail against an overwhelming first session, not a
cap on the product: a workspace that has finished onboarding and wants its 21st
document is doing the thing NEXUS is for."""

WORKSPACE_QUOTA_BYTES: Final = 500 * MB
"""Per workspace, counting what is already stored — a 10 MB file is fine on its
own and not fine as the 500th MB."""


class LimitBreach(StrEnum):
    """Which limit was hit. The message names the number, always.

    A refusal the user cannot act on makes them retry the same file. "This file
    is over 25 MB, split it" tells them what to do instead — the same rule the
    parse failures already follow in `OUTCOME_MESSAGE`.
    """

    FILE_TOO_LARGE = "file_too_large"
    TOO_MANY_FILES = "too_many_files"
    WORKSPACE_FULL = "workspace_full"

    @property
    def message(self) -> str:
        return _MESSAGE[self]


_MESSAGE: Final[dict[LimitBreach, str]] = {
    LimitBreach.FILE_TOO_LARGE: (
        f"This file is over {MAX_FILE_BYTES // MB} MB. Split it and upload the parts."
    ),
    LimitBreach.TOO_MANY_FILES: (
        f"That is {MAX_FILES_AT_ONBOARDING} files, which is as many as onboarding takes. "
        "Finish setting up and you can add the rest with no limit on how many."
    ),
    LimitBreach.WORKSPACE_FULL: (
        f"This workspace holds {WORKSPACE_QUOTA_BYTES // MB} MB of documents and is full. "
        "Remove something you no longer need, or talk to us about more room."
    ),
}


def check_upload(
    *,
    size_bytes: int,
    workspace_bytes_used: int,
    files_uploaded: int,
    onboarding: bool,
) -> LimitBreach | None:
    """The first limit this upload breaks, or `None`.

    Order matters: the per-file limit is checked first because it is the one the
    founder can act on immediately, and being told "the workspace is full" about
    a file that was never going to fit anyway sends them to delete things they
    did not need to.

    A non-positive size is **not** a limit question. An empty file is refused
    earlier with its own message, and two components refusing one input for
    different stated reasons is how a user gets told something untrue.
    """
    if size_bytes <= 0:
        return None

    if size_bytes > MAX_FILE_BYTES:
        return LimitBreach.FILE_TOO_LARGE

    if onboarding and files_uploaded >= MAX_FILES_AT_ONBOARDING:
        return LimitBreach.TOO_MANY_FILES

    if workspace_bytes_used + size_bytes > WORKSPACE_QUOTA_BYTES:
        return LimitBreach.WORKSPACE_FULL

    return None
