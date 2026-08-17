# 0009 — Register and sign-in UI, built ahead of the milestone sequence

- **Status:** Accepted
- **Date:** 17 August 2026
- **Decider:** the user — *"build the register and login UI"*, after asking where
  users register and being told they could not
- **Relates to:** [0005](0005-contributor-l3-subset.md),
  [0008](0008-neon-as-the-primary-database.md), doc 07 §3 (milestone order)

## Context

Doc 07 sequences M6 (the scoped retrieval layer) next, and every milestone after
it depends on that layer existing. An auth UI is not in M6, nor in any completed
milestone — M1 built the auth *endpoints* and stopped there deliberately, because
the security core comes before the surfaces.

The gap surfaced from the user's side: they asked where a user registers
themselves. The answer was nowhere. `POST /auth/register` and `POST /auth/login`
both worked, nothing in `apps/web` called either, and the header's **Sign in**
link was `href="#"` — a placeholder that reads as a broken product rather than an
unbuilt one.

## Decision

**Build the register and sign-in UI now, out of sequence.** M6 remains next for
the product's own logic; this is a surface over endpoints that already exist and
are already tested.

Scope held deliberately tight: register, sign in, sign out, and a signed-in
account page. **No domain-claim UI** — that is the flow that actually creates a
workspace, and it needs DNS or file verification with its own states and waiting
periods. It stays on the API for now, and the account page says so.

## Two API changes, because the UI could not exist without them

Both are preconditions rather than scope creep, and both are worth recording.

**1. `GET /auth/session` is new.** `/auth/me` depends on `CurrentScope`, which
requires an active workspace — correctly, since it returns the authority used to
reach workspace data. But a person has no workspace between registering and
verifying a domain, so `/me` returned 403 and **a signed-in user could not
retrieve even their own identity**. No client can answer "am I logged in?" after
a page reload without that, so no sign-in UI was possible.

The new endpoint returns exactly what `/login` returns, read from the session
cookie instead of from credentials. It discloses nothing new — the same user, the
same memberships, under the same `membership_own_rows` policy.

A new dependency, `current_session`, sits alongside `current_scope` rather than
becoming a flag on it. It yields a `ResolvedSession` and **cannot** produce a
`ScopedSession`, and since `retrieval/` accepts nothing else, no route built on it
can reach workspace-scoped data. That limit is structural, which is the whole
reason it is a separate dependency: a boolean parameter on `current_scope` would
have put "may I skip the workspace requirement?" one wrong argument away from
being an authority bypass.

`/auth/session` also refuses to echo a stale pointer. A membership can be revoked
while a session is live (doc 06 §4.15), leaving `user_session.active_workspace_id`
aimed at a workspace the user has lost. Reporting it verbatim would leave a client
insisting it is somewhere `current_scope` refuses on the next request, with no way
to explain why.

**2. Logout never cleared its cookies.** Found while testing, and pre-existing.

The handler called `response.delete_cookie(...)` on an injected `Response` and
then `return Response(status_code=204)`. FastAPI merges the injected response's
headers only when a handler returns *data*; returning a `Response` replaces it
outright, so **both deletions were silently discarded**. The session was genuinely
revoked server-side — which is why nothing caught it, and why it was not an access
bug — but the browser kept sending a cookie for a dead session.

That mattered the moment a UI existed. The session cookie is `httponly`, so the
readable CSRF companion is the only signed-in signal a client can see; one
surviving logout leaves every client believing a revoked session is live. Logout
now clears both, on the response it actually returns.

## The web layer

Auth requests go through this app's own `/api/auth/*` route handlers, never to
the API directly. Same reasoning as the Preview proxy, plus one that is specific
to auth: `SameSite=Lax` on the session cookie is load-bearing (it is the primary
CSRF defence per `app/auth/csrf.py`, with double-submit as the second layer), and
it only holds while the cookie is first-party. Calling the API from the page would
make every auth request cross-origin — CORS with credentials and `SameSite=None`
— which removes exactly that protection. Proxying keeps the cookie first-party
and leaves the API with no CORS surface at all.

The proxy forwards `Cookie` and `X-CSRF-Token` upstream and `Set-Cookie` back. It
uses `Headers.getSetCookie()` rather than `get('set-cookie')`, because login sets
two cookies and `get` joins them into one string no browser can split back — and
cookie values may legitimately contain commas, so splitting is not a fix.

## Consequences

- **Login is not rate limited.** `rate_limit.py` covers only the Preview path, so
  password attempts are unbounded. argon2id and timing equalisation make offline
  and oracle attacks hard; online guessing against a weak password is not
  mitigated. The design questions are real — per-IP or per-account, and a
  per-account lock is a denial-of-service vector against a known user — so this
  goes to `DECISIONS-REQUIRED.md` as **D14** rather than being invented here.
  **It should be answered before this is exposed publicly.**
- Registration still sends no email (M5's carried gap). The success screen says
  so plainly instead of instructing the user to check an inbox that will stay
  empty.
- The account page shows what a signed-in person actually has, which is an
  account and no workspace, and names the gate that explains why. A skeleton
  dashboard with zeroes in it would have broken I10 on the product's own surface.
- Sessions last 12 hours (`session_max_age_seconds`), unchanged.

## Revisit if

M6 lands and a real signed-in surface exists — the account page is a placeholder
for a workspace home, not a destination.
