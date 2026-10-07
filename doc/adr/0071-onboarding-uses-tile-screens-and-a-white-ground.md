# ADR 0071 — Onboarding picks areas and tools on tile screens, on a white ground

- Status: Accepted
- Date: 2026-10-07
- Amends: [0069](0069-conversational-onboarding-with-live-company-brain.md) — specifically
  its "department selection happens in the chat" decision, and the bone/paper +
  ambient-aura chrome Direction A shipped with.
- Related: [0067](0067-combined-onboarding-flow.md) (the catalogue flow whose
  `AreasStage` tile screen this brings back), ADR 0066 (the aura).

## Context

ADR 0069 made onboarding a conversation and folded **department selection into
the chat** as quick-reply chips after the brief, and tools into an in-chat step.
It shipped and was walked end-to-end. Seeing it live, the product owner asked for
three structural/visual changes:

- **Department (Areas of Interest) should be its own tile-selection screen,
  *before* the chat** — as it was in the ADR 0067 catalogue flow (`AreasStage`),
  not chips mid-conversation.
- **The tools step should also be a tile-selection screen**, in the same visual
  language as the areas tiles (keeping the ADR 0069 phase-4 recommendations).
- The onboarding should sit on a **white ground** (a subtle gradient/animated
  accent is fine), not the bone/paper wash — and the **chat input** restyled.

These are owner directives from reviewing the running product, not an open design
question.

## Decision

1. **Areas of Interest returns to a dedicated tile screen, before the chat.**
   `OnboardingEntry` resolves `company → areas → chat`: company creation first
   (`CompanyStage`), then the `AreasStage` tile screen (reused unchanged from the
   catalogue flow — icon tiles, floor of one, `fetchDepartments`/`saveDepartments`,
   Chief of Staff excluded), then the conversation. The in-chat department beat
   (`DeptPicker`) is removed from `ConversationalOnboarding`; the chat reads the
   already-chosen departments on boot for the Brain panel and tool
   recommendations.
2. **The tools step is a tile-selection screen** matching the areas tiles, with
   every ADR 0069 principle intact — nothing filtered, CRMs grouped, the live
   unlock panel, "declare" not "connect", resume-seeding, the
   `onContinue(providers, skipped)` contract, and the phase-4 "Recommended for
   you" shelf and badges.
3. **The onboarding chrome goes white.** `OnboardingShell` and the chat `<main>`
   use a white background with a subtle, reduced-motion-aware gradient/animated
   accent (the aura retuned, or a light gradient) rather than the bone ground.
   The chat composer is restyled to a self-contained modern input.

## Reasoning

- **A choice from a fixed, known set is a picker, not a conversation.** The
  departments are a closed list of six; the website cannot infer which the
  company runs, so the agent would have to ask regardless. A tile screen shows
  all six at once, lets the founder compare and multi-select in one glance, and
  is faster than chips revealed one message in. ADR 0069 folded it into the chat
  for continuity; the owner's call is that continuity lost more than the explicit
  screen gains. `AreasStage` already exists and is tested, so this is a
  re-placement, not new surface.
- **Before the chat, because it scopes the chat.** The chosen departments drive
  which threshold questions are worth asking and what the Brain panel groups —
  so choosing them up front lets the conversation and the panel be department-
  aware from their first turn, instead of the chat opening generic and narrowing
  mid-stream.
- **Tiles for tools, for the same reason areas are tiles** — a bounded catalogue
  of known systems is a selection grid, and matching the two screens' visual
  language makes the flow read as one designed sequence rather than two idioms.
- **White is the product's surface.** The rest of the app is a white/light
  ground; the bone wash was specific to the onboarding's "calm letter" framing.
  Aligning onboarding to the app's ground makes arrival at the dashboard
  continuous rather than a palette change.

## Consequences

- ADR 0069's "department selection happens in the chat" is **reversed**; the rest
  of 0069 (the conversation, the live Brain panel, the website read, the no-model
  block) stands. The three-part "Part X of 3" framing still fits: company +
  areas are the pre-chat setup, the conversation is the middle, assembly the end.
- `ConversationalOnboarding` no longer owns department state — one fewer in-chat
  branch, and `chosenDepartments` becomes a read on boot. If a founder reaches
  the chat with no departments (direct navigation), `OnboardingEntry`'s resolve
  routes them to `areas` first, so the chat can assume a chosen set.
- The bone-ground onboarding screenshots in `docs/design` are now historical.
- This does not touch the Company Brain page, its sources, or the catalogue
  `StartFlow` (still slated for retirement per 0069).

## Revisit trigger

Revisit if any of:
- Onboarding completion drops after moving areas out of the chat — i.e. a
  separate screen before the conversation reads as "more steps" rather than
  "fewer questions," the opposite of the brief behind 0069/0067.
- The white ground with its accent fails contrast or feels flat/clinical in use,
  such that the bone wash (or a stronger accent) served the "something is
  happening" signal better.
- A future need to infer or pre-select departments (from the website or a
  connected system) makes a pre-chat manual screen redundant — at which point the
  choice might move back into a confirm-style chat beat.
