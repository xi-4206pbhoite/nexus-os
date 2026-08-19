import type { Metadata } from 'next'
import Link from 'next/link'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import { Logo } from '@/components/ui/Logo'

export const metadata: Metadata = {
  title: 'Fill in the rest',
  robots: { index: false, follow: false },
}

/**
 * The questions that used to be signup.
 *
 * Goals, context, department definitions, tools, team and brief recipients all
 * lived inside the seven-step setup wizard, ahead of the dashboard and behind a
 * required currency select. None of them is needed to run the audit or to reach the
 * product, and asking for a ranked list of quarterly goals and an average deal size
 * before showing anything is the specific failure doc 04 §2e names.
 *
 * So they live here instead: same component, same catalogue, same scope tags — and
 * nothing on the page is required. A user who never opens it has a working
 * workspace, which was not true before.
 */
export default function OnboardingDetailsPage() {
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
            Optional detail
          </p>
        </header>

        <div className="py-10">
          <h1 className="font-display text-title font-medium text-ink-900">
            Fill in the rest
          </h1>
          <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
            None of this is required, and nothing here is holding anything up. Each
            answer sharpens what the product can say about your business, and each one
            you skip stays unanswered rather than becoming a guess. The scope beside a
            question is where that answer will live.
          </p>
          <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
            You can leave at any point —{' '}
            <Link
              href="/dashboard"
              className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
            >
              back to your dashboard
            </Link>
            . Answers are saved as you move between steps.
          </p>

          <div className="mt-10">
            <OnboardingWizard flow="details" />
          </div>
        </div>
      </div>
    </main>
  )
}
