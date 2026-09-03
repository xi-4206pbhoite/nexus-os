# ADR 0020 — The department question bank, and the one question cut from it

**Status** Accepted
**Date** 3 September 2026
**Decided by** Phase 7, applying Q33.

## Context

`doc/12` §Phase 7 requires the question bank as data, and requires that **any
question no capability consumes is cut**, with the cuts recorded here.

The rule exists because the pressure runs entirely one way. Nobody proposes
thirty-nine onboarding questions. They propose one — it would be useful to know,
and it is only one more field — and the thirty-ninth arrives the same way the
first did. An earlier draft of `doc/08` carried thirty-nine. A founder does not
experience that as thoroughness.

## Decision

**Twenty-nine questions**, five per department across six, minus one cut.

Every question declares `consumed_by`: the capability that reads its answer.
`tests/test_question_bank.py` fails on a question that declares none, which is
the guard against drift — the rule is only worth writing down if something
checks it on every commit.

The names are namespaced (`marketing.growth_planner`, not `growth_planner`) and
a test enforces that too. Two departments will eventually both have a
"forecast", and a bare name makes the collision invisible: the second one added
silently reads as the first.

### The cut: Finance 4.1, "when does your financial year end?"

Not because nothing consumes it — a great deal does. Because **P6's company
stage already asks when the financial year starts**, and the same fact asked
from both ends is two rows that can disagree with nothing to decide which wins.

This is the neighbouring case to Q33 rather than Q33 itself, and worth naming as
its own rule: *cut a question something else already answers*. It is easier to
miss than an unconsumed question, because both questions look useful in
isolation and the duplication is only visible if you hold two documents in your
head at once. `test_no_question_duplicates_the_company_stage` now holds them for
you.

### The one scope exception

Department answers are `L3_DEPARTMENT`. One is not: **"Should NEXUS track visa
and document expiry?"** sits at `L4_RESTRICTED`, because the answer decides
whether the product holds immigration documents at all. That is a decision about
people rather than about a department, and it is opt-in for the same reason —
nobody should be enrolled into having their documents held by a default.

A test asserts this is the *only* exception, so a second one has to be argued
rather than added.

## Consequences

- **`doc/08` §2–7 and this module can drift**, and nothing checks that they
  agree. The doc is prose with tables; this is data. If a question changes
  there, somebody has to change it here. Worth a test comparing them if the doc
  ever becomes machine-readable — today it would be a parser for one input.
- **`consumed_by` names capabilities that do not exist yet.** P15 builds the
  registry, P16 onward builds the capabilities. Until then these are claims
  about the future, and the test only checks that a claim was made — not that it
  is true. When the registry lands, the stronger test is to check every
  `consumed_by` against it, and that is the test that would actually catch a
  question whose consumer was quietly dropped.
- **Twenty-nine is still a lot to ask.** Q27 is what makes it bearable — the
  founder answers their own department now and defers the rest, and each
  unanswered block surfaces on its director as the thing that turns it on. That
  half is built in P7's authority model; the deferral UI is not yet.
