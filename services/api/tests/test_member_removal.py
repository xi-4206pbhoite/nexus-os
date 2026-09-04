"""Removing a member, and what happens to their uploads (Q71).

Two failure modes, both defensible in isolation and both wrong:

**Deleting** destroys company property because an employment relationship
ended — the contract they uploaded is the company's contract. **Silently
reassigning** makes the Owner the apparent uploader of files they have never
seen, and uploader-only chunks become readable by somebody the original uploader
never expected.

So the transfer happens *and* it is logged, and the log names who held them
before. That record exists to be questioned.
"""

from __future__ import annotations

from uuid import uuid4

from app.domain.membership_removal import Transfer, plan_removal


def test_documents_move_rather_than_being_deleted() -> None:
    """The contract they uploaded is the company's contract. Ending an
    employment relationship does not un-buy it."""
    member, owner = uuid4(), uuid4()
    docs = (uuid4(), uuid4())

    transfer = plan_removal(member_id=member, owner_id=owner, member_document_ids=docs)

    assert transfer is not None
    assert transfer.document_ids == docs
    assert transfer.to_user_id == owner


def test_the_transfer_names_who_held_them_before() -> None:
    """Silent reassignment makes the Owner the apparent uploader of files they
    have never seen. Somebody must be able to ask "why can the Owner see this?"
    and get an answer."""
    member, owner = uuid4(), uuid4()

    transfer = plan_removal(member_id=member, owner_id=owner, member_document_ids=(uuid4(),))

    assert transfer is not None
    assert transfer.from_user_id == member
    assert transfer.reason, "a transfer with no stated reason cannot be questioned"


def test_a_transfer_cannot_omit_its_previous_owner() -> None:
    import dataclasses

    required = {f.name for f in dataclasses.fields(Transfer) if f.default is dataclasses.MISSING}
    assert {"from_user_id", "to_user_id", "reason"} <= required


def test_a_member_who_uploaded_nothing_produces_no_transfer_row() -> None:
    """An empty transfer in the audit trail suggests documents moved when none
    did, and somebody reading it later would go looking for them."""
    assert plan_removal(member_id=uuid4(), owner_id=uuid4(), member_document_ids=()) is None
