import Link from 'next/link'
import type { ReactNode } from 'react'
import { NexusMark } from '@/components/ui/NexusMark'

/**
 * The frame around every auth page.
 *
 * One full-bleed deep-blue background with a single elevated white card centred
 * on top — the form lives in the card. This replaces the earlier 50/50 split:
 * the card-over-background layout reads as one focused surface rather than two
 * competing halves, and it collapses cleanly to a phone (the card simply centres
 * on the same background) with no second column to hide.
 *
 * The background is built from token colours — a gradient, two soft glows and a
 * faint grid — so it needs no image to look finished. A real image can be laid
 * behind the card later; see the marked slot below.
 *
 * The promise the product is built on sits under the card in quiet white, so the
 * one line that states what NEXUS is still travels with every sign-in screen.
 */
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
      {/* ── Full-bleed background ──
          A positioned layer (not `-z-10`, which would fall behind the
          `.theme-app` white base and vanish). The card sits above it with
          `z-10`. */}
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-gradient-to-br from-brand-700 via-brand-600 to-brand-900"
      >
        {/* Drop a background image in here when there is one:
            <img src="…" alt="" className="absolute inset-0 h-full w-full object-cover opacity-40" />
            The gradient above and the overlays below keep the card legible over it. */}
        <div className="absolute -right-32 -top-32 h-[32rem] w-[32rem] rounded-full bg-brand-400/25 blur-3xl" />
        <div className="absolute -bottom-32 -left-24 h-[30rem] w-[30rem] rounded-full bg-azure-500/20 blur-3xl" />
        <div className="absolute inset-0 opacity-[0.06] [background-image:linear-gradient(theme(colors.white)_1px,transparent_1px),linear-gradient(90deg,theme(colors.white)_1px,transparent_1px)] [background-size:48px_48px]" />
      </div>

      {/* ── The card ── */}
      <div className="relative z-10 w-full max-w-md">
        <div className="rounded-panel border border-white/15 bg-white p-8 shadow-e3 sm:p-10">
          <Link
            href="/"
            className="inline-flex w-fit rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-4 focus-visible:ring-offset-white"
            aria-label="NEXUS home"
          >
            <NexusMark />
          </Link>

          <p className="mt-8 font-mono text-2xs uppercase tracking-[0.2em] text-brand-500">
            AI Business Operating System
          </p>
          <h1 className="mt-2 font-sans text-page font-semibold text-cloud-900">{title}</h1>
          <p className="mt-3 text-body leading-relaxed text-cloud-600">{intro}</p>

          <div className="mt-7">{children}</div>

          {footer ? (
            <div className="mt-8 border-t border-cloud-200 pt-5 text-meta text-cloud-500">
              {footer}
            </div>
          ) : null}
        </div>

        {/* The promise, under the card. */}
        <p className="mt-6 text-center text-meta leading-relaxed text-white/75">
          Every number NEXUS shows you is fetched or computed. None of them are generated.
        </p>
      </div>
    </main>
  )
}
