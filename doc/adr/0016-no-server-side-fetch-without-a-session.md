# ADR 0016 — The crawl engine moves behind authentication, and a test keeps it there

**Status** Accepted
**Date** 2026-09-03
**Decided by** Phase 2, executing `doc/11` Q1 (D18). The removal was Parul's
decision; the shape of the boundary that replaces it is this ADR.

## Context

`POST /preview` audited any website a visitor typed, with no account. Its own
docstring named the risk exactly:

> Anyone can type a competitor's URL, and without that limit NEXUS would crawl a
> company the requester does not own, name its competitors, and hand that to a
> stranger — a competitive-intelligence product sold by accident.

The mitigation was a **reduced** audit: brand, performance and technical SEO
only, no competitor discovery, no keyword data, a 24-hour TTL, three rate limits
and a deletion path for the crawled company. All of it real, all of it working,
and all of it answering the wrong question. The scope limit made the leak
smaller. It did not make the endpoint something a stranger should have.

`doc/11` Q1 removed the entry point. That leaves the question this ADR settles:
the engine is 1,100 lines of guard, crawler, extractor and calculator that P11
needs — where does it live, and what stops the next unauthenticated caller
reaching it?

## Decision

### 1. The engine lives in `app/research/`, and the calculator does not

`ssrf.py`, `crawler.py` and `extract.py` moved out of `app/connectors/` into a
new `app/research/`. `app/connectors/` keeps `domain_check.py` and
`rate_limit.py` — neither belongs to research.

`app/calculators/audit.py` deliberately **stayed**. It scores the signals the
extractor produces, and I1 says every calculation lives in one place. Moving it
would have put a calculator outside `calculators/` for the sake of grouping
things that are used together, which is the weaker organising principle.

The move is a rename, not a rewrite. `tests/test_ssrf_guard.py` (89 cases),
`tests/test_audit_calculators.py` (29) and `tests/test_crawler_redirects.py`
(18) pass from the new location with **only their import lines changed** — six
lines across three files, no assertion touched. That was the acceptance
condition in the phase brief: *"if a single one needs editing, the move was
wrong."*

### 2. The invariant is asserted structurally, not intended

`tests/test_no_unauthenticated_crawl.py` walks the import graph from every route
that declares no session dependency and fails if any of them can reach the crawl
engine, at any depth.

It replaces `test_preview_scope.py`, which asserted the *reduced shape* of the
one unauthenticated audit. That test could only ever describe the endpoint it was
written for. Deleting a route removes today's exposure; nothing about the
deletion prevents the next one. The dangerous version of this mistake is not a
route that crawls on purpose — it is a helper imported into an anonymous module
for one innocent function, dragging the crawler in behind it.

Three properties of the walk were chosen deliberately:

**It reads the source, not `sys.modules`.** A runtime check sees only what the
test session happened to import, and would go quiet exactly when a new import
path appeared. An `ast` walk sees the import whether or not anything calls it.

**"Anonymous" means "declares no session dependency", not "requires no
session".** `app/routes/onboarding.py` resolves the session inside its handlers,
via a local `_require_user(nexus_session)`, so three of its four routes are
authenticated in fact and anonymous to any structural check. They are treated as
anonymous rather than argued away: **a check that cannot see an authentication
decision cannot rely on it.** The fix is to declare the dependency, and P5 owns
those routes.

**It carries its own guards.** Two tests exist only to stop the real one passing
vacuously: one asserts `app/research/` still contains the modules being checked,
the other asserts at least one anonymous route was found. The second earned its
place immediately — `include_router` does not flatten in this version of FastAPI,
so the first implementation classified *every* route as authenticated and passed
while checking nothing.

### 3. `app.research.ssrf` is exempt, and only it

An anonymous module may import the SSRF guard. It may not import `crawler` or
`extract`.

The guard is not the exposure. It resolves a hostname and refuses a private
address; it is what makes a fetch safe rather than what performs one.
`connectors/domain_check.py` proves a domain claim by fetching a well-known file
and is required to use it — and `/domains/{claim_id}/check` is one of the
hand-rolled-auth routes above, so it reads as anonymous.

Forbidding the import would not stop that fetch. It would push `domain_check.py`
towards its own copy of the guard, which is the worst outcome available: two SSRF
implementations, one of them younger and less tested, on the path that fetches an
address a caller supplied.

### 4. The rate limiter is re-keyed, not retired

`(ip, domain, global)` becomes `(workspace, global)`. The first two limits lost
their subject with the anonymous path: there is no address to attribute a crawl
to when every caller is authenticated, and no reflected-DoS shape when the target
must be a domain the workspace has claimed. `hash_ip` and the `X-Forwarded-For`
trust chain — `trusted_proxy_ips`, `trusted_proxies`, `lib/client-address.ts` —
go with them.

No migration was required. A bucket is an opaque string, so the `ip:` and
`domain:` rows are simply never written again and age out through
`purge_expired`.

**The per-workspace number is provisional and says so in the source.** P11 builds
the research job model and will know what a run costs; a limit nobody has
measured should not present itself as a measured one.

## Consequences

- **D9 is void, not satisfied.** It asked how long to retain crawl data about a
  company with no account, and how that company could request deletion. Nothing
  collects such data now, so there is no TTL to ratify and no request to answer.
  This is the rare good ending for a privacy obligation: the strongest answer
  turned out to be not collecting it. Finding #14 narrows to re-verification
  alone.
- **The landing page loses its first-value moment.** `doc/11` §3.1 flags this and
  it is the real cost of the decision: the audit was value at minute seven, and
  the review gate at minute twenty is now the only one. It raises the stakes on
  P8 and P13.
- **`/domains/{claim_id}/check` is now the only unmetered outbound fetch in the
  product**, and finding #4 cited the per-domain bucket — deleted here — as its
  mitigation. The finding is updated to say the phase made it worse. It is
  narrower than the preview ever was (guarded, pinned, no redirects, tied to a
  claim the caller initiated), but it is no longer sitting behind anything.
- **`calculators/audit.py` is now wired to nothing.** Kept, because `doc/11`
  §3.1 makes its scores the dashboard's first real numbers at P11. It is covered
  by its own 29 tests, so it cannot rot silently.
