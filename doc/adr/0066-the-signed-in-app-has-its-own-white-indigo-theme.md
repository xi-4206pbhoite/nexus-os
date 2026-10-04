# 0066. The signed-in app has its own white-and-indigo theme, scoped away from the landing page

- **Status:** Accepted
- **Date:** 3 October 2026
- **Deciders:** Parul (requested in session, UI/UX pass)
- **Affects:** `apps/web/tailwind.config.ts` (new `brand`, `azure`, `cloud` colour
  families), `apps/web/app/globals.css` (the `.theme-app` scope and its `app-*`
  component classes), `apps/web/components/ui/NexusMark.tsx` (new product mark),
  and every signed-in shell that now carries `.theme-app` — `AppShell`,
  `AuthShell`, `app/error.tsx`, `app/not-found.tsx`, and the onboarding/dashboard
  surfaces reskinned on top of it.

## Context

Parul asked for a UI/UX redesign of the signed-in product — a new logo (no PNG),
a white application background, and onboarding and dashboard screens redrawn in
the direction of a supplied reference (a clean white SaaS layout with an
indigo/violet primary, an indigo progress stepper, a dark side-rail on the
dashboard, and a black "X" logo mark whose upper-right arm is blue). The landing
page was explicitly out of scope: *"Landing page looks perfect, don't touch it."*

Two facts about the existing code make this a real decision rather than a recolour:

1. **The landing page and the app share one palette and one logo.** The marketing
   identity is the cut-paper system — navy `ink`, warm `bone` surfaces, a single
   `gold` accent — defined in `tailwind.config.ts` and `globals.css`, and the
   `Logo` component is rendered by both the landing nav and the app shell. Editing
   those shared tokens to make the app white-and-indigo would have changed the
   landing page too, which the brief forbids.

2. **A standing team rule names a different accent.** The dev-team design-token
   rule asserts a single magenta accent (`#E331D0`) with no blue or purple, owned
   by the `adf-brand-guide`. The reference Parul supplied is indigo/blue on white.
   These disagree, and the rule is that a disagreement of this kind is not
   resolved silently.

Parul was asked which direction the app theme should take and chose **indigo/violet
primary together with the logo's blue accent**, overriding the magenta rule for the
signed-in product, with the wordmark set to **"NEXUS"**.

## Decision

Introduce a **product theme that is additive and scoped**, leaving the landing
page's tokens and `Logo` exactly as they are.

- **Three new colour families** in `tailwind.config.ts`, used only by the app:
  `brand` (indigo, the primary — buttons, active nav, progress, focus), `azure`
  (the logo's blue accent), and `cloud` (cool neutral for white-based surfaces,
  borders and text). The landing page references none of them, so it is unaffected
  by their addition; the existing `ink`/`steel`/`slate`/`bone`/`gold`/`clay`
  families are untouched.
- **A `.theme-app` scope** in `globals.css` that paints white, sets cool-neutral
  text, re-bases the focus ring onto `brand`, and defines the `app-card`,
  `app-panel`, `app-btn`, `app-field`, `app-label` component classes — the
  white-based counterparts of the marketing `.paper`/`.control` set. Only
  signed-in shells carry the class.
- **A new `NexusMark` component** — a bold "X" built from token-coloured strokes
  (`stroke-cloud-900` ink, `stroke-azure-500` for the upper-right arm) and the
  word "NEXUS". Colours come from Tailwind `stroke-*`/`text-*` utilities, so no
  raw hex sits in the component.

> **Amendment (same session) — palette:** Parul found the indigo too generic for
> the product. The `brand` and `azure` token *values* were swapped to the
> "Minimalist Blue" palette (deep blue `#1A3D63` primary, steel `#4A7FA7` accent,
> pale `#B3CFE5`, deepest `#0A1931`, cool white `#F6FAFD`). Only the token values
> and the `.theme-app` button variables changed — every component keeps addressing
> `brand`/`azure`/`cloud`, so the whole app (and the logo's accent arm) re-themed
> at once. Steel `#4A7FA7` is accent-only: at 3.9:1 on white it never carries
> small body text or white button labels, so the deep blue is the primary fill.
>
> **Amendment (same session):** Parul then asked for the new mark on the landing
> page as well. `NexusMark` now replaces the cut-paper `Logo` in the landing
> `Nav` and `Footer` too, so the product has **one mark everywhere**. The old
> `components/ui/Logo.tsx` had no remaining importers and was removed. The landing
> page keeps the rest of its cut-paper identity (serif type, gold accent, bone
> surfaces) — only the wordmark changed there.
>
> **Amendment (same session) — auth layout:** The auth pages (`AuthShell`, shared
> by login, register, verify, reset) went through two layout directions at Parul's
> direction. First a 50/50 split — form on the left, a brand panel on the right
> that mirrored the landing hero (tagline + the Morning Brief / Health Score
> product cards, tagged *Illustrative*). Parul then rejected the split and chose,
> from a supplied reference, a **single elevated white card centred over a
> full-bleed deep-blue background** (gradient, faint grid, soft glows). That is the
> accepted layout. **Reasoning:** the card-over-background reads as one focused
> surface rather than two competing halves, and collapses to mobile with no second
> column to hide; the background is built from theme tokens so it needs no image,
> with a marked slot to drop a real image behind the card later. The product cards
> from the split panel were retired with it. **Revisit trigger:** if a real
> background image or product screenshot is introduced, or if the auth flow grows
> steps that no longer fit one card.
>
> **Amendment (same session) — auth ground:** The centred card was first given a
> dark full-bleed deep-blue background with animated aurora and drifting domain
> chips. Parul found the dark panel heavy and the scattered chips cluttered (they
> collided with the footer), and chose, from a supplied reference, a **light,
> airy ground instead** — near-white with a faint blue/gold wash and a few subtle
> drifting geometric shapes (hexagons, a cube, a ring, a diamond). The card stays
> white and premium (blue+gold sheen bar, gold sparkle eyebrow, animated gold
> underline); the domains moved into one contained "every domain" marquee at the
> bottom. The palette still pairs the app blue with the landing gold as accents.
> **Reasoning:** the light ground reads calmer and more premium than a heavy dark
> panel, keeps the brand's blue+gold without shouting, and contained layers
> (shapes behind the card, marquee as a sibling band) remove the overlap the
> scattered chips caused. **Revisit trigger:** if a dark theme is introduced, or
> if a real illustration/photo replaces the geometric accents.

The magenta standing rule is **overridden for the signed-in product by this ADR**,
at Parul's explicit direction. The landing page does not adopt indigo and is not
in scope for the override.

## Consequences

- The landing page is provably untouched: it shares no token with the app theme
  and keeps its own `Logo`.
- The product carries **one mark everywhere** — `NexusMark`, in both the landing
  page and the signed-in app (see the amendment above). The earlier split between
  a cut-paper landing mark and the new app mark is retired. The landing page's
  colour identity (serif, gold, bone) is otherwise unchanged; only its wordmark
  moved to the new mark.
- The magenta design-token rule and the `adf-brand-guide` no longer describe the
  signed-in product. If the team wants one brand across marketing and app, that is
  a separate decision that would supersede this one.
- Raw colour values still live only in the two sanctioned token files; components
  compose the names, as the existing discipline requires.
