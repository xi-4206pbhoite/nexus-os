import Link from 'next/link'
import type { ReactNode } from 'react'
import { NexusMark } from '@/components/ui/NexusMark'

/**
 * The frame around every auth page.
 *
 * Two columns on desktop: the form on the left, the paper-cut landscape on the
 * right. The landscape is the landing page's own artwork rather than a stock
 * illustration, so signing in does not feel like leaving the product — but it is
 * `aria-hidden` and drops away entirely below `lg`, where a form has better uses
 * for the space.
 *
 * ## The artwork reaches the edge of the glass
 *
 * It did not. The grid was `max-w-6xl mx-auto`, so at 1440 the whole two-column
 * layout was 1152px wide and centred — which left a 144px strip of bone
 * page-background to the right of a full-bleed navy artwork panel. A dark panel
 * that stops 144px short of the window reads as a layout that failed to finish
 * loading, and it was the first thing anybody saw on the sign-in page.
 *
 * The grid is now full width. The *form* is what stays measured: its column
 * centres a `max-w-md` block, so the reading column is unchanged and only the
 * artwork gained the space it should always have had.
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
    <main id="main" tabIndex={-1} className="theme-app min-h-screen">
      <div className="grid min-h-screen w-full grid-cols-1 lg:grid-cols-2">
        {/* ── The form ── */}
        <div className="flex flex-col items-center px-6 py-8 sm:px-10 lg:py-12">
          <div className="w-full max-w-md">
            <Link
              href="/"
              className="inline-flex w-fit rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-4 focus-visible:ring-offset-white"
              aria-label="NEXUS home"
            >
              <NexusMark />
            </Link>
          </div>

          {/* `justify-center` with a bounded gap rather than `py-10`: the form
              was pinned to the vertical centre of the column while the logo sat
              at the top, which on a 900px window left ~180px of nothing between
              them and put the heading below the midpoint. */}
          <div className="flex w-full max-w-md flex-1 flex-col justify-center py-8">
            <h1 className="font-sans text-page font-semibold text-cloud-900">{title}</h1>
            <p className="mt-3 text-body leading-relaxed text-cloud-600">{intro}</p>
            <div className="mt-7">{children}</div>
          </div>

          {footer ? <div className="w-full max-w-md text-meta text-cloud-500">{footer}</div> : null}
        </div>

        {/* ── The welcome panel ──
            The signed-in product's own indigo, not the landing page's navy
            artwork — so the brand the user is about to enter is the brand they
            see while entering it. A column so the promise sits at the bottom and
            cannot collide with the decorative field above it at any height. */}
        <div
          className="relative hidden flex-col justify-end overflow-hidden bg-brand-600 lg:flex"
          aria-hidden="true"
        >
          {/* A soft field of brand light — token colours only, no image request. */}
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-400/40 blur-3xl" />
            <div className="absolute -bottom-16 -left-10 h-80 w-80 rounded-full bg-azure-500/30 blur-3xl" />
          </div>
          <div className="relative shrink-0 px-12 pb-14 pt-10">
            <NexusMark tone="dark" className="mb-8" />
            <p className="max-w-sm font-sans text-2xl font-semibold leading-snug text-white">
              Every number NEXUS shows you is fetched or computed. None of them are
              generated.
            </p>
            <p className="mt-3 text-2xs uppercase tracking-[0.14em] text-brand-100">
              The rule the product is built on
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}
