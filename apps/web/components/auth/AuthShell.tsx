import Link from 'next/link'
import type { ReactNode } from 'react'
import { NexusMark } from '@/components/ui/NexusMark'

/**
 * The frame around every auth page.
 *
 * Two columns on desktop: the form on the left, a brand panel on the right that
 * deliberately echoes the landing page — the same tagline, and the same
 * "Morning Brief" / "Health Score" product cards the hero floats over its
 * landscape — rebuilt in the product's blue palette (ADR 0066). The point is
 * that signing in does not feel like leaving the site: the thing the visitor
 * was just reading about is the thing they see while entering it. The panel is
 * `aria-hidden` and drops away below `lg`, where a form has better uses for the
 * space.
 *
 * ## The cards carry the `Illustrative` tag
 *
 * CLAUDE.md's content rule — never invent a number — binds the marketing surface
 * too, and these cards show numbers that were written for the page. Each carries
 * the same `Illustrative` marker the landing hero uses, because a card is
 * screenshot-shaped and the screenshot travels without a footnote.
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
            <p className="font-mono text-2xs uppercase tracking-[0.2em] text-brand-500">
              AI Business Operating System
            </p>
            <h1 className="mt-3 font-sans text-page font-semibold text-cloud-900">{title}</h1>
            <p className="mt-3 text-body leading-relaxed text-cloud-600">{intro}</p>
            <div className="mt-7">{children}</div>
          </div>

          {footer ? <div className="w-full max-w-md text-meta text-cloud-500">{footer}</div> : null}
        </div>

        {/* ── The brand panel ──
            A deep-blue composition that mirrors the landing hero in the app's
            own palette: tagline, the hero's product cards, and the promise the
            product is built on. `aria-hidden` and desktop-only — it is
            reassurance and context, never content the form depends on. */}
        <aside
          className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-brand-800 lg:flex"
          aria-hidden="true"
        >
          {/* Depth: two soft glows and a faint grid — token colours only. */}
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-400/30 blur-3xl" />
            <div className="absolute -bottom-24 -left-20 h-96 w-96 rounded-full bg-azure-500/20 blur-3xl" />
            <div className="absolute inset-0 opacity-[0.06] [background-image:linear-gradient(theme(colors.white)_1px,transparent_1px),linear-gradient(90deg,theme(colors.white)_1px,transparent_1px)] [background-size:46px_46px]" />
          </div>

          {/* Top: mark, tagline, headline. */}
          <div className="relative px-12 pt-14">
            <NexusMark tone="dark" />
            <p className="mt-12 font-mono text-2xs uppercase tracking-[0.22em] text-brand-200">
              Your AI executive team
            </p>
            <h2 className="mt-4 max-w-md font-sans text-[2rem] font-semibold leading-tight text-white">
              Built around your company.
            </h2>
            <p className="mt-4 max-w-sm text-body leading-relaxed text-brand-100">
              Connect your website, documents and tools once. NEXUS tells you what
              needs attention — and does the work.
            </p>
          </div>

          {/* Middle: the hero's product cards, in the blue palette. */}
          <div className="relative my-8 px-12">
            <div className="mx-auto max-w-sm space-y-4">
              {/* Morning Brief */}
              <div className="rounded-2xl border border-cloud-200 bg-white p-4 shadow-e3">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 shrink-0 rounded-full bg-azure-500" />
                  <span className="font-mono text-2xs uppercase tracking-[0.18em] text-cloud-400">
                    Morning Brief
                  </span>
                  <IllustrativeTag />
                </div>
                <p className="mt-2.5 text-[0.92rem] font-medium leading-snug text-cloud-800">
                  Pipeline value rose while three deals went quiet for 11 days.
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {['CRM', 'GA4'].map((s) => (
                    <span
                      key={s}
                      className="rounded-md bg-cloud-100 px-1.5 py-0.5 font-mono text-2xs text-cloud-500"
                    >
                      source: {s}
                    </span>
                  ))}
                </div>
              </div>

              {/* Health Score */}
              <div className="ml-auto w-[88%] rounded-2xl border border-cloud-200 bg-white p-4 shadow-e3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-2xs uppercase tracking-[0.18em] text-cloud-400">
                    Health Score
                  </span>
                  <IllustrativeTag />
                </div>
                <div className="mt-1 flex items-end gap-1.5">
                  <span className="font-sans text-4xl font-semibold leading-none text-cloud-900">
                    72
                  </span>
                  <span className="pb-1 text-xs text-cloud-400">/ 100</span>
                </div>
                <div className="mt-3 space-y-1.5">
                  {[
                    { label: 'Sales', v: 84 },
                    { label: 'Marketing', v: 61 },
                    { label: 'Finance', v: 77 },
                  ].map((d) => (
                    <div key={d.label} className="flex items-center gap-2">
                      <span className="w-16 shrink-0 text-2xs text-cloud-500">{d.label}</span>
                      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-cloud-200">
                        <span
                          className="block h-full rounded-full bg-brand-500"
                          style={{ width: `${d.v}%` }}
                        />
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Bottom: the promise. */}
          <div className="relative px-12 pb-14">
            <div className="h-px w-full bg-white/10" />
            <p className="mt-6 max-w-sm font-sans text-lg font-medium leading-snug text-white">
              Every number NEXUS shows you is fetched or computed. None of them are
              generated.
            </p>
            <p className="mt-2 font-mono text-2xs uppercase tracking-[0.14em] text-brand-200">
              The rule the product is built on
            </p>
          </div>
        </aside>
      </div>
    </main>
  )
}

/** The marker every product mock carries — see the file's top note. */
function IllustrativeTag() {
  return (
    <span className="ml-auto shrink-0 rounded-md bg-cloud-100 px-1.5 py-0.5 font-mono text-2xs uppercase tracking-[0.14em] text-cloud-500">
      Illustrative
    </span>
  )
}
