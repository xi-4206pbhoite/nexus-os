import Link from 'next/link'
import type { ReactNode } from 'react'
import { Logo } from '@/components/ui/Logo'

/**
 * The frame around a setup page that is not part of the main flow.
 *
 * Finding F10. `/onboarding/[department]` and `/onboarding/documents` rendered
 * as bare content on an empty background — no logo, no account link, no way
 * onward except the browser's Back button. Both are load-bearing: the
 * department blocks are how each director gets anything to work with, and the
 * documents page is how the brain gets real source material. Both were
 * reachable only by typing the URL, because the wizard's own stages are
 * `company`, `departments` and `review`, and neither of these is one of them.
 *
 * A shell rather than a copy of the header in two files, because that is how
 * the third one comes to disagree with the first two.
 */
export function SetupShell({
  eyebrow,
  children,
  width = 'max-w-2xl',
}: {
  /** What this page is, in the header's right-hand corner. */
  eyebrow: string
  children: ReactNode
  width?: string
}) {
  return (
    <main className="min-h-screen bg-bone-50">
      <div className={`mx-auto ${width} px-6 py-8 sm:px-10`}>
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-ink-100 pb-6">
          <Link
            href="/"
            className="inline-flex rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-500"
            aria-label="NEXUS OS home"
          >
            <Logo />
          </Link>
          <div className="flex flex-wrap items-center gap-4">
            <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
              {eyebrow}
            </p>
            <Link
              href="/dashboard"
              className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
            >
              Dashboard
            </Link>
            <Link
              href="/onboarding"
              className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
            >
              Workspace setup
            </Link>
            <Link
              href="/account"
              className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
            >
              Account
            </Link>
          </div>
        </header>

        <div className="py-10">{children}</div>
      </div>
    </main>
  )
}
