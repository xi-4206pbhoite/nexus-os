import Link from 'next/link'
import type { ReactNode } from 'react'
import { Logo } from '@/components/ui/Logo'
import { PaperLandscape } from '@/components/art/PaperLandscape'

/**
 * The frame around every auth page.
 *
 * Two columns on desktop: the form on the left, the paper-cut landscape on the
 * right. The landscape is the landing page's own artwork rather than a stock
 * illustration, so signing in does not feel like leaving the product — but it is
 * `aria-hidden` and drops away entirely below `lg`, where a form has better uses
 * for the space.
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
    <main className="min-h-screen bg-bone-50">
      {/* Full width, so the artwork reaches the edge of the screen instead of
          sitting in a letterbox with bone-coloured margin either side. The 6xl cap
          this replaces meant that above ~1150px the page stopped growing and the
          two columns drifted into the middle. */}
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* ── The form ── */}
        <div className="flex flex-col px-[var(--shell-x)] py-8 lg:py-12">
          <Link
            href="/"
            className="inline-flex w-fit rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-500"
            aria-label="NEXUS OS home"
          >
            <Logo />
          </Link>

          <div className="flex flex-1 flex-col justify-center py-10">
            <div className="w-full max-w-md">
              <h1 className="font-display text-title font-medium text-ink-900">{title}</h1>
              <p className="mt-3 text-[0.95rem] leading-relaxed text-ink-600">{intro}</p>
              <div className="mt-8">{children}</div>
            </div>
          </div>

          {footer ? <div className="w-full max-w-md text-sm text-ink-500">{footer}</div> : null}
        </div>

        {/* ── The artwork ── */}
        <div className="relative hidden overflow-hidden bg-ink-900 lg:block" aria-hidden="true">
          {/* No `object-cover`: it has no effect on inline SVG. The viewBox
              letterboxes against `bg-ink-900`, which is the artwork's own
              ground, so the fit is invisible. */}
          <PaperLandscape className="absolute inset-0 h-full w-full" />

          {/* A scrim, because the caption sits on the artwork rather than below it.
              At the old capped width the illustration letterboxed and the text landed
              on flat `bg-ink-900`; full width pushes the artwork down behind it, and
              bone-100 on pale water is unreadable. The gradient is the artwork's own
              ground colour, so it darkens the foot of the picture rather than
              introducing a panel. */}
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-ink-900 via-ink-900/85 to-transparent"
            aria-hidden="true"
          />

          <div className="absolute inset-x-0 bottom-0 p-10">
            <p className="max-w-xl font-display text-xl leading-snug text-bone-100">
              Every number NEXUS shows you is fetched or computed. None of them are
              generated.
            </p>
            <p className="mt-3 font-mono text-2xs uppercase tracking-[0.14em] text-slate-300">
              The rule the product is built on
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}
