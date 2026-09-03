# ADR 0017 — Database GUCs are set after connecting, not in the startup packet

**Status** Accepted
**Date** 2026-09-03
**Decided by** Phase 2, closing finding #15.

## Context

`app/db.py` set four timeouts, and three of them did nothing in production for
as long as they existed.

They travelled in asyncpg's `server_settings`, which becomes the connection's
**startup packet**. Stock PostgreSQL applies whatever is in it. Neon does not:
its proxy filters the startup packet to an allowlist and drops the rest without
complaint. On a live application connection:

```
SHOW statement_timeout                     -> 0
SHOW lock_timeout                          -> 0
SHOW idle_in_transaction_session_timeout   -> 5min   (the server default)
SHOW application_name                      -> nexus-api
```

The last line is why this survived. `application_name` was in the same
dictionary and arrived, so the connection was demonstrably healthy and
demonstrably carrying settings — just not those three. Nothing raised, nothing
logged, and `pool_pre_ping` was cheerful throughout.

And CI was green. `tests/test_db_timeouts.py` asserts exactly the right thing —
`SHOW`, against the application's own engine, rather than over the keyword
arguments — but the workflow runs `pgvector/pgvector:pg17`, where the startup
packet works. **ADR 0008 makes Neon the production database.** So the test, the
code and the CI run were each individually correct and the protection existed
nowhere that mattered.

It was found by running the suite against Neon during Phase 2, for an unrelated
reason.

## Decision

**Server-side settings are issued after the connection is established, on the
pool's `connect` event.** Only `application_name` stays in `server_settings`.

```python
@event.listens_for(engine.sync_engine, "connect")
def _set_timeouts(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute(
        "SELECT set_config('statement_timeout', $1, false), ...", values
    )
```

Four details, each of which was a wrong first attempt or nearly one:

**`connect`, not `checkout`.** `connect` fires once per *physical* connection;
`checkout` fires every time one leaves the pool. This costs one round trip per
connection rather than one per request, which on a serverless Postgres billed by
connection-time is the difference between negligible and a line item.

**`set_config(name, $1, false)`, not `SET name = value`.** `SET` does not accept
parameters, so the values — which come from configuration — would have to be
interpolated into SQL. `set_config` takes them as bind parameters.

**`false`, not `true`.** That is `is_local`. `SET LOCAL` would be reverted by the
first `COMMIT`, so the connection would be protected for one transaction and
then hand itself, unprotected, to every later request that checked it out of the
pool. This is the more dangerous failure of the two, because the first
transaction — the one a test is most likely to look at — would pass.

**`$1`, not `%s`.** SQLAlchemy's asyncpg dialect is `numeric_dollar`. The first
version used `%s` and every connection failed with `syntax error at or near "%"`
— which is at least loud, unlike the bug being fixed.

**`application_name` stays where it was**, deliberately. It is the control: if
these three regress, the question is whether the startup packet is being
filtered or the connection is broken, and `application_name` answers it. Moving
it would have removed the only evidence that distinguished the two.

## Consequences

- **The three timeouts are proved on Neon**, not only on stock PostgreSQL.
  Verified the way this repository verifies things — by planting the old
  `server_settings` version and watching `test_db_timeouts.py` go red.
- **The test file states its own limitation.** Reverting this change turns those
  tests red against Neon and leaves them **green** against stock PostgreSQL, so
  a CI run cannot prove the claim. That is written into the module docstring
  rather than left for the next person to rediscover.
- **Two new assertions.** One proves the setting survives a commit and a pool
  checkout cycle — the `SET LOCAL` failure above. One proves `application_name`
  still arrives, keeping the control in place.
- **The general rule, which outlives these three settings:** anything put in
  `server_settings` is a *request*, and a managed Postgres may decline it
  silently. If a setting matters, read it back. `pgvector` availability is
  already reported at `/health/ready` for a related reason; these could
  reasonably join it.
- **This does not generalise to a lockfile-shaped problem, but it rhymes with
  one.** Finding #16 is the same lesson about dependency resolution, and D23 was
  the same lesson about schema. Three incidents, one rule: **an environment that
  differs from production can be green in the place nobody deploys to.**
