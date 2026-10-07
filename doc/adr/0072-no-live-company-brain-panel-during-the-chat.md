# ADR 0072 — No live Company Brain panel during the onboarding chat

- Status: Accepted
- Date: 2026-10-07
- Amends: [0069](0069-conversational-onboarding-with-live-company-brain.md) — its
  phase-1 "a live Company Brain panel beside the chat" decision.
- Related: [0071](0071-onboarding-uses-tile-screens-and-a-white-ground.md) (the
  tile-screen + white-ground rework this follows), the Company Brain page
  (ADR 0069 phase 2).

## Context

ADR 0069 made onboarding a chat with a **live Company Brain panel** down the
right-hand side — facts filling in with provenance as the website was read and
the conversation ran. It shipped and was walked end-to-end. After the 0071 rework
(areas and tools as tile screens, white ground) the product owner asked to
**remove the live panel** from the chat.

The panel's job — showing what NEXUS has learned, with each fact's source — is
also done, in full, by the **Company Brain page** (`/brain`), which reads the same
data with the same provenance and is available immediately after onboarding.

## Decision

Remove the live Company Brain panel (`BrainPanel`) from `ConversationalOnboarding`.
The chat is now a single centred column on the white ground. `BrainPanel.tsx` and
its test are deleted (nothing else used them). `chosenDepartments` is still read
once on boot — now only to scope `ToolsStep`'s recommendations. The Company Brain
**page** is untouched: the "building as we talk" idea becomes "see it on its own
page when setup is done."

## Reasoning

- **The panel duplicated the Company Brain page.** It was the headline of 0069
  when the page did not yet exist; now it does (0069 phase 2), with search, the
  relationship graph, and the conversation as a source. A live mirror of a
  surface that already exists is cost without new information.
- **A calmer chat.** The brief behind this whole line of work was "onboarding
  feels too busy." A second column updating in real time beside the conversation
  is motion competing with the thing the person is actually doing — answering.
  One centred column is the calmer read, consistent with 0071's white, tile-based
  direction.
- **Provenance is not lost.** The promise the panel carried — every fact shows
  its source — is intact on the Company Brain page, which is where a founder goes
  to audit and correct. Removing the panel removes a preview, not the guarantee.

## Consequences

- ADR 0069's phase-1 "live Company Brain panel" is **withdrawn**; the rest of
  0069 (the conversation, the website read, the grounded brief, the no-model
  block) and the Company Brain page stand.
- `BrainPanel` and its `mapAgentStateToBrainGroups` mapping are gone; the page
  uses its own `brain-facts`/`brain-sources` mappings and is unaffected.
- The founder no longer sees facts accumulate *during* the chat — the first time
  the assembled Brain is shown is the Company Brain page after onboarding. If that
  loss of in-the-moment feedback proves to matter, see the revisit trigger.
- Screenshots and docs showing the two-column chat are now historical.

## Revisit trigger

Revisit if any of:
- Onboarding feedback shows the live, in-the-moment "it's learning about us"
  signal was load-bearing for trust — i.e. people believed the brief less without
  watching it build — in which case a lighter in-chat affordance (a count, a peek)
  might return without the full panel.
- The Company Brain page proves too easy to miss after onboarding, so the only
  place provenance was shown live is gone and the page is not discovered — a
  routing/surfacing fix, or a reconsideration of this removal.
