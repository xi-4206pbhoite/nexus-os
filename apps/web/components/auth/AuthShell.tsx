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
      <div className="mx-auto grid min-h-screen max-w-6xl grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* ── The form ── */}
        <div className="flex flex-col px-6 py-8 sm:px-10 lg:py-12">
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
          <div className="absolute inset-x-0 bottom-0 p-10">
            <p className="max-w-sm font-display text-xl leading-snug text-bone-100">
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
