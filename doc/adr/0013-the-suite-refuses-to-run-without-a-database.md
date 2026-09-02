# ADR 0013 — The test suite refuses to run without a database

**Status** Accepted
**Date** 2026-09-03
**Decided by** Phase 0. No product judgement was required — this is a
consequence of what the suite claims to prove.

## Context

Ninety-four of the tests in `services/api/tests` assert *database* behaviour:
row-level security policies, `CHECK` constraints, partial unique indexes, the
`FORCE ROW LEVEL SECURITY` flag, and the fact that the application role is
neither a superuser nor `BYPASSRLS`. Twelve of them exist solely to attempt
cross-tenant and cross-workspace access and fail.

Before Phase 0 each of the nine modules holding those tests carried its own
alias:

```python
DB_URL = database_url()
requires_db = pytest.mark.skipif(DB_URL is None, reason="No NEXUS_DATABASE_URL")
```

Nine copies, and CI had no database. So every CI run reported **94 skipped, exit
code 0** — green, with the product's central security claim never exercised
anywhere. `BUILD-STATUS.md` recorded two `CHECK`-constraint violations sitting in
`main` that a single DB-backed test would have caught on the commit that
introduced them.

A skip is not a weaker pass. It is the absence of evidence, presented in the same
colour as evidence.

## Decision

**A database is a precondition for running this suite, not an option.** Four
parts:

1. **`requires_db` is a real marker**, declared in `pyproject.toml`, with
   `--strict-markers` so that misspelling it is an error rather than a silent
   no-op. The nine local `skipif` aliases become `pytest.mark.requires_db`.

2. **There is exactly one place a database test may be skipped** —
   `pytest_collection_modifyitems` in `tests/conftest.py`, and only when no
   database is configured at all.

3. **A skipped `requires_db` test fails the session.**
   `pytest_runtest_logreport` records them and `pytest_sessionfinish` sets a
   failing exit status, naming each one. This catches a skip arriving by any
   route, including a `pytest.skip()` inside a fixture — which is how five of the
   nine modules used to skip.

4. **`tests/test_ci_contract.py` asserts the other half**, unconditionally:
   a database is configured; it is reachable; the connected role has
   `rolsuper = false` and `rolbypassrls = false`; and `alembic_version` matches
   the migration head on disk. `test_a_skipped_database_test_fails_the_run`
   proves part 3 by running a throwaway suite containing one skipping
   `requires_db` test and asserting the run exits non-zero.

`tests/dburl.py` now resolves the URL **once, at import**. It previously read the
environment on every call, and `conftest.py` deliberately pins
`NEXUS_DATABASE_URL` to empty for hermeticity — so a runtime read fell through to
the `.env` fallback, which exists on a developer's machine and never in CI. The
same code would have read Neon locally and `None` in CI. That is precisely the
machine-state dependence `dburl.py` was written to remove.

**Coverage has a floor**, `--cov-fail-under=74`, set to the measured branch
coverage at Phase 0 (74.21%) rounded down so it cannot flake on a fraction. It
goes up and never down. It is a ratchet that makes a deleted test visible, not a
quality claim — 74% here sits beside four of ten invariants proved.

## Why

- **The alternative is a suite whose verdict is unrelated to its subject.** A
  green run with 94 skips says nothing about isolation, and it is indistinguishable
  at a glance from a green run that proved it.
- **One skip site, one guard.** Nine `skipif` aliases were nine independent
  chances to lose a suite. The guard means losing one is loud rather than silent.
- **The contract test is unconditional on purpose.** Making it conditional on CI
  would leave the local run — the one a developer actually watches — able to pass
  with no database.

## Consequences

- **A developer cannot run the suite without a database.** That is the point, and
  `scripts\db-ci.ps1` (ADR 0014) exists so the cost of having one is one command.
- **`test_the_schema_is_migrated_to_head` immediately failed against the
  developer's Neon instance**, which is at revision `0014` while the repository
  heads at `0009`, with three tables no migration here creates. The test found a
  real drift on the first run. Resolving it is Parul's call and is recorded in
  `DECISIONS-REQUIRED.md`.
- Nine modules keep a module-level `DB_URL`, now with `assert DB_URL is not None`
  where they used to `pytest.skip`. An assert is the loud version of the same
  statement.

## What this does not settle

- **The guard fails the session, it does not fail a test.** A reader scanning for
  `F` in pytest's output sees the contract test's failure but learns about the
  skips from the summary that `pytest_sessionfinish` writes to stderr. Good
  enough; a per-test failure would need the skip decision to become a failure at
  collection, which loses the reason.
- **Coverage is measured over `app` only.** `tests` is type-checked but not
  covered by itself, which is correct but means a test file that is never
  collected is invisible to the floor.
