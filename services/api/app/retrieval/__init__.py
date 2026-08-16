"""The only path to workspace data.

**I2** — identity is bound to the session, never passed as an argument.
**I3** — the permission predicate is part of the query, never a post-filter.

Every function in this package takes a `ScopedSession` as its first parameter
and **never** takes a `user_id`, `workspace_id` or `role`. That is not a
convention: `tests/test_retrieval_signatures.py` inspects every public signature
here and fails the build on a violation. The reason is doc 06 §4.3 — a model
whose context contains a crawled competitor page is one injected line away from
requesting another user's scope, if scope is something a caller can pass.

Enforcement is at the data-access layer, not in a hook. Doc 06 §4.4 rule 4: a
hook is configured per process, so any path that bypasses the orchestrator — a
scheduled job, a retry worker, a second service — would be unfiltered.
"""

from app.retrieval.scoped import scoped_connection

__all__ = ["scoped_connection"]
