# ADR 0015 — Doc 08 is the question bank, and where it loses to doc 06

- **Status:** Accepted
- **Date:** 18 August 2026
- **Resolves:** **D17** — where doc 08 sits in the precedence order
- **Needed by:** phase R3, which implements doc 08 §1.6 and §2-§7

## Context

Doc 07 §1 sets the precedence: **doc 07 > doc 06 > doc 05 > doc 04 > doc 03/01**.
Doc 08 is not in that list. It arrived later and is described in `doc/00-README.md`
as *"extracted from the prototype, so it records what exists rather than what was
intended"*.

D17 asked where it ranks. The question became blocking once the registration flow
needed department-specific questions, because doc 08 §2-§7 is the only place they
are specified — 30 questions across six departments, each with its type, its option
list, and what it changes downstream. Inventing them instead would have been worse
in every respect.

## Decision

**Doc 08 is authoritative for question *content*, and subordinate to doc 06 for
question *classification*.**

That split is not a compromise; the two documents are about different things. Doc 08
knows what to ask — it was extracted from a working prototype and its "what it
changes" column is a specification of downstream behaviour. Doc 06 §2.5 is the
security model, and it is explicit in a way doc 08 is not:

> *"Average deal size and marketing budget are L3 Sales and L3 Finance facts. They
> are not 'company facts' visible to everyone merely because they arrived through a
> form. Tag them at capture."*

Doc 08 §0 says every answer is stored *"as an L1 or L2 fact"*. For most of the set
that is right — what counts as a lead, which stages a pipeline has, when an order is
late. These are **definitions**, and hiding them serves nobody.

For five of them it is wrong, and they are classified L3 instead:

| Question | Classified | Why doc 08 §0 is wrong here |
|---|---|---|
| §4.3 spend approval threshold | L3 Finance | A money threshold. Doc 06 §2.5's own example in all but name |
| §4.5 runway that would worry you | L3 Finance | Discloses how close to the edge the company is |
| §5.5 supplier you are most exposed to | L3 Operations | A named dependency and its share — doc 08's own sample answer is exactly that |
| §6.3 biggest people risk | L3 HR | Free text that will often identify an individual |
| §7.3 market you are trying to enter | L3 Strategy | Unannounced expansion intent |

A Viewer reaches L2. None of the five should be readable by one.

## Two corrections to doc 08

**§1.6's arithmetic is wrong.** It says *"multi-select across the **seven** below"*
and computes 39 fields from `4 + 7 x 5`. Only **six** department blocks exist in the
document, and the seventh could only be Executive — which doc 05 §10 defines as a
synthesis layer that consumes the others and produces no data of its own, and which
is why the composite score is out of six, never seven. Read as six: **34 fields, not
39**. `test_the_executive_department_is_never_asked_anything` holds this.

**Two of the 30 already existed**, so 28 were added and 2 reused:

- §2.3 "Monthly budget for acquisition" is `monthly_marketing_budget` (already L3
  Finance, exactly as doc 06 §2.5 names it).
- §4.1 "When does your financial year end?" is `fiscal_year_start`.

Asking either again would put one fact in two rows and let them disagree — the same
reason `Sink` exists (ADR: none; see `Question.sink`).

## Consequences

- **`Question.asked_of` is a new field, and deliberately not `department`.** D15
  warned about exactly this conflation. `asked_of` routes — which block a question
  appears in, and therefore who is asked. `department` classifies — which department
  owns the answer at L3. Doc 08 §3.1's pipeline stages are `asked_of=SALES` with
  `department=None`; §4.3's threshold sets both. Collapsing them would have made
  every Sales question an L3 Sales fact and hidden the pipeline stages from a Viewer
  for no reason.
- **D15 is now partly answered by doc 08 rather than by me.** Its hardest open
  question — who answers department-scoped questions — is settled by doc 08 §0: *"The
  workspace owner selects which departments the company runs and answers those
  departments' questions. An invited team member answers only their own department's
  set."* That is implemented as two independent narrowings in `may_be_asked`.
- **D15's remaining questions stay open.** Whether one manager's answer binds the
  whole department, and what happens to answers when someone changes department, are
  untouched by doc 08 and unresolved here.
- **Doc 08 §1.5 is not yet implemented.** It specifies `stated_purpose` as a
  four-option select (`diagnose` / `consolidate` / `time` / `grow`) that changes what
  each dashboard leads with; it currently exists as free text from doc 06 §2.5. Now
  that doc 08 is authoritative for content, this becomes a real change to make —
  tracked as R2c, not done here, because it alters an existing question's type and
  belongs with the persona work that consumes it.

## Revisit when

Doc 08 and doc 06 disagree about something that is *not* a classification — a
question's wording, its options, or whether it is asked at all. This ADR gives doc 08
the content and no more, so a conflict of that shape would need its own decision.
