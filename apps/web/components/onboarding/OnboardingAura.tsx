'use client'

/**
 * The motion on the onboarding screen, in two pieces.
 *
 * It started as one large blurred disc fixed behind the transcript, with a
 * rotating dashed ring around it. Two things were wrong with that and both are
 * visible in a screenshot: at 42rem it was a 672px circle centred on the
 * viewport, so on the boot screen — which has nothing else on it — the entire
 * page was one soft blob; and a dashed ring slowly rotating behind body text
 * reads as a loading spinner that forgot to stop, which is decoration drawing
 * attention to itself rather than to the conversation.
 *
 * So: a **wash** with no discernible edge, and a **mark** small enough to be
 * looked at deliberately. The wash is atmosphere and says nothing. The mark
 * carries the state, at a size where its detail is legible instead of blurred
 * into a gradient.
 *
 * Both are `aria-hidden`. Every state either shows is also written in words
 * elsewhere on the screen — `globals.css` collapses animations to one iteration
 * under `prefers-reduced-motion`, and neither of these may be the only signal.
 *
 * **Colour comes from Tailwind utilities only (ADR 0066).** Every tone below is
 * a class name resolved against the `brand`/`clay`/`cloud` families in
 * `tailwind.config.ts` — never a literal hex in this file. The wash reuses
 * Tailwind's own gradient machinery (`from-*`/`to-*` write the
 * `--tw-gradient-stops` the arbitrary `radial-gradient(...)` shape reads) so the
 * colour is a standard utility and only the shape is custom; the mark uses the
 * `stroke-*`/`fill-*` utilities directly. `brand` carries work and the one
 * arrival; `clay` is kept for the single state that is a risk, a live
 * microphone; `cloud` is the neutral for waiting on the person.
 */

export type AuraState =
  /** The read, and every model call after it. */
  | 'thinking'
  /** The microphone is open. A distinct colour, because it is a distinct risk. */
  | 'listening'
  /** Waiting on the person. */
  | 'idle'
  /** The Brain is live. */
  | 'ready'

/**
 * The wash, as a background utility — a shapeless radial field, never a hex
 * literal. The shape is the one arbitrary value (`radial-gradient` is not a
 * Tailwind utility); the colour comes from `from-*`/`to-*`, which is, and which
 * is what writes the `--tw-gradient-stops` the shape reads.
 */
const WASH: Record<AuraState, string> = {
  thinking: 'from-brand-500/[0.16] to-transparent to-[72%]',
  listening: 'from-clay-500/[0.16] to-transparent to-[72%]',
  idle: 'from-cloud-500/[0.12] to-transparent to-[72%]',
  ready: 'from-brand-500/20 to-transparent to-[72%]',
}
const WASH_SHAPE = 'bg-[radial-gradient(58rem_30rem_at_50%_-10rem,var(--tw-gradient-stops))]'

/** The mark's ring and core, as `stroke-*`/`fill-*` utilities. */
const TONE: Record<AuraState, { ring: string; core: string }> = {
  thinking: { ring: 'stroke-brand-400', core: 'fill-brand-600' },
  listening: { ring: 'stroke-clay-400', core: 'fill-clay-500' },
  idle: { ring: 'stroke-cloud-300', core: 'fill-cloud-400' },
  ready: { ring: 'stroke-brand-300', core: 'fill-brand-500' },
}

/**
 * Atmosphere. A gradient bleeding down from above the fold.
 *
 * Deliberately shapeless — it reaches `transparent` before any edge could be
 * made out, which is the whole difference from the disc it replaces. Nothing
 * here animates except the colour, which crossfades over a second when the
 * state changes; a background that moves competes with the text on top of it.
 */
export function OnboardingAura({ state }: { state: AuraState }) {
  return (
    <div
      aria-hidden
      className={`pointer-events-none fixed inset-0 -z-10 transition-[background] duration-1000 ${WASH_SHAPE} ${WASH[state]}`}
    />
  )
}

/**
 * The state, as one small mark.
 *
 * Concentric rather than blurred: at this size the two rings and the core are
 * distinguishable, so "waiting on a model" and "waiting on you" differ in a way
 * you can actually see rather than in an opacity nobody notices. The outer ring
 * only spins while something is in flight — motion means work here, so a mark
 * that always moved would mean nothing.
 */
export function PresenceMark({
  state,
  size = 22,
}: {
  state: AuraState
  size?: number
}) {
  const tone = TONE[state]
  const active = state === 'thinking' || state === 'listening'

  return (
    <svg
      aria-hidden
      viewBox="0 0 32 32"
      style={{ width: size, height: size }}
      className="shrink-0 overflow-visible"
    >
      {/* Dashed, and only turning while there is work. Six dashes rather than a
          fine dotted line: at 22px a fine one aliases into a grey smudge. */}
      <circle
        cx="16"
        cy="16"
        r="14"
        fill="none"
        strokeOpacity={active ? 0.85 : 0.4}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeDasharray="5 6.3"
        className={`animate-spin-slow ${tone.ring}`}
        style={{
          transformOrigin: 'center',
          animationDuration: active ? '3.2s' : '0s',
          animationDirection: state === 'listening' ? 'reverse' : 'normal',
        }}
      />
      {/* The halo pulse is the "something is happening" signal, and it is paused
          rather than hidden when nothing is: a mark that vanished between turns
          would read as the agent having gone away. */}
      <circle
        cx="16"
        cy="16"
        r="9"
        fill="none"
        strokeOpacity="0.5"
        strokeWidth="1.5"
        className={`animate-pulse-ring ${tone.ring}`}
        style={{
          transformOrigin: 'center',
          animationPlayState: active ? 'running' : 'paused',
        }}
      />
      <circle cx="16" cy="16" r="5.5" fillOpacity={active ? 1 : 0.75} className={tone.core} />
    </svg>
  )
}
