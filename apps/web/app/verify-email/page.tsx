import type { Metadata } from 'next'
import { Suspense } from 'react'
import { AuthShell } from '@/components/auth/AuthShell'
import { VerifyEmailPanel } from '@/components/auth/VerifyEmailPanel'

export const metadata: Metadata = {
  title: 'Confirm your email',
  robots: { index: false, follow: false },
}

export default function VerifyEmailPage() {
  return (
    <AuthShell
      title="Confirm your email"
      intro="One click and your address is confirmed. Confirming lets you invite colleagues and connect tools."
    >
      {/* `useSearchParams` needs a Suspense boundary, or `next build` fails the
          whole route with a prerender error rather than a warning. */}
      <Suspense fallback={<p className="text-ink-500">Loading…</p>}>
        <VerifyEmailPanel />
      </Suspense>
    </AuthShell>
  )
}
