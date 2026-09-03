import type { Metadata } from 'next'
import { Button } from '@/components/ui/Button'
import { Logo } from '@/components/ui/Logo'

export const metadata: Metadata = {
  title: 'Page not found',
  robots: { index: false, follow: false },
}

/**
 * A 404 that stays in the product rather than dropping to the framework default.
 *
 * Offers the way back, and a way in.
 *
 * The second button used to be "Run a free audit", which needed no account.
 * Phase 2 retired that endpoint, so it pointed at nothing.
 */
export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col bg-bone-50 px-6 py-8 sm:px-10">
      <a href="/" className="w-fit" aria-label="NEXUS OS home">
        <Logo />
      </a>

      <div className="flex flex-1 items-center">
        <div className="w-full max-w-lg">
          <p className="font-mono text-2xs uppercase tracking-[0.14em] text-ink-400">
            404
          </p>
          <h1 className="mt-3 font-display text-title font-medium text-ink-900">
            There&rsquo;s nothing at this address
          </h1>
          <p className="mt-3 text-[0.95rem] leading-relaxed text-ink-600">
            The page may have moved, or the link may be wrong.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Button href="/">Back to the start</Button>
            <Button href="/register" variant="secondary">
              Create an account
            </Button>
          </div>
        </div>
      </div>
    </main>
  )
}
