import type { Metadata } from 'next'
import Link from 'next/link'
import { DashboardLanding } from '@/components/dashboard/DashboardLanding'
import { Logo } from '@/components/ui/Logo'

export const metadata: Metadata = {
  title: 'Your dashboard',
  robots: { index: false, follow: false },
}

/**
 * Where signing in and finishing setup both lead.
 *
 * It holds nothing of its own — it asks the API which director this person
 * belongs to and forwards them. The decision is server-side because it is the
 * same fact that authorises the page it forwards to, and two sources for one
 * fact is how a redirect starts disagreeing with a permission check.
 */
export default function DashboardPage() {
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
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">Dashboard</p>
        </header>

        <div className="py-10">
          <DashboardLanding />
        </div>
      </div>
    </main>
  )
}
