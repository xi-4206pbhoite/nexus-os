# ADR 0015 — Configuration fails closed, and a required-looking secret is deleted

**Status** Accepted
**Date** 2026-09-03
**Decided by** Phase 1. Three decisions, taken together because they are one
failure with three surfaces.

## Context

`app/config.py` declared a validator over the three secrets, documented it as
*"strict everywhere else"*, and gave it the body `return v`. It enforced nothing
while presenting as a security control — which is worse than its absence,
because absence is visible in a review and a no-op is not.

Two more things compounded it. `env` defaulted to `local`, and `is_local` also
answered true for `ci`. So a deployment that simply forgot `NEXUS_ENV` served
`/docs` and `/openapi.json` publicly and set `secure=False` on both the session
and the CSRF cookie — over the internet, on a product holding company
financials. Nothing failed and nothing logged.

And `session_secret` was declared here, documented in `.env.example`, listed in
that no-op validator, pinned in `conftest.py`, asserted in `test_hermeticity.py`
— and read by no line of code in the repository.

## Decisions

### 1. `NEXUS_ENV` is required, with no default

The plan offered two fixes: remove `Env.ci` from `is_local`, or make cookie
security independent of it. **Neither addresses the default**, which is what
turned a forgotten variable into insecure cookies. Either one would have left a
deployment with no `NEXUS_ENV` running as `local`.

So `env` has no default. A missing `NEXUS_ENV` is a startup error naming the
variable, rather than a silent choice of the most permissive environment. This
is a third option and it is why the two properties below can stay simple: `ci`
is now only reachable by asking for it.

The blast radius is small and was checked: `conftest.py` already sets
`NEXUS_ENV=ci` for every test, `.env` carries it locally, and the twelve tests
that construct `Settings(...)` directly inherit it from the environment. **CI
needed a line** — `alembic` builds `Settings` of its own and there is no `.env`
there, so `.github/workflows/ci.yml` sets `NEXUS_ENV: ci` at job level. That is
exactly the local-versus-CI divergence Phase 0's `dburl` fix was about, arriving
from the other direction.

### 2. The validator is real, and it is a model validator

It raises when `env` is `staging` or `production` and either `database_url` or
`storage_signing_secret` is empty, naming **every** missing secret in one error.
A deployment fixing them one restart at a time is a deployment being told the
truth slowly.

A `model_validator(mode="after")` rather than a `field_validator` for two
reasons: it reads `env` without depending on field declaration order — the
previous shape would have broken silently if someone moved `env` down the class
— and it can see all the secrets at once.

`local` and `ci` stay permissive, so the process boots and answers a health
check before a database exists. That was always the intent; only the enforcement
everywhere else was missing.

`anthropic_api_key` is deliberately **not** in the list. An empty key is a
supported operating state (ADR 0011), and requiring it would turn "no AI yet"
into a refusal to boot.

### 3. `is_local` is replaced by two narrower properties

| | `cookies_secure` | `docs_enabled` |
|---|---|---|
| `local` | insecure | served |
| `ci` | insecure | **not served** |
| `staging`, `production` | secure | not served |

They differ, and the difference is the point. Plain HTTP is a fact about how
`local` and `ci` are served, so cookie security follows both. `/docs` and
`/openapi.json` together enumerate every endpoint and its schema, and a
developer's machine is the only place that is a convenience rather than a
disclosure — nobody reads `/docs` in CI. One property serving both purposes is
how `ci` came to mean "publish the API surface".

### 4. `session_secret` is deleted

Nothing signs a session token because there is nothing to sign. The token is 256
bits of CSPRNG output and only its SHA-256 hash is stored (`app/auth/tokens.py`),
so presenting it is authenticated by the lookup itself; an HMAC over a random
opaque string adds no property that the random string did not already have.

Deleting it is the honest half of the choice the plan offered. Wiring it into
signing would have been ceremony — a secret to rotate, a failure mode to
operate, and no attack it prevents.

A required-looking secret that nothing reads is not harmless. It teaches whoever
provisions an environment that the list of secrets is approximate, which is
precisely the belief that makes a genuinely missing one survive review.

## Also decided here

**`.env.example` is verified, not generated.** The plan says *"regenerate from
`Settings` so the two cannot diverge"*. Generating it would have produced a
correct file with no comments, and the comments are most of its value — the
`-pooler` warning, the ADR references, why the Anthropic key may be absent.
Instead `tests/test_config_gates.py` asserts set-equality in both directions,
with two named allowlists: `NOT_SETTINGS` for keys something else reads
(`docker-compose.yml`), and `FUTURE` for credentials that do not exist yet, each
naming the phase that will read them. The stated goal — that the two cannot
diverge — is met, and adding a key to either file without saying why fails the
build.

## Consequences

- **A missing `NEXUS_ENV` now stops the process.** Intended. The error names the
  variable, which is a better first symptom than a downstream secret complaint.
- Twelve `Settings(...)` call sites in tests depend on the ambient `NEXUS_ENV`.
  `tests/test_config_gates.py` passes `_env_file=None` **and** deletes the
  variable where a genuinely absent one is the subject — a first version of that
  test passed against the very default it was written to forbid, because
  `_env_file=None` disables the file and not the environment.
- `signed_url_ttl_seconds`, `mailer_backend`, `mail_root` and `model_cache_dir`
  are still unread. The plan defers them to after Phase 3, which wires email;
  they are deliberately kept.
