# The end-to-end goal: what works, what is simulated, what is not built

Regenerate the evidence with:

```
services/api/.venv/bin/python scripts/goal_walkthrough.py
```

**50 checks, 0 failures**, against a real API and Neon. Re-runnable.

## Working, verified through HTTP

| | |
|---|---|
| Two companies, two founders | `parulbhoite315+acme…` and `parulbhoite315+zahra…` |
| Isolation | A sees finance/sales, B sees operations/hr; A gets **404** on B's departments |
| Invitation | `parulbhoite31@gmail.com` invited to B as Operations manager |
| The link carries the company | Its token names workspace *and* role, so the joiner never picks a company and structurally cannot pick the wrong one |
| The invitation is emailed | Wired this session — it had only ever been handed back to the inviter |
| Member lands on a dashboard | Scoped to **operations only**; `hr` is 404, not merely hidden |
| The company brain | Built from the founder's own answers, versioned, every claim naming its source |
| The persona interview | Four questions, resumable; declaring seniority is refused and the dashboards do not widen |

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

## The brain, and why it needs no model

`generated_by = 'answers'`. By the end of onboarding the founder has typed what
they sell, who they sell it to and how each department works, every answer still
carrying its question — so **assembling that is not generating**. It invents
nothing and names a source for every line, which is I1 exactly.

The archived design had only `model` and `unavailable`, which would have meant
no API key, no brain. The model's job when it arrives is to enrich a real brain
rather than to be the only way to have one.

Three rules the schema enforces, not just the code: a grounded brain cannot be
stored with empty provenance; an unavailable one cannot be stored without a
reason; and a partial unique index makes two current brains impossible rather
than merely unlikely.

## The persona interview, and the line it must not cross

`doc/05` §2.6 was already an invariant, and this is the feature that would break
it — a chat is exactly where you would let someone describe themselves into more
access.

**Role and departments are never asked.** They come from the invitation, which
somebody else issued. Typing "I'm the CFO" into a chat box is not a promotion,
and the walkthrough asserts both halves: the answer is refused *and* the
dashboards do not widen afterwards.

Scripted, so it works with no API key (ADR 0011). A model makes the wording
conversational; it does not decide what is asked or what is stored.

## Not built

**Phases 10–21.** Phases 0–9 are complete and green in CI, and the brain and
persona above are Phase 13 and personalisation work pulled forward because the
goal asked for them. What is not pulled forward is Phase 10, the retrieval core
— so the brain is assembled directly from answers rather than retrieved through
a scoped path. When P10 lands, that assembly should move behind it.

## Open findings

| # | |
|---|---|
| 17 | Rolling session has no absolute cap — a decision, not a defect |
| 22 | A client error returned as a 500 |
| 23 | `GET /dashboards` spends 25–30 round trips; the timeout was raised, the round trips were not fixed |
| — | **Rotate the Neon credential `npg_2sQGXiOzueB7`** — it has been in a conversation log since P5 |
