import type { Metadata } from 'next'
import { Suspense } from 'react'
import { AcceptInvitation } from '@/components/onboarding/AcceptInvitation'
import { AuthShell } from '@/components/auth/AuthShell'

export const metadata: Metadata = {
  title: 'Accept your invitation',
  robots: { index: false, follow: false },
}

/**
 * Where an invitation link lands.
 *
 * `useSearchParams` forces the reading component into a client boundary that
 * Next needs a `Suspense` wrapper for; without it the build fails rather than
 * degrading, which is the correct trade but an easy one to be surprised by.
 */
export default function AcceptInvitationPage() {
  return (
    <AuthShell
      title="You have been invited"
      intro="Your role was chosen by whoever invited you. This screen does not offer to change it — that is deliberate."
    >
      <Suspense fallback={<p className="font-mono text-sm text-ink-500">Loading…</p>}>
        <AcceptInvitation />
      </Suspense>
    </AuthShell>
  )
}
