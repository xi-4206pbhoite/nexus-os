# ADR 0019 — The AI questionnaire wraps the form; it does not replace it

**Status** Accepted
**Date** 3 September 2026
**Decided by** Parul. Raised as an idea during P5 planning, decided before any
code was written for it.

## Context

Onboarding today is a form: `doc/08` specifies the questions per department, and
P7's `question` / `question_choice` catalogue is where they live. The proposal
was to replace it with an AI-generated questionnaire — a conversation rather than
a form — so that setup feels like being interviewed by someone competent, and so
a **persona** for the user and the company falls out of it.

The instinct is right. A form asks a founder to translate what they know into
somebody else's categories; a conversation lets them answer in their own terms.
And the `persona` table has existed since migration 0002 with nothing writing to
it.

But taken literally — the model *generates* the questions — it collides with
three things that are already decided:

- **ADR 0011: the language model is optional.** "No API key is a supported state,
  not a degraded one." A generated questionnaire on the signup path would make
  the model load-bearing for the one flow every customer must complete. Nothing
  else in the product is.
- **D13 is unanswered.** There is no Anthropic access or model tier yet, so this
  cannot be built against a real model today in any case.
- **`doc/08` specifies the question set**, and each question carries the scope tag
  that decides whether an answer is stored at L2 or L3. A generated question has
  no scope tag, so its answer has nowhere honest to go.

## Decision

**The catalogue stays declarative and the model becomes a presentation layer over
it.**

- `doc/08`'s questions remain the source of truth for *what must be known*, with
  their scope tags. Coverage stays provable: it is a set, and a set can be
  checked.
- The model decides **how to ask** — phrasing, order, follow-ups, and skipping
  what it can already infer from the domain crawl or from an earlier answer. It
  never introduces a question that is not in the catalogue.
- **No key falls back to the plain form.** The same pattern as `FileMailer` versus
  `SmtpMailer`: the flow works end to end in local and CI with no vendor, and the
  conversation is the good path rather than the only one.
- The **persona is derived from answers**, and every field cites the answer that
  produced it. I1 holds — nothing in the Brain is an ungrounded inference — and
  a persona a user disagrees with can be traced to the sentence that caused it.

## Consequences

- **ADR 0011 is unamended**, which is the whole point of choosing "wrap". A
  deployment with no key still onboards customers.
- **This lands in P6 and P7, not P5.** P5 builds company registration — the
  authenticated entry point that does not exist yet — and the questionnaire has
  nothing to attach to until it does. P6's spine and P7's catalogue are where the
  work goes, and both briefs will need rewriting to describe two renderers over
  one catalogue rather than one form.
- **Two renderers, one catalogue** is now an invariant of the onboarding design.
  A question that only works in the conversation is a question the form cannot
  ask, which means a no-key deployment silently collects less — the failure this
  decision exists to prevent. Whatever P7 builds should have a test that the two
  renderers cover the same set.
- **The persona is a new grounded artefact.** It needs the same citation
  discipline as everything else the Brain holds, and it is the first thing
  written to a table that has been empty since M1.
