"""The research engine — fetching and reading a public website.

Formerly the machinery behind the unauthenticated Preview audit. The audit was
retired in Phase 2 (`doc/11` Q1); the engine was not, because it is what the
authenticated research runs in Phase 11 are built on.

**Nothing here is reachable without a session, and that is checked rather than
intended** — `tests/test_no_unauthenticated_crawl.py` walks the import graph
from every anonymous route and fails if one can reach the crawler. The reason
is the reason the audit was retired: a server-side fetch of a user-supplied
address, offered to anyone, means a stranger can point NEXUS at a company they
do not own and be handed an analysis of it.

`app/calculators/audit.py` is deliberately **not** here. It scores the signals
this package extracts, and I1 keeps every calculation in one place.
"""
