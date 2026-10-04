import Link from 'next/link'
import type { ReactNode } from 'react'
import { NexusMark } from '@/components/ui/NexusMark'
import { IconSparkle } from '@/components/art/Icons'

/**
 * The frame around every auth page.
 *
 * A clean, premium composition: one elevated white card centred over a calm
 * deep-blue background, with the domains NEXUS serves scrolling in a single
 * contained strip pinned to the bottom. The palette pairs the app's blue with
 * the landing page's gold — blue is the ground, gold is the accent (the sparkle
 * eyebrow, the heading underline, the card's top sheen, the strip's dots) — so
 * the sign-in screen reads as the same brand as the marketing site.
 *
 * The earlier version scattered the domain chips across the whole viewport, which
 * let them collide with the card and the footer at the bottom edge. They live in
 * one bottom band now — a sibling block, never absolutely positioned over the
 * card — so nothing can overlap at any height.
 *
 * Everything moves with CSS, not JavaScript: entrances run at first paint with no
 * hydration, and the global `prefers-reduced-motion` rule collapses every
 * duration rather than leaving anything hidden.
 */

const DOMAINS = [
  'Marketing',
  'Sales',
  'Finance',
  'Operations',
  'People',
  'Strategy',
  'Chief of Staff',
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
      className="theme-app relative flex min-h-screen flex-col overflow-hidden"
    >
      {/* ── Calm animated background ── */}
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-gradient-to-br from-brand-700 via-brand-600 to-brand-900"
      >
        <div className="absolute -right-40 -top-40 h-[36rem] w-[36rem] rounded-full bg-brand-400/25 blur-3xl motion-safe:animate-drift" />
        <div className="absolute -bottom-48 -left-40 h-[36rem] w-[36rem] rounded-full bg-gold-400/15 blur-3xl motion-safe:animate-float" />
        <div className="absolute inset-0 opacity-[0.05] [background-image:linear-gradient(theme(colors.white)_1px,transparent_1px),linear-gradient(90deg,theme(colors.white)_1px,transparent_1px)] [background-size:52px_52px]" />
      </div>

      {/* ── The card ── */}
      <div className="relative z-10 flex flex-1 items-center justify-center px-4 py-10 sm:px-6">
        <div className="animate-rise-scale w-full max-w-md">
          <div className="relative overflow-hidden rounded-[1.75rem] border border-white/15 bg-white p-8 shadow-e3 sm:p-10">
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
          <p className="animate-fade-in mt-6 flex items-center justify-center gap-2 text-center text-meta leading-relaxed text-white/70" style={{ animationDelay: '0.5s' }}>
            <span className="h-1 w-1 shrink-0 rounded-full bg-gold-400" />
            Every number NEXUS shows you is fetched or computed. None of them are generated.
          </p>
        </div>
      </div>

      {/* ── One OS, every domain — a single contained strip, never over the card. ── */}
      <div
        aria-hidden="true"
        className="animate-fade-in relative z-10 shrink-0 border-t border-white/10 bg-brand-900/30 py-4 backdrop-blur-sm"
        style={{ animationDelay: '0.6s' }}
      >
        <p className="mb-3 text-center font-mono text-2xs uppercase tracking-[0.22em] text-white/45">
          One OS, every domain
        </p>
        <div className="mask-fade-x overflow-hidden pause-on-hover">
          <div className="flex w-max motion-safe:animate-marquee">
            {[0, 1].map((copy) => (
              <div key={copy} className="flex shrink-0 items-center">
                {DOMAINS.map((d) => (
                  <span
                    key={d}
                    className="flex shrink-0 items-center gap-3 px-6 text-meta font-medium text-white/70"
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
