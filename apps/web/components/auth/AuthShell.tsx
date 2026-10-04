import Link from 'next/link'
import type { ReactNode } from 'react'
import { NexusMark } from '@/components/ui/NexusMark'
import { IconSparkle } from '@/components/art/Icons'

/**
 * The frame around every auth page.
 *
 * A light, airy ground — near-white with a faint blue/gold wash — scattered with
 * subtle geometric shapes (hexagons, a cube, rings, diamonds) that drift behind a
 * clean white card. Blue is the structure, gold the accent (the sparkle eyebrow,
 * the heading underline, the card's top sheen, a shape or two), so the screen
 * reads as the same brand as the marketing site without a heavy dark panel.
 *
 * The shapes and the domain strip are contained layers — the shapes sit behind
 * the card, the "every domain" strip is a sibling band at the bottom — so nothing
 * overlaps the form at any height.
 *
 * Motion is CSS only: entrances run at first paint, and the global
 * `prefers-reduced-motion` rule collapses every duration rather than hiding
 * anything.
 */

const DOMAINS = ['Marketing', 'Sales', 'Finance', 'Operations', 'People', 'Strategy', 'Chief of Staff']

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
      className="theme-app relative flex min-h-screen flex-col overflow-hidden bg-cloud-50"
    >
      {/* ── Light ground: soft wash + drifting geometry ── */}
      <div aria-hidden="true" className="absolute inset-0">
        <div className="absolute inset-0 [background-image:radial-gradient(42rem_32rem_at_12%_8%,theme(colors.brand.100),transparent_60%),radial-gradient(38rem_30rem_at_88%_92%,theme(colors.gold.100),transparent_62%)]" />

        {/* Hexagon, top-left */}
        <svg className="absolute left-[7%] top-[14%] h-28 w-28 text-brand-200 opacity-70 motion-safe:animate-float" viewBox="0 0 100 100" fill="none" aria-hidden="true">
          <path d="M50 6 L88 28 V72 L50 94 L12 72 V28 Z" stroke="currentColor" strokeWidth="2" />
        </svg>
        {/* Cube, top-right */}
        <svg className="absolute right-[9%] top-[12%] h-24 w-24 text-brand-300 opacity-60 motion-safe:animate-drift" style={{ animationDelay: '1.2s' }} viewBox="0 0 100 100" fill="none" aria-hidden="true">
          <path d="M50 10 L85 30 L50 50 L15 30 Z" stroke="currentColor" strokeWidth="2" />
          <path d="M15 30 V66 L50 86 V50 Z" stroke="currentColor" strokeWidth="2" />
          <path d="M85 30 V66 L50 86 V50 Z" stroke="currentColor" strokeWidth="2" />
        </svg>
        {/* Ring, mid-left */}
        <span className="absolute left-[14%] top-[52%] h-16 w-16 rounded-full border-2 border-gold-300 opacity-60 motion-safe:animate-sway" />
        {/* Diamond, mid-right */}
        <span className="absolute right-[13%] top-[46%] h-12 w-12 rotate-45 rounded-md border-2 border-brand-200 opacity-70 motion-safe:animate-float" style={{ animationDelay: '0.8s' }} />
        {/* Small hexagon, bottom-left */}
        <svg className="absolute bottom-[20%] left-[20%] h-16 w-16 text-gold-300 opacity-60 motion-safe:animate-drift" style={{ animationDelay: '0.5s' }} viewBox="0 0 100 100" fill="none" aria-hidden="true">
          <path d="M50 6 L88 28 V72 L50 94 L12 72 V28 Z" stroke="currentColor" strokeWidth="3" />
        </svg>
        {/* Dot cluster, bottom-right */}
        <span className="absolute bottom-[26%] right-[22%] h-20 w-20 rounded-full bg-brand-100 opacity-70 blur-xl motion-safe:animate-sway" style={{ animationDelay: '1.6s' }} />
        {/* Small filled dot, upper-mid */}
        <span className="absolute left-[30%] top-[9%] h-2.5 w-2.5 rounded-full bg-gold-400 opacity-70 motion-safe:animate-float" style={{ animationDelay: '2s' }} />
      </div>

      {/* ── The card ── */}
      <div className="relative z-10 flex flex-1 items-center justify-center px-4 py-10 sm:px-6">
        <div className="animate-rise-scale w-full max-w-md">
          <div className="relative overflow-hidden rounded-[1.75rem] border border-cloud-200 bg-white p-8 shadow-e3 sm:p-10">
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
              style={{ animationDelay: '0.42s' }}
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
          <p className="animate-fade-in mt-6 flex items-center justify-center gap-2 text-center text-meta leading-relaxed text-cloud-500" style={{ animationDelay: '0.5s' }}>
            <span className="h-1 w-1 shrink-0 rounded-full bg-gold-400" />
            Every number NEXUS shows you is fetched or computed. None of them are generated.
          </p>
        </div>
      </div>

      {/* ── One OS, every domain — a single contained strip. ── */}
      <div
        aria-hidden="true"
        className="animate-fade-in relative z-10 shrink-0 border-t border-cloud-200 bg-white/60 py-4 backdrop-blur-sm"
        style={{ animationDelay: '0.6s' }}
      >
        <p className="mb-3 text-center font-mono text-2xs uppercase tracking-[0.22em] text-cloud-400">
          One OS, every domain
        </p>
        <div className="mask-fade-x overflow-hidden pause-on-hover">
          <div className="flex w-max motion-safe:animate-marquee">
            {[0, 1].map((copy) => (
              <div key={copy} className="flex shrink-0 items-center">
                {DOMAINS.map((d) => (
                  <span
                    key={d}
                    className="flex shrink-0 items-center gap-3 px-6 text-meta font-medium text-cloud-500"
                  >
                    {d}
                    <span className="h-1 w-1 rounded-full bg-gold-400" />
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  )
}
