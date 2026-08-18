# 0011 — The language model is an optional dependency

- **Status:** Accepted
- **Date:** 18 August 2026
- **Decider:** the user — *"the Anthropic LLM/API integration will be connected
  and tested later… the application must be usable end-to-end without it"*
- **Relates to:** D11, D13, doc 06 §8, doc 07 M8 and M12

## Context

The Anthropic key arrives later. The obvious reading of that is "stub the AI
and come back to it", and the obvious implementation is a demo mode that returns
plausible text so screens look finished.

That would be the most damaging thing this codebase could contain. The product's
entire position is that a figure on the screen was fetched or computed and can be
traced to its source (I1). A fabricated paragraph that reads like a real
recommendation destroys that whether or not it carries a label, because the label
stays on the screen and the screenshot goes into the customer's email.

## Decision

**No API key is a supported operating state, not a degraded one.** The
application starts, serves every route, and reports the language model as
unavailable with a reason a person can act on.

**Nothing invents content.** `UnavailableProvider` refuses when called;
`ScriptedProvider` returns only what a test explicitly supplied and raises on an
unscripted skill. There is no third provider that improvises.

## Shape

```
app/ai/
  contracts.py            the interface, request/response models, error types
  anthropic_provider.py   the only module that knows the vendor exists
  providers.py            UnavailableProvider · ScriptedProvider
  registry.py             selection from configuration
```

Four decisions inside that are worth recording:

**Availability is a value, not an exception.** `status()` answers before any
call, so a caller renders "this needs an API key" instead of catching an error
from a request it should never have made. Doc 07 §7's honesty rule applied to
our own operations surface.

**`anthropic` is an optional extra, imported lazily.** `pip install -e ".[ai]"`
adds it. Absent, `import app.main` is unaffected — the registry never reaches for
the SDK without a key, and `/health/ready` asks `status()`, which never touches
it. mypy has an `ignore_missing_imports` override for exactly this reason: the
package is *meant* to be missing until the integration is switched on.

**`anthropic_api_key` deliberately bypasses `Settings.require()`.** Every other
secret fails loudly when absent because the application cannot work without it.
This one must not, and routing it through `require()` would turn "no AI yet" into
a crash at startup.

**Grounding travels with the prompt, and so does the prohibition.**
`CompletionRequest.grounding` carries values already computed in deterministic
code, and the system prompt instructs the model to use them exactly and to name a
missing figure rather than produce one. That is the cheap half of I1 — prompt
rules are weak, as doc 06 §7.2 says plainly about L0 knowledge. The expensive
half is M8 validating the response and rejecting figures that were not supplied.

## Consequences

- **`/health/ready` gains a `language_model` check, advisory and never gating.**
  Same treatment as pgvector before M5: an optional capability that must be
  *visible* from the start so nobody discovers its state when the first feature
  needing it is switched on. A readiness probe that failed on a missing API key
  would take the service out of a load balancer over an optional feature.
- **Vendor errors are mapped to our types and never carry the vendor message.**
  A provider error can echo the request back, and the request carries customer
  content. Only the type crosses the boundary.
- **Retry is once, transient only.** Doc 06 §8's pipeline is fetch, compute, one
  model call, validate, retry once, then Unavailable. A 4xx is deterministic, so
  retrying it only spends the budget twice.
- **The kill switch exists now** (`NEXUS_DISABLED_AI_SKILLS`), ahead of the
  skills it will switch off, because task 8.7 needs it and adding it later means
  threading it through every call site.
- **Token budgets are declared but not yet enforced.** `Availability
  .BUDGET_EXHAUSTED` and the two settings exist; the accounting that spends them
  is M8 task 8.6. Recording this so the gap is visible rather than assumed done.

## The claim, and the test that holds it

`test_ai_boundary.py` asserts that **nothing outside `app/ai/` names the
vendor** — verified by planting a violating import and watching the test fail.
Scattered SDK calls are what make a provider decision expensive to revisit, and
D11 leaves open whether a second provider is ever needed.

## When the key arrives

1. Add `NEXUS_ANTHROPIC_API_KEY` to `.env`.
2. `pip install -e ".[ai]"` in `services/api`.
3. `/health/ready` flips `language_model` to `ok`.

No architectural work should remain. What remains is a live integration test
against the real endpoint, which cannot be written honestly without a key.
