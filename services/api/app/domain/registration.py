"""The vocabularies P5's two new tables are constrained to.

Both exist because `tests/test_constraint_enum_parity.py` requires every
value-list `CHECK` to have a Python counterpart, in both directions. That rule
was written after `ck_chunk_review_state` and `ck_document_status` were each
found permitting a set no code could produce — two certain runtime failures that
survived because the SQL vocabulary and the Python one had nowhere to meet.

Declared here rather than beside the code that writes them because both are
written from more than one place: a run is queued at registration and moved on by
P11's engine, and a join request is created by one person and decided by another.
"""

from __future__ import annotations

from enum import StrEnum


class ResearchRunState(StrEnum):
    """Where a queued crawl has got to.

    `QUEUED` is the only value P5 writes — the engine is P11. The rest exist
    because a constraint that permitted only `queued` would have to be migrated
    the moment anything drained the queue, and a migration to widen a vocabulary
    is a migration whose only purpose is to catch up with code.
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class JoinRequestState(StrEnum):
    """`doc/11` Q8.

    `WITHDRAWN` is distinct from `DECLINED` on purpose: one is the requester
    changing their mind and the other is an Owner refusing them. Collapsing the
    two would make "were you turned down?" unanswerable, and that is the
    question a person asks.
    """

    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
