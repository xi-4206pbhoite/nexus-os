# The end-to-end goal: what works, what is simulated, what is not built

Regenerate the evidence with:

```
services/api/.venv/bin/python scripts/goal_walkthrough.py
```

**36 checks, 0 failures**, against a real API and Neon. Re-runnable.

## Working, verified through HTTP

| | |
|---|---|
| Two companies, two founders | `parulbhoite315+acme…` and `parulbhoite315+zahra…` |
| Isolation | A sees finance/sales, B sees operations/hr; A gets **404** on B's departments |
| Invitation | `parulbhoite31@gmail.com` invited to B as Operations manager |
| The link carries the company | Its token names workspace *and* role, so the joiner never picks a company and structurally cannot pick the wrong one |
| The invitation is emailed | Wired this session — it had only ever been handed back to the inviter |
| Member lands on a dashboard | Scoped to **operations only**; `hr` is 404, not merely hidden |

**Plus-addressing is not a workaround.** One company per founder (`doc/11` Q8)
is a rule the product means, so two companies need two founders. Both inboxes
are the same real one.

## Simulated, and why

**The domain-verification gate before inviting.** Marked verified directly, and
the script says so on every run. The gate is right and unsatisfiable here: DNS
needs a record, FILE needs hosting, and EMAIL only matches when the founder's
address is on the company domain — which a Gmail founder never is, because
`is_free_email_domain` refuses to let anyone claim gmail.com. Everything
downstream of the gate is exercised for real.

To make it real: register a founder at an address on the company's own domain,
and the EMAIL method verifies with no DNS at all.

## Not built

**The company brain** is Phase 13, and Phase 10 (the retrieval core) comes
first — the plan calls that one the security core that everything after depends
on. The brain has no substrate until it exists.

**The AI persona chat.** Before anyone builds it, read
`services/api/tests/test_persona_and_invitations.py`. Doc 05 §2.6 is already
enforced there as an invariant:

> No persona field is ever an input to the retrieval predicate.

The persona says **what to lead with**. It must never say **what you may see**.
A chat that infers "this person is a finance lead" must not widen what finance
data they can reach — that is `ScopedSession`'s job and its alone, and the test
asserts `ScopedSession` carries no persona field so the mistake cannot compile.

**Phases 10–21.** Phases 0–9 are complete and green in CI.

## Open findings

| # | |
|---|---|
| 17 | Rolling session has no absolute cap — a decision, not a defect |
| 22 | A client error returned as a 500 |
| 23 | `GET /dashboards` spends 25–30 round trips; the timeout was raised, the round trips were not fixed |
| — | **Rotate the Neon credential `npg_2sQGXiOzueB7`** — it has been in a conversation log since P5 |
