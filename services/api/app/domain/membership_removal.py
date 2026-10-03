"""Removing a member, and what happens to what they uploaded (Q71).

**Never silent reassignment, never silent deletion.** Both are defensible in
isolation and both are wrong here, for opposite reasons:

- **Deleting** their documents destroys company property because an employment
  relationship ended. The contract they uploaded is the company's contract.
- **Silently reassigning** them makes the Owner the apparent uploader of files
  they have never seen, and `uploader-only` chunks become readable by somebody
  the original uploader never expected to read them.

So the transfer happens *and* it is logged, with the previous owner named. The
audit row is the part that makes it honest: somebody can ask "why can the Owner
see this?" and get an answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Transfer:
    """What moved, from whom, to whom. Every field required.

    A transfer that cannot say who held the documents before is a transfer
    nobody can question — and this record exists precisely to be questioned.
    """

    document_ids: tuple[UUID, ...]
    from_user_id: UUID
    to_user_id: UUID
    reason: str

    @property
    def is_empty(self) -> bool:
        return not self.document_ids


def plan_removal(
    *, member_id: UUID, owner_id: UUID, member_document_ids: tuple[UUID, ...]
) -> Transfer | None:
    """What to do with a departing member's uploads.

    `None` when they uploaded nothing — and that is a real case worth
    distinguishing, because an empty transfer row in the audit trail suggests
    documents moved when none did, and somebody reading it later would go
    looking for them.

    **Removing yourself is refused elsewhere**, not here: this function answers
    what happens to the files, and an owner removing the last owner is a
    different question with a different answer.
    """
    if not member_document_ids:
        return None

    return Transfer(
        document_ids=member_document_ids,
        from_user_id=member_id,
        to_user_id=owner_id,
        reason=(
            "The person who uploaded these left the workspace. Ownership moved to "
            "the workspace owner so the company keeps its own documents."
        ),
    )
