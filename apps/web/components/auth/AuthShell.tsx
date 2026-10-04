import Link from 'next/link'
import type { ReactNode } from 'react'
import { NexusMark } from '@/components/ui/NexusMark'
import { IconSparkle } from '@/components/art/Icons'

/**
 * The frame around every auth page.
 *
 * One full-bleed animated blue background with a single elevated white card
 * centred on top. The product serves many business domains, so the background
 * drifts a set of domain chips (the seven directors) behind the card, and the
 * palette pairs the app's blue with the landing page's gold — blue is the
 * primary, gold the accent (the sparkle eyebrow, the heading underline, one
 * aurora and the card's sheen), so the sign-in screen reads as the same brand
 * as the marketing site.
 *
 * Everything moves with CSS, not JavaScript: the entrances run at first paint
 * with no hydration, and the global `prefers-reduced-motion` rule collapses
 * every duration to ~0 rather than leaving anything hidden. The whole decorative
 * layer is `aria-hidden` and desktop-only.
 */

/** The domains NEXUS runs — drifted behind the card to say "many domains". */
const DOMAINS: { label: string; pos: string; anim: string }[] = [
  { label: 'Marketing', pos: 'left-[7%] top-[16%]', anim: 'animate-float' },
  { label: 'Sales', pos: 'right-[9%] top-[13%]', anim: 'animate-drift' },
  { label: 'Finance', pos: 'left-[5%] top-[45%]', anim: 'animate-sway' },
  { label: 'Operations', pos: 'right-[6%] top-[42%]', anim: 'animate-float' },
  { label: 'People', pos: 'left-[11%] bottom-[16%]', anim: 'animate-drift' },
  { label: 'Strategy', pos: 'right-[10%] bottom-[19%]', anim: 'animate-sway' },
  { label: 'Chief of Staff', pos: 'left-[38%] bottom-[9%]', anim: 'animate-float' },
]

export function AuthShell({
  title,
  intro,
  children,
  footer,
}: {
  title: string
  intro: ReactNode
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <main
      id="main"
      tabIndex={-1}
      className="theme-app relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-10 sm:px-6"
    >
      {/* ── Animated background ── */}
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-gradient-to-br from-brand-700 via-brand-600 to-brand-900"
      >
        {/* Aurora — two blue, one gold, drifting on different clocks. */}
        <div className="absolute -right-32 -top-32 h-[34rem] w-[34rem] rounded-full bg-brand-400/30 blur-3xl motion-safe:animate-drift" />
        <div className="absolute top-1/3 -left-32 h-[30rem] w-[30rem] rounded-full bg-azure-500/25 blur-3xl motion-safe:animate-float" />
        <div className="absolute -bottom-40 right-1/4 h-[28rem] w-[28rem] rounded-full bg-gold-400/20 blur-3xl motion-safe:animate-sway" />

        {/* Faint grid. */}
        <div className="absolute inset-0 opacity-[0.06] [background-image:linear-gradient(theme(colors.white)_1px,transparent_1px),linear-gradient(90deg,theme(colors.white)_1px,transparent_1px)] [background-size:48px_48px]" />

        {/* Drifting domain chips — the "many domains" the product serves. */}
        {DOMAINS.map((d, i) => (
          <span
            key={d.label}
            style={{ animationDelay: `${i * 0.6}s`, animationDuration: `${9 + i}s` }}
            className={`absolute hidden items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3.5 py-1.5 text-meta font-medium text-white/85 shadow-lg backdrop-blur-md lg:inline-flex ${d.pos} ${d.anim}`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-gold-400" />
            {d.label}
          </span>
        ))}
      </div>

      {/* ── The card ── */}
      <div className="animate-rise-scale relative z-10 w-full max-w-md">
        <div className="relative overflow-hidden rounded-panel border border-white/15 bg-white/95 p-8 shadow-e3 backdrop-blur-xl sm:p-10">
          {/* Blue↔gold sheen along the top edge. */}
          <div className="animate-sheen absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r from-brand-500 via-gold-400 to-brand-500" />

          <div className="animate-rise" style={{ animationDelay: '0.05s' }}>
            <Link
              href="/"
              className="inline-flex w-fit rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-4 focus-visible:ring-offset-white"
              aria-label="NEXUS home"
            >
              <NexusMark />
            </Link>
          </div>

          <div
            className="animate-rise mt-8 inline-flex items-center gap-2 rounded-full bg-gold-100 py-1 pl-1.5 pr-3"
            style={{ animationDelay: '0.12s' }}
          >
            <span className="grid h-5 w-5 place-items-center rounded-full bg-gold-200 text-gold-700">
              <IconSparkle className="h-3 w-3" />
            </span>
            <span className="font-mono text-2xs uppercase tracking-[0.18em] text-gold-700">
              AI Business Operating System
            </span>
          </div>

          <h1
            className="animate-rise mt-4 font-sans text-page font-semibold text-cloud-900"
            style={{ animationDelay: '0.18s' }}
          >
            {title}
          </h1>
          <span
            className="animate-grow-x mt-3 block h-[3px] w-14 rounded-full bg-gold-400"
            style={{ animationDelay: '0.4s' }}
            aria-hidden="true"
          />

          <p
            className="animate-rise mt-4 text-body leading-relaxed text-cloud-600"
            style={{ animationDelay: '0.24s' }}
          >
            {intro}
          </p>

          <div className="animate-rise mt-7" style={{ animationDelay: '0.32s' }}>
            {children}
          </div>

          {footer ? (
            <div
              className="animate-rise mt-8 border-t border-cloud-200 pt-5 text-meta text-cloud-500"
              style={{ animationDelay: '0.42s' }}
            >
              {footer}
            </div>
          ) : null}
        </div>

        {/* The promise, under the card. */}
        <p className="animate-fade-in mt-6 flex items-center justify-center gap-2 text-center text-meta leading-relaxed text-white/75" style={{ animationDelay: '0.5s' }}>
          <span className="h-1 w-1 shrink-0 rounded-full bg-gold-400" />
          Every number NEXUS shows you is fetched or computed. None of them are generated.
        </p>
      </div>
    </main>
  )
}
