import type { Metadata } from 'next'
import Link from 'next/link'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import { Logo } from '@/components/ui/Logo'

export const metadata: Metadata = {
  title: 'Set up your workspace',
  robots: { index: false, follow: false },
}

/**
 * Workspace setup.
 *
 * Client-fetched, like the account page and for the same reason: a server
 * component would have to render either the signed-in or the signed-out view
 * before the client knew which, and a mismatch shows as a flash of the wrong
 * screen.
 *
 * The wizard renders what the API says this caller may see and change. Nothing
 * on this page decides that — a hidden field is a presentation choice, and the
 * boundary is in `app/routes/setup.py`.
 */
export default function OnboardingPage() {
  return (
    <main className="min-h-screen bg-bone-50">
      <div className="shell-wide py-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-ink-100 pb-6">
          <Link
            href="/"
            className="inline-flex rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-500"
            aria-label="NEXUS OS home"
          >
            <Logo />
          </Link>
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
            Workspace setup
          </p>
        </header>

        <div className="py-10">
          <h1 className="font-display text-title font-medium text-ink-900">
            Set up your workspace
          </h1>
          <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
            Four questions, one of them required. Every answer is stored with the scope
            it belongs at — shown beside each question, so you can see where it will
            live before you type it. Answering never changes what you or anyone else can
            see.
          </p>
          <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
            Everything else — your goals, your departments, your team, the tools you use
            — waits until after you have seen something. None of it is needed to start.
          </p>

          <div className="mt-10">
            <OnboardingWizard />
          </div>
        </div>
      </div>
    </main>
  )
}
